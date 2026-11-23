// Local HTTP serving smoke. Environment-file loading and dependency discovery
// are disabled; no browser is opened (fonts/maps would require external URLs).
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
process.chdir(root); // Match npm run dev's working directory for PostCSS/Tailwind.
const server = await createServer({
  root, configFile: false, envFile: false, plugins: [react()],
  cacheDir: path.resolve(root, '../runs/.phase3-vite-smoke'),
  optimizeDeps: { noDiscovery: true, include: [] },
  server: { host: '127.0.0.1', port: 0, proxy: { '/api': `http://127.0.0.1:${Number(process.argv[2])}` } },
  logLevel: 'error',
});
let passed = 0;
try {
  await server.listen();
  const base = `http://127.0.0.1:${server.httpServer.address().port}`;
  const request = async (url, body) => {
    const response = await fetch(base + url, {
      method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(60000),
    });
    assert.equal(response.status, 200, `${url}: ${response.status}`);
    return response;
  };
  assert.match(await (await request('/')).text(), /RouteIQ/); passed++;
  assert.match(await (await request('/src/App.tsx')).text(), /applyWinner/); passed++;
  assert.equal((await (await request('/api/health')).json()).status, 'ok'); passed++;
  const instance = await (await request('/api/instances', { num_stops: 5, num_drivers: 2, seed: 11 })).json();
  assert.equal(instance.stops.length, 5); passed++;
  for (const method of ['nearest_neighbor', '2opt']) {
    const result = await (await request('/api/routing/solve', { instance_id: instance.instance_id, method })).json();
    assert.ok(result.total_distance > 0); passed++;
  }
  const run = await (await request('/api/evolution/runs', {
    num_stops: 10, num_instances: 3, num_generations: 2,
    candidates_per_generation: 2, elites_kept: 1, mode: 'mock', seed: 42,
  })).json();
  const deadline = Date.now() + 60000;
  let progress;
  do {
    progress = await (await request(`/api/evolution/runs/${run.run_id}`)).json();
    if (['completed', 'failed', 'cancelled'].includes(progress.status)) break;
    assert.ok(Date.now() < deadline, 'Evolution deadline exceeded');
    await new Promise(resolve => setTimeout(resolve, 100));
  } while (true);
  assert.equal(progress.status, 'completed', progress.error || progress.status);
  assert.equal(progress.test_evaluation.test_instances_count, 2); passed++;
  const preview = await (await request('/api/routing/solve', {
    instance_id: instance.instance_id, method: 'evolved', run_id: run.run_id, preview: true,
  })).json();
  assert.equal(preview.run_id, run.run_id);
  assert.ok(preview.total_distance <= preview.optimization.best_baseline_distance);
  assert.equal((await (await request(`/api/results/${instance.instance_id}/comparison`)).json()).comparisons.length, 2); passed++;
  const evolved = await (await request('/api/routing/solve', {
    instance_id: instance.instance_id, method: 'evolved', run_id: run.run_id,
  })).json();
  assert.equal(evolved.instance_id, instance.instance_id);
  assert.equal(evolved.total_distance, preview.total_distance);
  assert.ok(evolved.total_distance <= evolved.optimization.best_baseline_distance);
  assert.deepEqual(evolved.drivers.flatMap(d => d.route.filter(s => s !== 0)).sort((a, b) => a - b), [1, 2, 3, 4, 5]); passed++;
  const comparisons = await (await request(`/api/results/${instance.instance_id}/comparison`)).json();
  assert.equal(comparisons.comparisons.length, 3); passed++;
  const failed = await (await request('/api/routing/solve', {
    instance_id: instance.instance_id, method: 'evolved', heuristic_code: 'def score_candidates(context): return {}',
  })).json();
  assert.equal(failed.optimization.raw_evolved_distance, null);
  assert.ok(failed.optimization.errors.raw_evolved);
  assert.ok(failed.optimization.baseline_retained);
  assert.equal(failed.total_distance, failed.optimization.best_baseline_distance); passed++;
  console.log(`Local Vite/Uvicorn smoke: ${passed} passed, 0 failed`);
} finally {
  await server.close();
}
