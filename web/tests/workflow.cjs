// Shared test setup uses only installed TypeScript/React and mocked HTTP.
require('./phase3.cjs');
require('./product.cjs');
require('./visual-design.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { initialPlan, validatePlan, planRequest, generatePlan, differenceText, viewFromHash } = require('../src/services/workflow.ts');
const { api } = require('../src/services/api.ts');
const { CompareScreen } = require('../src/components/CompareScreen.tsx');

test('wizard validates steps, road counts, driver limits and seed zero', () => {
  assert.equal(validatePlan(initialPlan), null);
  assert.equal(planRequest({ ...initialPlan, seed: '0' }).seed, 0);
  assert.equal(planRequest({ ...initialPlan, seed: '' }).seed, undefined);
  assert.equal(validatePlan({ ...initialPlan, numDrivers: 0 }, 1), null);
  assert.match(validatePlan({ ...initialPlan, numDrivers: 0 }, 2), /drivers/);
  const road = { ...initialPlan, mode: 'road', depotLon: '0', depotLat: '52', numStops: 5,
    stops: Array.from({ length: 5 }, () => ({ lon: '0', lat: '52.1' })) };
  assert.equal(validatePlan(road), null);
  assert.deepEqual(planRequest(road).depot_coords, [0, 52]);
  assert.match(validatePlan({ ...road, numStops: 100 }), /5–99/);
  assert.match(validatePlan({ ...road, stops: [] }), /exactly 5/);
  assert.match(validatePlan({ ...road, depotLat: '90bad' }), /depot/);
});

test('generation uses one instance for both methods and retains partial failures', async t => {
  t.mock.method(api, 'createInstance', async request => { assert.equal(request.seed, 0); return { instance_id: 'selected' }; });
  const calls = [];
  t.mock.method(api, 'solveRouting', async request => {
    calls.push(request);
    if (request.method === '2opt') throw new Error('Service unavailable');
    return { instance_id: 'selected', method: request.method, total_distance: 10 };
  });
  const progress = [];
  const result = await generatePlan({ ...initialPlan, seed: '0' }, text => progress.push(text));
  assert.deepEqual(calls.map(c => c.instance_id), ['selected', 'selected']);
  assert.equal(result.results.size, 1);
  assert.match(result.errors[0], /2-Opt: Service unavailable/);
  assert.equal(progress.length, 2);
});

test('failed instance generation never proceeds to solving or reports success', async t => {
  t.mock.method(api, 'createInstance', async () => { throw new Error('Road service unavailable'); });
  const solve = t.mock.method(api, 'solveRouting', () => assert.fail('must not solve failed instance'));
  await assert.rejects(generatePlan(initialPlan, () => {}), /Road service unavailable/);
  assert.equal(solve.mock.callCount(), 0);
});

test('mismatched instance or method results cannot enter the selected plan', async t => {
  t.mock.method(api, 'createInstance', async () => ({ instance_id: 'selected' }));
  t.mock.method(api, 'solveRouting', async () => ({ instance_id: 'wrong', method: '2opt', total_distance: 1 }));
  const result = await generatePlan(initialPlan, () => {});
  assert.equal(result.results.size, 0);
  assert.equal(result.errors.length, 2);
});

test('comparisons describe shorter, longer, equal and undefined outcomes honestly', () => {
  assert.equal(differenceText(80, 100), '20.0% shorter');
  assert.equal(differenceText(120, 100), '20.0% longer');
  assert.equal(differenceText(0, 0), 'Same distance');
  assert.equal(differenceText(99.96, 100), '<0.1% shorter');
  assert.equal(differenceText(100.04, 100), '<0.1% longer');
  assert.equal(differenceText(1, 0), 'Percentage comparison unavailable');
  assert.equal(differenceText(1, undefined), 'Comparison unavailable');
  assert.equal(differenceText(NaN, 1), 'Comparison unavailable');
});

test('comparison screen labels worse measured results and missing evolved routes', () => {
  const instance = { instance_id: 'selected', mode: 'road', num_stops: 5, num_drivers: 2 };
  const comparison = { instance_id: 'selected', comparisons: [
    { method: 'nearest_neighbor', total_distance: 1000, longest_route_distance: 500, computation_time: .1 },
    { method: '2opt', total_distance: 1200, longest_route_distance: 600, computation_time: .1 },
  ] };
  const html = renderToStaticMarkup(React.createElement(CompareScreen, { instance, comparison, loading: false, busy: false, evolution: null }));
  assert.match(html, /20.0% longer/);
  assert.match(html, /1.20 km/);
  assert.match(html, /No measured result for this plan yet/);
  assert.doesNotMatch(html, /20.0% shorter/);
});

test('navigation has explicit destinations and safely handles unknown hashes', () => {
  for (const view of ['home', 'setup', 'routes', 'compare', 'lab']) assert.equal(viewFromHash('#' + view), view);
  assert.equal(viewFromHash('#unknown'), 'home');
});

const { EvolutionLab, initialEvolution } = require('../src/components/EvolutionLab.tsx');
const { PlanSelection } = require('../src/components/PlanSelection.tsx');
for (const mode of ['live', 'mock']) test(`experiment mode ${mode} has honest labels and exactly two choices`, () => {
  const html = renderToStaticMarkup(React.createElement(EvolutionLab, { config: { ...initialEvolution, mode }, setConfig() {}, evolution: null, busy: false, hasInstance: true }));
  assert.equal((html.match(/<option/g) || []).length, 2);
  assert.match(html, /Live LLM/); assert.match(html, /Offline Demo/);
  assert.doesNotMatch(html, /Replay|value="replay"/);
  assert.match(html, mode === 'live' ? /configured provider/ : /Predefined candidates/);
  assert.doesNotMatch(html, /<details open/);
});

test('preview requests current plan and run without applying', async t => {
  t.mock.method(global, 'fetch', async (url, options) => {
    assert.equal(url, '/api/routing/solve');
    assert.deepEqual(JSON.parse(options.body), { instance_id: 'selected', method: 'evolved', run_id: 'winner', preview: true });
    return { ok: true, json: async () => ({ instance_id: 'selected', run_id: 'winner' }) };
  });
  assert.equal((await api.previewWinner('winner', 'selected')).instance_id, 'selected');
});

test('selection exposes raw losses, ties, failures and genuine gains without inventing improvement', () => {
  const selection = { nearest_neighbor_distance: 25000, two_opt_distance: 24210, best_baseline_distance: 24210, raw_evolved_distance: 24750, refined_evolved_distance: null, selected_source: '2opt', baseline_retained: true, improvement_percent: 0, errors: {} };
  const render = (overrides = {}, distance = 24210) => renderToStaticMarkup(React.createElement(PlanSelection, { selection: { ...selection, ...overrides }, distance, mode: 'road' }));
  const loss = render();
  assert.match(loss, /24.75 km/); assert.match(loss, /24.21 km/); assert.match(loss, /2.2% longer/);
  assert.match(loss, /Baseline retained/); assert.match(loss, /Same distance/); assert.doesNotMatch(loss, /Evolution improved/);
  assert.match(render({ raw_evolved_distance: 24210 }), /Same distance/);
  const failure = render({ raw_evolved_distance: null, errors: { raw_evolved: 'Candidate validation or execution failed' } });
  assert.match(failure, /Unavailable/); assert.match(failure, /Candidate validation or execution failed/);
  const gain = render({ baseline_retained: false, selected_source: 'refined_evolved', refined_evolved_distance: 24000 }, 24000);
  assert.match(gain, /Evolution improved this plan/); assert.match(gain, /0.9% shorter/); assert.match(gain, /2.2% longer/);
});
