// Offline tests using installed TypeScript/React; no bundler or .env loading.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');
for (const ext of ['.ts', '.tsx']) {
  require.extensions[ext] = (module, filename) => {
    const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
    });
    module._compile(outputText, filename);
  };
}
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { api, watchEvolution } = require('../src/services/api.ts');
const { formatDistance } = require('../src/services/distance.ts');
const { EvolutionPanel } = require('../src/components/EvolutionPanel.tsx');
const { CompactResults } = require('../src/components/CompactResults.tsx');
const { DriverDetailsPanel } = require('../src/components/DriverDetailsPanel.tsx');
const flush = () => new Promise(setImmediate);
const ok = data => ({ ok: true, json: async () => data });

test('progress calls without an explicit signal retain a timeout', async t => {
  t.mock.method(global, 'fetch', async (url, options) => {
    assert.ok(options.signal instanceof AbortSignal);
    return ok({ run_id: 'run', status: 'completed' });
  });
  await api.getEvolutionProgress('run');
});

test('applyWinner requests a newly computed evolved route for the selected instance', async t => {
  const route = { instance_id: 'selected', method: 'evolved', total_distance: 321, drivers: [] };
  t.mock.method(global, 'fetch', async (url, options) => {
    assert.equal(url, '/api/routing/solve');
    assert.deepEqual(JSON.parse(options.body), { instance_id: 'selected', method: 'evolved', run_id: 'winner' });
    return ok(route);
  });
  assert.deepEqual(await api.applyWinner('winner', 'selected'), route);
});

test('network and structured validation failures are readable', async t => {
  t.mock.method(global, 'fetch', async () => { throw new TypeError('offline'); });
  await assert.rejects(api.healthCheck(), /Cannot reach the backend/);
  global.fetch = async () => ({ ok: false, status: 422, json: async () => ({ detail: [{ msg: 'Invalid coordinate' }] }) });
  await assert.rejects(api.healthCheck(), /Invalid coordinate/);
});

test('polling retries errors and stops on a terminal state', async t => {
  const queued = [], errors = [], updates = [];
  t.mock.method(global, 'setTimeout', fn => { queued.push(fn); return queued.length; });
  t.mock.method(global, 'clearTimeout', () => {});
  let calls = 0;
  t.mock.method(api, 'getEvolutionProgress', async () => {
    if (++calls === 1) throw new Error('temporary failure');
    return { run_id: 'run', status: calls === 2 ? 'running' : 'completed' };
  });
  const stop = watchEvolution('run', p => updates.push(p), e => errors.push(e));
  await flush();
  assert.equal(errors.length, 1);
  await queued.shift()();
  assert.equal(updates[0].status, 'running');
  await queued.shift()();
  assert.equal(updates[1].status, 'completed');
  assert.equal(queued.length, 0);
  stop();
});

test('stopped polling rejects late responses from a previous run', async t => {
  let resolve;
  t.mock.method(api, 'getEvolutionProgress', () => new Promise(r => { resolve = r; }));
  const updates = [];
  const stop = watchEvolution('old', p => updates.push(p), () => assert.fail('No stale errors'));
  stop();
  resolve({ run_id: 'old', status: 'completed' });
  await flush();
  assert.deepEqual(updates, []);
});

test('mismatched run identity is never displayed', async t => {
  t.mock.method(global, 'setTimeout', () => 1);
  t.mock.method(global, 'clearTimeout', () => {});
  t.mock.method(api, 'getEvolutionProgress', async () => ({ run_id: 'other', status: 'completed' }));
  const errors = [];
  const stop = watchEvolution('expected', () => assert.fail('Wrong run'), e => errors.push(e));
  await flush();
  assert.match(errors[0], /Unexpected evolution run/);
  stop();
});

test('distance formatter keeps synthetic map units separate from road units', () => {
  assert.equal(formatDistance(1500, 'synthetic'), '1500.00 map units');
  assert.equal(formatDistance(1500, 'road'), '1.50 km');
  assert.equal(formatDistance(150, 'road'), '150 m');
});

test('winner UI distinguishes training, held-out and application', () => {
  const evolution = { run_id: 'run', status: 'completed', generations: [{ generation: 1, best_fitness: 100,
    valid_count: 1, invalid_count: 0, candidates: [{ heuristic_id: 'winner', fitness: 100, is_valid: true, code: '' }] }],
    test_evaluation: { test_instances_count: 2, evolved_avg_distance: 120,
      baselines: [{ algorithm: 'nearest_neighbor', avg_route_distance: 110 }],
      improvement_vs_nn_percent: -9.1, improvement_vs_2opt_percent: -12 }, total_generations: 1 };
  const html = renderToStaticMarkup(React.createElement(EvolutionPanel, { evolution, canApply: true, onApply() {}, onClose() {} }));
  assert.match(html, /Apply final route to this plan/);
  assert.match(html, /Training mean distance \(map units\)/);
  assert.match(html, /Held-out performance/);
  assert.match(html, /9.1% longer/);
  assert.doesNotMatch(html, /9.1% shorter/);
  assert.match(html, /not results for your selected fleet/);
  const failed = renderToStaticMarkup(React.createElement(EvolutionPanel, { evolution: { ...evolution, status: 'failed' }, onClose() {} }));
  assert.doesNotMatch(failed, /Apply final route to this plan|Held-out performance/);
});

test('rendered route metrics retain units and disclose geometry failures', () => {
  const result = { method: 'evolved', total_distance: 1500, longest_route_distance: 1500, computation_time: 1,
    drivers: [{ driver_id: 0, route: [0, 1, 0], distance: 1500, geometry_error: 'offline' }] };
  const instance = { mode: 'synthetic', num_stops: 1, drivers: [{ driver_id: 0, name: 'Driver', color: 'blue' }], stops: [] };
  const render = mode => renderToStaticMarkup(React.createElement(CompactResults, { result, instance: { ...instance, mode }, results: new Map() }));
  assert.match(render('synthetic'), /1500.00 map units/);
  assert.match(render('road'), /1.50 km/);
  assert.match(render('road'), /Road geometry unavailable/);
  const details = renderToStaticMarkup(React.createElement(DriverDetailsPanel, { result, instance, selectedDriverId: null, onDriverSelect() {} }));
  assert.match(details, /1500.00 map units/);
});

test('completed UI shows the server winner when training scores tie', () => {
  const evolution = { status: 'completed', best_heuristic_id: 'server-winner', total_generations: 1,
    generations: [{ generation: 1, best_fitness: 100, valid_count: 2, invalid_count: 0,
      candidates: [
        { heuristic_id: 'first-in-array', fitness: 100, is_valid: true, code: 'first code' },
        { heuristic_id: 'server-winner', fitness: 100, is_valid: true, code: 'winner code' },
      ] }],
  };
  const html = renderToStaticMarkup(React.createElement(EvolutionPanel, { evolution, canApply: true, onClose() {} }));
  const winnerCard = html.match(/aria-label="Validated winner"[\s\S]*?<\/section>/)[0];
  assert.match(winnerCard, /winner code/);
  assert.doesNotMatch(winnerCard, /first code/);
  assert.match(html, /first code/); // Other candidates remain inspectable in history.
});


test('input parsing preserves seed zero and rejects malformed coordinates', () => {
  const { parseSeed, parseCoordinatePair } = require('../src/services/inputs.ts');
  assert.equal(parseSeed('0'), 0);
  for (const seed of ['', '1bad', '-1', '2.5', '4294967296']) assert.equal(parseSeed(seed), null);
  assert.deepEqual(parseCoordinatePair('0', '0'), [0, 0]);
  for (const pair of [[' ', '1'], ['2bad', '1'], ['Infinity', '0'], ['181', '0'], ['0', '-91']]) {
    assert.equal(parseCoordinatePair(...pair), null);
  }
});
