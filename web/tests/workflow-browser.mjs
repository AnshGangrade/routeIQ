// Real Chromium interaction tests with mocked API responses. External requests
// are blocked before navigation. Vite explicitly disables environment files.
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
process.chdir(root);
const output = path.resolve(root, '../runs/phase8/legacy-browser');
mkdirSync(output, { recursive: true });
const profile = mkdtempSync(path.join(output, 'browser-'));
const executable = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Google/Chrome/Application/chrome.exe'].find(existsSync);
assert.ok(executable, 'A locally installed Chromium browser is required');
const server = await createServer({ root, configFile: false, envFile: false, plugins: [react()],
  cacheDir: path.join(output, 'vite-cache'), optimizeDeps: { noDiscovery: true, include: ['react', 'react-dom/client', 'react/jsx-runtime', 'react-leaflet', 'leaflet'] },
  server: { host: '127.0.0.1', port: 0 }, logLevel: 'error' });
let browser, socket, send;
const requests = [], blocked = [], errors = [], checks = [];
let cancelledInterceptions = 0;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const instances = new Map(), routes = new Map(), runs = new Map();
let runNumber = 0, holdRun = true, pollFailures = 1, roadFailure = false, partialFailure = false;
function apiResponse(url, request) {
  const pathname = new URL(url).pathname;
  const body = request.postData ? JSON.parse(request.postData) : null;
  requests.push({ pathname, body });
  if (pathname === '/api/instances') {
    if (body.mode === 'road' && roadFailure) return [503, { detail: 'Road routing service unavailable' }];
    const instance_id = `plan-${instances.size + 1}`;
    const instance = { ...body, instance_id, depot: body.mode === 'road' ? { lon: body.depot_coords[0], lat: body.depot_coords[1] } : { x: 50, y: 50 },
      drivers: Array.from({ length: body.num_drivers }, (_, i) => ({ driver_id: i, name: `Driver ${i + 1}`, color: ['#2563eb', '#b86039', '#25826e'][i % 3], assigned_stops: [] })),
      stops: Array.from({ length: body.num_stops }, (_, i) => ({ stop_id: i + 1, x: body.stop_coords?.[i][0] ?? 50 + 40 * Math.cos(i), y: body.stop_coords?.[i][1] ?? 50 + 40 * Math.sin(i) })) };
    instances.set(instance_id, instance); return [200, instance];
  }
  if (pathname === '/api/routing/solve') {
    if (partialFailure && body.method === '2opt') return [503, { detail: 'Refinement temporarily unavailable' }];
    const instance = instances.get(body.instance_id);
    assert.ok(instance, 'Routing must target an existing selected instance');
    if (body.method === 'evolved') assert.equal(runs.get(body.run_id).status, 'completed');
    const distance = { nearest_neighbor: 100, '2opt': 80, evolved: 80 }[body.method];
    const result = { instance_id: body.instance_id, method: body.method, total_distance: distance, longest_route_distance: distance / instance.num_drivers, computation_time: .1,
      drivers: instance.drivers.map(driver => ({ driver_id: driver.driver_id, route: [0, ...instance.stops.filter((_, i) => i % instance.num_drivers === driver.driver_id).map(s => s.stop_id), 0], distance: distance / instance.num_drivers, geometry: null, geometry_error: instance.mode === 'road' ? 'Offline geometry fixture' : null })) };
    if (body.method === 'evolved') Object.assign(result, { run_id: body.run_id, optimization: { nearest_neighbor_distance: 100, two_opt_distance: 80, best_baseline_distance: 80, raw_evolved_distance: 90, refined_evolved_distance: null, selected_source: '2opt', baseline_retained: true, improvement_percent: 0, errors: {} } });
    if (!body.preview) routes.set(body.instance_id + ':' + body.method, result); return [200, result];
  }
  if (pathname.endsWith('/comparison')) {
    const id = pathname.split('/')[3], instance = instances.get(id);
    return [200, { instance_id: id, num_stops: instance.num_stops, num_drivers: instance.num_drivers, comparisons: [...routes.values()].filter(r => r.instance_id === id) }];
  }
  if (pathname === '/api/evolution/runs') {
    const run_id = `run-${++runNumber}`;
    runs.set(run_id, { run_id, status: 'running', stage: 'evaluating_candidates', current_generation: 1, total_generations: body.num_generations, candidates_done: 1, candidates_per_generation: body.candidates_per_generation, generations: [], best_heuristic_id: null, error: null });
    return [200, { run_id, status: 'pending', message: 'Started fixture run' }];
  }
  if (pathname.includes('/api/evolution/runs/')) {
    const id = pathname.split('/')[4], run = runs.get(id);
    assert.ok(run, 'Polling/cancellation must reference an existing run');
    if (pathname.endsWith('/cancel')) { run.status = 'cancelling'; return [200, { run_id: id, status: 'cancelling' }]; }
    if (pollFailures-- > 0) return [503, { detail: 'Temporary polling failure' }];
    if (run.status === 'cancelling') run.status = 'cancelled';
    if (!holdRun && run.status === 'running') Object.assign(run, { status: 'completed', stage: 'completed', best_heuristic_id: 'winner', current_generation: run.total_generations,
      generations: [{ generation: 1, best_fitness: 100, valid_count: 1, invalid_count: 0, candidates: [{ heuristic_id: 'winner', is_valid: true, fitness: 100, code: 'def score_candidates(context): return {"scores": {}}', rationale: 'Test fixture strategy' }] }],
      test_evaluation: { test_instances_count: 2, evolved_avg_distance: 120, baselines: [{ algorithm: 'nearest_neighbor', avg_route_distance: 110 }, { algorithm: 'two_opt', avg_route_distance: 100 }], improvement_vs_nn_percent: -9.1, improvement_vs_2opt_percent: -20 } });
    return [200, run];
  }
  return [404, { detail: 'Unknown fixture endpoint' }];
}

try {
  await server.listen();
  const base = `http://127.0.0.1:${server.httpServer.address().port}`;
  browser = spawn(executable, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-component-update', '--disable-sync', '--disable-default-apps', '--disable-extensions', '--disable-gpu', '--disable-features=MediaRouter', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1', 'about:blank'], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
  let launchErrors = '';
  browser.stderr.on('data', chunk => { launchErrors += chunk.toString(); });
  const portFile = path.join(profile, 'DevToolsActivePort');
  for (let i = 0; !existsSync(portFile) && i < 100; i++) await delay(100);
  if (!existsSync(portFile)) throw new Error(`Headless browser did not start (exit ${browser.exitCode}): ${launchErrors}`);
  const port = Number(readFileSync(portFile, 'utf8').split('\n')[0]);
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }));
  let counter = 0;
  const pending = new Map();
  send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++counter, timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 15000);
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }));
  });
  socket.addEventListener('message', async event => {
    const message = JSON.parse(event.data);
    if (message.id) { const operation = pending.get(message.id); if (!operation) return; clearTimeout(operation.timer); pending.delete(message.id); if (message.error) operation.reject(new Error(message.error.message)); else operation.resolve(message.result); }
    if (message.method === 'Page.javascriptDialogOpening') await send('Page.handleJavaScriptDialog', { accept: true });
    if (message.method === 'Runtime.bindingCalled' && message.params.name === 'routeiqConfirm') await send('Runtime.evaluate', { expression: `document.querySelector('dialog[open] ${true ? '[data-confirm]' : 'button:not([data-confirm])'}')?.click()` });
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text + ': ' + (message.params.exceptionDetails.exception?.description || ''));
    if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params;
      try {
        if (!request.url.startsWith(base + '/')) { blocked.push(request.url); await send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }); }
        else if (new URL(request.url).pathname.startsWith('/api/')) {
          const [responseCode, body] = apiResponse(request.url, request);
          await send('Fetch.fulfillRequest', { requestId, responseCode, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') });
        } else await send('Fetch.continueRequest', { requestId });
      } catch (error) {
        // Navigating away from a Leaflet map cancels pending tile requests;
        // Chromium can retire the interception before our block response lands.
        if (error.message.includes('Invalid InterceptionId')) cancelledInterceptions++;
        else errors.push(error.message);
      }
    }
  });
  await send('Runtime.enable'); await send('Page.enable');
  await send('Runtime.addBinding', { name: 'routeiqConfirm' });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `new MutationObserver(() => {const dialog = document.querySelector('dialog[open]'); if (dialog && !dialog.dataset.automating) {dialog.dataset.automating='yes'; window.routeiqConfirm('confirm');} for (const d of document.querySelectorAll('dialog:not([open])')) delete d.dataset.automating;}).observe(document,{subtree:true,childList:true,attributes:true,attributeFilter:['open']});` });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  const waitFor = async expression => { for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await delay(100); } throw new Error(`UI wait failed: ${expression}`); };
  const click = async (text, selector = 'button,a') => {
    await evaluate(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => { const copy = e.cloneNode(true); copy.querySelectorAll('[aria-hidden="true"]').forEach(n => n.remove()); return copy.textContent.trim() === ${JSON.stringify(text)}; }); if (!el || el.disabled) throw new Error('Unavailable action: ' + ${JSON.stringify(text)}); el.click(); })()`);
    await delay(80);
  };
  const fill = (selector, value) => evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) throw new Error('Missing input'); const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(String(value))}); el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })); })()`);
  const labelInput = label => `input[aria-label=${JSON.stringify(label)}]`;
  const fillLabel = async (text, value) => {
    const selector = await evaluate(`(() => { const label = [...document.querySelectorAll('label')].find(e => e.firstChild?.textContent.trim() === ${JSON.stringify(text)}); const el = label?.querySelector('input,select'); if (!el) throw new Error('Missing label: '+${JSON.stringify(text)}); el.setAttribute('data-fill', 'target'); return '[data-fill="target"]'; })()`);
    await fill(selector, value); await evaluate(`document.querySelector('[data-fill="target"]').removeAttribute('data-fill')`);
  };
  const screenshot = async name => { await delay(200); const { data } = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }); writeFileSync(path.join(output, name + '.png'), Buffer.from(data, 'base64')); };
  const check = name => { checks.push(name); console.log('PASS ' + name); };
  await send('Page.navigate', { url: base });
  await waitFor(`document.querySelector('h1')?.textContent.includes('clearer path')`);
  // A cold Vite dependency pre-bundle can reload after the first render.
  await delay(1500); await evaluate('document.fonts.ready'); await waitFor(`document.querySelector('h1')?.textContent.includes('clearer path')`);
  assert.equal(await evaluate(`!!document.querySelector('input')`), false);
  await screenshot('01-home-desktop'); check('Home offers one clear starting action without configuration');
  await click('Create route plan'); await waitFor(`!!document.querySelector('.stepper')`); await click('Continue');
  await fill(labelInput('Delivery stops'), 7); await click('Reproducibility options', 'summary'); await fillLabel('Random seed', 0); await click('Continue'); await fillLabel('Number of drivers', 3);
  await click('Home', 'nav a'); await click('Route Plan', 'nav a');
  assert.equal(await evaluate(`document.querySelector('input[type=number]').value`), '3');
  await click('Back'); assert.equal(await evaluate(`document.querySelector('input[aria-label="Delivery stops"]').value`), '7'); await click('Continue');
  await fillLabel('Number of drivers', 0); await click('Continue'); await waitFor(`document.querySelector('[role=alert]')?.textContent.includes('1–20')`);
  await fillLabel('Number of drivers', 3); await click('Continue');
  await screenshot('02-setup-review'); check('Wizard preserves inputs across steps/navigation and validates drivers');
  await click('Generate routes'); await waitFor(`document.querySelector('h1')?.textContent.includes('ready to explore')`);
  assert.deepEqual(requests.filter(r => r.pathname === '/api/instances')[0].body, { mode: 'synthetic', num_stops: 7, num_drivers: 3, layout: 'uniform', seed: 0 });
  assert.equal(requests.filter(r => r.pathname === '/api/routing/solve').length, 2);
  assert.match(await evaluate(`document.querySelector('.route-summary').textContent`), /80.00 map units/); check('Generate routes creates one instance and computes both real API methods');
  await evaluate(`document.querySelector('.driver-select').click()`);
  assert.equal(await evaluate(`document.querySelectorAll('.driver-itinerary').length`), 1);
  assert.equal(await evaluate(`document.querySelector('.map-panel button[aria-pressed=true]')?.textContent.trim()`), 'Driver 1');
  await screenshot('03-routes-desktop'); check('Driver selection synchronizes the map and itinerary');
  await click('Compare', 'nav a'); await waitFor(`document.querySelector('.comparison-grid')?.textContent.includes('20.0% shorter')`);
  assert.equal(await evaluate(`!!document.querySelector('.stepper') || !!document.querySelector('.driver-panel')`), false);
  await screenshot('04-comparison'); check('Compare is separate and shows only measured same-plan results');
  await evaluate('history.back()'); await waitFor(`document.querySelector('h1')?.textContent.includes('ready to explore')`);
  await evaluate('history.forward()'); await waitFor(`!!document.querySelector('.comparison-grid')`); check('Browser Back and Forward preserve the selected route plan');
  await click('Evolution Lab', 'nav a'); await click('Legacy heuristic lab');
  assert.equal(await evaluate(`document.querySelector('form details').open`), false);
  assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('.legacy-lab form select option')).map(o => o.textContent)`), ['Live LLM', 'Offline Demo']);
  await fillLabel('Experiment mode', 'live');
  assert.match(await evaluate(`document.querySelector('form').textContent`), /configured provider/);
  await fillLabel('Experiment mode', 'live');
  check('Exactly two experiment modes map to live and mock requests');
  await click('Start experiment'); await waitFor(`document.body.textContent.includes('Progress unavailable')`);
  await waitFor(`document.body.textContent.includes('candidates 1/4')`);
  await click('Route Plan', 'nav a'); assert.equal(await evaluate(`document.querySelector('.context-bar').textContent.includes('running')`), true);
  await click('Evolution Lab', 'nav a'); await click('Cancel evolution'); await waitFor(`document.body.textContent.includes('Evolution cancelled')`);
  assert.equal(requests.find(r => r.pathname.endsWith('/cancel')).pathname, '/api/evolution/runs/run-1/cancel'); check('Polling recovers, progress survives navigation, cancellation reaches terminal state');
  assert.equal(requests.find(r => r.pathname === '/api/evolution/runs').body.mode, 'live');
  holdRun = false;
  await fillLabel('Experiment mode', 'mock');
  await click('Start experiment'); await waitFor(`!!document.querySelector('[aria-label="Validated winner"]')`);
  assert.match(await evaluate(`document.querySelector('[aria-label="Held-out performance"]').textContent`), /9.1% longer/);
  await waitFor(`!!document.querySelector('[aria-label="Current-plan selection"]')`);
  assert.match(await evaluate(`document.querySelector('[aria-label="Current-plan selection"]').textContent`), /Baseline retained/);
  assert.match(await evaluate(`document.querySelector('[aria-label="Current-plan selection"]').textContent`), /12.5% longer/);
  assert.equal(routes.has('plan-1:evolved'), false);
  assert.equal(requests.filter(r => r.pathname === '/api/evolution/runs').at(-1).body.mode, 'mock');
  check('Preview measures the raw loss and baseline fallback without applying it');
  await screenshot('05-evolution-lab');
  await click('Apply final route to this plan'); await waitFor(`document.querySelector('.route-summary')?.textContent.includes('80.00 map units')`);
  const application = requests.filter(r => r.pathname === '/api/routing/solve').at(-1).body;
  assert.deepEqual(application, { instance_id: 'plan-1', method: 'evolved', run_id: 'run-2' });
  await click('Compare', 'nav a'); await waitFor(`document.querySelector('.comparison-grid')?.textContent.includes('Baseline retained')`); check('Winner application targets the selected instance and displays recomputed fleet results');
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
  await screenshot('06-comparison-mobile');
  assert.equal(await evaluate(`document.documentElement.scrollWidth <= window.innerWidth`), true); check('Small viewport comparison has no horizontal page overflow');
  assert.equal(await evaluate(`document.querySelector('nav').scrollWidth <= document.querySelector('nav').clientWidth`), true);
  await click('Route Plan', 'nav a'); await click('Edit plan'); await click('Continue');
  assert.equal(await evaluate(`document.querySelector('input[aria-label="Delivery stops"]').value`), '7');
  await screenshot('07-setup-mobile');
  await click('Continue'); await click('Continue'); partialFailure = true;
  await click('Generate routes'); await waitFor(`document.querySelector('[role=alert]')?.textContent.includes('Refinement temporarily unavailable')`);
  assert.match(await evaluate(`document.querySelector('.route-summary').textContent`), /100.00 map units/);
  partialFailure = false; await click('2-Opt'); await waitFor(`document.querySelector('.route-summary')?.textContent.includes('80.00 map units')`); check('Partial routing failures retain usable results and retry successfully');
  await click('Apply evolved winner'); await waitFor(`document.querySelector('.route-summary')?.textContent.includes('80.00 map units')`);
  assert.equal(requests.filter(r => r.pathname === '/api/routing/solve').at(-1).body.instance_id, 'plan-2'); check('Same winner recomputes against a different selected instance');
  assert.equal(blocked.length, 0); check('Synthetic workflow loads no external browser resources');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await click('Edit plan'); await evaluate(`document.querySelectorAll('input[name="route-mode"]')[1].click()`); await click('Continue');
  await fill(labelInput('Delivery stops'), 5); await fillLabel('Depot longitude', 13.4); await fillLabel('Depot latitude', 52.5); await fillLabel('How to add stops', 'manual');
  for (let i = 0; i < 5; i++) { await click('Add stop'); await fill(`#lon-${i}`, 13.41 + i / 1000); await fill(`#lat-${i}`, 52.51 + i / 1000); }
  await fillLabel('How to add stops', 'map'); await waitFor(`document.querySelectorAll('.leaflet-marker-icon').length === 6`);
  await click('Continue'); await click('Back'); assert.equal(await evaluate(`document.querySelectorAll('.leaflet-marker-icon').length`), 6); check('Road map/manual coordinates and markers persist between wizard steps');
  await screenshot('08-road-setup-offline');
  await click('Continue'); await click('Continue'); roadFailure = true; await click('Generate routes');
  await waitFor(`document.querySelector('[role=alert]')?.textContent.includes('Road routing service unavailable')`);
  assert.equal(await evaluate(`!!document.querySelector('.wizard-panel')`), true);
  assert.equal(instances.size, 2); check('Road failure stays explicit and preserves the draft without synthetic fallback');
  roadFailure = false; await click('Generate routes'); await waitFor(`document.querySelector('.route-summary')?.textContent.includes('80 m')`);
  await waitFor(`document.body.textContent.includes('Road geometry unavailable')`); check('Road result uses road units and discloses missing geometry');
  assert.deepEqual(errors, []);
  check('No browser runtime exceptions');
  console.log(`Browser workflow: ${checks.length} passed, 0 failed; external requests blocked: ${blocked.length}`);
  writeFileSync(path.join(output, 'results.json'), JSON.stringify({ checks, failures: [], blockedExternalRequests: blocked.length, cancelledInterceptions }, null, 2));
} catch (error) {
  if (send && socket?.readyState === WebSocket.OPEN) {
    const state = await send('Runtime.evaluate', { expression: 'document.body.innerText.slice(0, 3000)', returnByValue: true });
    console.error('Browser state:', state.result.value, 'Runtime errors:', errors);
    const shot = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(path.join(output, 'failure.png'), Buffer.from(shot.data, 'base64'));
  }
  throw error;
} finally {
  if (send && socket?.readyState === WebSocket.OPEN) { try { await send('Browser.close'); } catch {} socket.close(); }
  if (browser && browser.exitCode === null) browser.kill();
  await server.close();
}
