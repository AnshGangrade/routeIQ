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
const output = path.resolve(root, `../runs/milestone11-20261128/workflow-browser-${Date.now()}`);
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
const strategyJobs=new Map(),optimizationJobs=new Map();
let providerState='unreachable';
let panelComplete=false;
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
    Object.assign(instance,{problem_fingerprint:`problem-${instance_id}`,matrix_fingerprint:`matrix-${instance_id}`,distance_units:body.mode==='road'?'meters':'map_units'});
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
    Object.assign(result,{feasible:true,problem_fingerprint:instance.problem_fingerprint,matrix_fingerprint:instance.matrix_fingerprint,distance_units:instance.distance_units,execution:{status:'completed',termination:'historical_baseline_complete',operations:null,budget_exhausted:false}});
    if (body.method === 'evolved') Object.assign(result, { run_id: body.run_id, optimization: { nearest_neighbor_distance: 100, two_opt_distance: 80, best_baseline_distance: 80, raw_evolved_distance: 90, refined_evolved_distance: null, selected_source: '2opt', baseline_retained: true, improvement_percent: 0, errors: {} } });
    if (!body.preview) routes.set(body.instance_id + ':' + body.method, result); return [200, result];
  }
  if (pathname === '/api/strategy-experiments/provider/check' && providerState==='bad_payload') return [200,{available:true}];
  if (pathname === '/api/strategy-experiments/provider/check') return [200,{configured:true,reachable:['available','model_missing'].includes(providerState),available:providerState==='available',status:providerState,model:body.model,message:providerState==='available'?'Model available':providerState==='model_missing'?'Requested model missing; install it and retry.':providerState==='check_failed'?'Provider check failed; retry.':'Ollama unreachable; start it and retry.'}];
  if (pathname === '/api/strategy-experiments') {
    const job_id=`strategy-${strategyJobs.size+1}`;
    const record={strategy_id:'winner',parents:[],generation:1,creation_method:'llm',rationale:'Mocked browser fixture, not live evidence',config:{construction:'legacy_2opt',operators:['swap']},fitness:{policy:'completed_panel/v1',eligible:panelComplete,mean_distance:panelComplete?100:null,cases:2,expected_cases:2,completed:panelComplete?2:1,incomplete:panelComplete?0:1,failed:0,operations:10,seconds:.1},evaluation_history:[{rows:body.config.case_ids.map((case_id,i)=>({case_id,feasible:true,independently_validated:true,status:panelComplete||i===0?'completed':'incomplete',termination:panelComplete||i===0?'local_search_complete':'operation_budget'}))}]};
    strategyJobs.set(job_id,{job_id,status:'running',generation:1,reserved_evaluations:2,manifest:{arm:body.arm,provider_mode:body.mode,config:{...body.config,proposal_policy:'llm_only'}},proposal_events:[{source:'llm',outcome:'accepted',strategy_id:'winner'}],records:{winner:record},history:[{generation:0,best_so_far:null,unique_configurations:1,behavioral_diversity:1}],best_id:null});
    return [200,{job_id,status:'pending'}];
  }
  if (pathname.startsWith('/api/strategy-experiments/')) {
    const id=pathname.split('/')[3],job=strategyJobs.get(id);assert.ok(job);
    if (pathname.endsWith('/cancel')) {job.status='cancelling';return [200,{job_id:id,status:job.status}];}
    if (pollFailures-- >0) return [503,{detail:'Temporary polling failure'}];
    if(job.status==='cancelling')job.status='cancelled';
    if(!holdRun && job.status==='running'){job.status='completed';job.best_id='winner';}
    return [200,job];
  }
  if(pathname==='/api/optimization/jobs') {
    assert.equal(strategyJobs.get(body.strategy_job_id).status,'completed');
    const job_id=`optimization-${optimizationJobs.size+1}`;
    const original=routes.get(body.instance_id+':2opt');assert.ok(original);
    const result={...original,method:'strategy',feasible:true,execution:{status:'completed',termination:'local_search_complete',search_status:'completed',schedule_completed:true,route_validity:'validated',independently_validated:true}};
    routes.set(body.instance_id+':strategy',result);
    const job={job_id,instance_id:body.instance_id,problem_fingerprint:original.problem_fingerprint,matrix_fingerprint:original.matrix_fingerprint,method:'strategy',status:'completed',result};
    optimizationJobs.set(job_id,job);return [200,job];
  }
  if(pathname.startsWith('/api/optimization/jobs/'))return [200,optimizationJobs.get(pathname.split('/')[4])];
  if (pathname.endsWith('/comparison')) {
    const id = pathname.split('/')[3], instance = instances.get(id);
    return [200, { instance_id: id, problem_fingerprint:instance.problem_fingerprint,matrix_fingerprint:instance.matrix_fingerprint,num_stops: instance.num_stops, num_drivers: instance.num_drivers, comparisons: [...routes.values()].filter(r => r.instance_id === id).map(r=>({...r,server_verified:true})) }];
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
  const screenshot = async name => {
    const previous=await evaluate('[innerWidth,innerHeight]');
    const viewports=[[1440,900],[1280,800],[768,1024],[390,844]];
    for(const [width,height] of viewports) {
      await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await delay(180);
      assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,`${name} overflow at ${width}`);
      assert.equal(await evaluate('document.querySelector("nav").scrollWidth<=document.querySelector("nav").clientWidth'),true,`${name} navigation overflow at ${width}`);
      const {data}=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      writeFileSync(path.join(output,`${name}-${width}.png`),Buffer.from(data,'base64'));
    }
    await send('Emulation.setDeviceMetricsOverride',{width:previous[0],height:previous[1],deviceScaleFactor:1,mobile:false});await delay(100);
  };
  const check = name => { checks.push(name); console.log('PASS ' + name); };
  await send('Page.navigate', { url: base });
  await waitFor(`!!document.querySelector('.home')`);
  // A cold Vite dependency pre-bundle can reload after the first render.
  await delay(1500); await evaluate('document.fonts.ready'); await waitFor(`!!document.querySelector('.home')`);
  assert.equal(await evaluate(`!!document.querySelector('input')`), false);
  await screenshot('01-home-desktop'); check('Home offers one clear starting action without configuration');
  await evaluate(`document.querySelector('.skip-link').focus()`);
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  assert.equal(await evaluate(`document.activeElement.id==='main-content'`),true);
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('.button')).transitionDuration`),'0s');
  await send('Emulation.setEmulatedMedia',{features:[]});
  check('Keyboard skip navigation and reduced-motion preferences work');

  await click('Create route plan'); await waitFor(`!!document.querySelector('.planning-workspace')`);
  await fill(labelInput('Delivery stops'), 7); await click('Reproducibility options', 'summary'); await fillLabel('Random seed', 0);  await fillLabel('Number of drivers', 3);
  await click('Home', 'nav a'); await click('Route Plan', 'nav a');
  assert.equal(await evaluate(`[...document.querySelectorAll('label')].find(l=>l.firstChild?.textContent.trim()==='Number of drivers').querySelector('input').value`), '3');
  await click('Home','nav a');await click('Route Plan','nav a'); assert.equal(await evaluate(`document.querySelector('input[aria-label="Delivery stops"]').value`), '7');
  await fillLabel('Number of drivers', 0); await click('Generate Plan');  await waitFor(`document.querySelector('[role=alert]')?.textContent.includes('1–20')`);
  await fillLabel('Number of drivers', 3);
  await screenshot('02-setup-review'); check('Workspace preserves inputs across navigation and validates drivers');
  await click('Generate Plan'); await waitFor(`!!document.querySelector('.route-summary')`);
  assert.deepEqual(requests.filter(r => r.pathname === '/api/instances')[0].body, { mode: 'synthetic', num_stops: 7, num_drivers: 3, layout: 'uniform', seed: 0 });
  assert.equal(requests.filter(r => r.pathname === '/api/routing/solve').length, 2);
  assert.match(await evaluate(`document.querySelector('.route-summary').textContent`), /80.00 map units/); check('Generate routes creates one instance and computes both real API methods');
  assert.ok(await evaluate(`Math.abs(document.querySelector('.workspace-results').getBoundingClientRect().top-document.querySelector('.planning-scroll').getBoundingClientRect().top)<2`));
  assert.match(await evaluate(`document.querySelector('.route-outcome').textContent`), /Nearest Neighbor \(historical\).*20.00 map units saved.*20.0% shorter/);
  assert.equal(await evaluate(`document.querySelector('.workspace-advanced').open`),false);
  await evaluate(`document.querySelector('.route-explanation button').click()`);
  assert.equal(await evaluate(`document.querySelector('.map-panel button[aria-pressed=true]')?.textContent.trim()`),'Driver 1');
  check('Measured savings name the baseline and explanation focuses its driver while diagnostics stay collapsed');
  await screenshot('03a-measured-route-output');
  await evaluate(`document.querySelector('.driver-select').click()`); // Restore all-driver view before the existing toggle test.
  await evaluate(`document.querySelector('.driver-select').click()`);
  assert.equal(await evaluate(`document.querySelectorAll('.driver-itinerary').length`), 1);
  assert.equal(await evaluate(`document.querySelector('.map-panel button[aria-pressed=true]')?.textContent.trim()`), 'Driver 1');
  await screenshot('03-routes-desktop'); check('Driver selection synchronizes the map and itinerary');
  await evaluate(`document.querySelector('svg [aria-label="Delivery stop 1"]').focus()`);
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  assert.equal(await evaluate(`document.querySelector('svg [aria-label="Delivery stop 1"]').getAttribute('aria-pressed')`),'true');
  check('Synthetic map stops support keyboard selection');

  await click('Compare', 'nav a'); await waitFor(`document.querySelector('.comparison-grid')?.textContent.includes('20.0% shorter')`);
  assert.equal(await evaluate(`!!document.querySelector('.stepper') || !!document.querySelector('.driver-panel')?.getBoundingClientRect().height`), false);
  await screenshot('04-comparison'); check('Compare is separate and shows only measured same-plan results');
  await evaluate('history.back()'); await waitFor(`!!document.querySelector('.route-summary')`);
  await evaluate('history.forward()'); await waitFor(`!!document.querySelector('.comparison-grid')`); check('Browser Back and Forward preserve the selected route plan');
  await click('Evolution','nav a');
  assert.equal(await evaluate(`document.querySelectorAll('.strategy-lab select,.strategy-lab input[type=radio]').length`),0);
  assert.equal(await evaluate(`document.querySelectorAll('.lab-tabs,.legacy-lab').length`),0);
  assert.equal(await evaluate(`document.querySelectorAll('nav a[href="#lab"]').length`),1);
  for(const status of ['unreachable','model_missing','check_failed','bad_payload','available']) {
    providerState=status;await click('Check Ollama');
    await waitFor(`document.querySelector('.strategy-lab [role="status"]')?.textContent.includes(${JSON.stringify(status==='available'?'Model available':status==='model_missing'?'Requested model missing':['check_failed','bad_payload'].includes(status)?'Provider check failed':'Ollama unreachable')})`);
    assert.equal(await evaluate(`document.querySelector('button[type="submit"]').disabled`),status!=='available');
  }
  assert.equal(strategyJobs.size,0);check('One page, no tabs; all provider states gate AI submission without starting a job');
  providerState='unreachable';await click('Run evolution');await waitFor(`document.querySelector('.strategy-lab [role="alert"]')?.textContent.includes('unreachable')`);
  assert.equal(strategyJobs.size,0);assert.equal(await evaluate(`document.querySelector('button[type="submit"]').disabled`),true);
  providerState='available';await click('Check Ollama');await waitFor(`!document.querySelector('button[type="submit"]').disabled`);
  check('Provider disappearing after preflight blocks submission and requires a successful retry');
  await click('Run evolution');await waitFor(`document.body.textContent.includes('Progress unavailable')`);
  await waitFor(`document.querySelector('.strategy-progress h2')?.textContent==='Evaluating strategies' && document.querySelector('.context-bar')?.textContent.includes('running')`);
  await click('Route Plan','nav a');assert.equal(await evaluate(`document.querySelector('.context-bar').textContent.includes('running')`),true);
  await click('Evolution','nav a');await click('Cancel evolution');
  await waitFor(`document.querySelector('.strategy-progress')?.textContent.includes('Evolution was cancelled')`);
  assert.equal(requests.find(r=>r.pathname.endsWith('/cancel')).pathname,'/api/strategy-experiments/strategy-1/cancel');
  check('Polling recovers, progress survives navigation, cancellation reaches terminal state');
  holdRun=false;await click('Run evolution');
  await waitFor(`document.querySelector('.strategy-progress h2')?.textContent==='No fully evaluated strategy was produced' && !document.querySelector('.strategy-progress button')?.textContent.includes('Cancel')`);
  assert.equal(await evaluate(`document.querySelector('.winner-card')===null`),true);
  assert.equal(requests.filter(r=>r.pathname==='/api/strategy-experiments').at(-1).body.mode,'ollama');
  assert.equal(routes.has('plan-1:strategy'),false);
  check('Incomplete candidate has no winner or apply action and never becomes a route result');
  panelComplete=true;await click('Run evolution');await waitFor(`!!document.querySelector('.winner-card button:not(:disabled)')`);
  assert.match(await evaluate(`document.querySelector('.winner-card').textContent`),/2 of 2 cases completed/);
  assert.equal(await evaluate(`document.querySelector('.research-details').open`),false);
  check('Completed full-panel candidate is applicable with diagnostics collapsed');
  await screenshot('05-strategy-experiments-desktop');
  await click('Apply to current plan');await waitFor(`document.querySelector('.map-panel select')?.value==='strategy'`);
  const application=requests.filter(r=>r.pathname==='/api/optimization/jobs').at(-1).body;
  assert.equal(application.instance_id,'plan-1');assert.equal(application.strategy_job_id,'strategy-3');assert.equal(application.strategy_id,'winner');
  await click('Compare','nav a');await waitFor(`document.querySelector('.comparison-grid')?.textContent.includes('80.00 map units')`);
  check('Winner application targets selected instance and displays recomputed fleet results');
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
  await screenshot('06-comparison-mobile');
  assert.equal(await evaluate(`document.documentElement.scrollWidth <= window.innerWidth`), true); check('Small viewport comparison has no horizontal page overflow');
  assert.equal(await evaluate(`document.querySelector('nav').scrollWidth <= document.querySelector('nav').clientWidth`), true);
  await click('Route Plan', 'nav a'); await click('Edit Plan');
  assert.equal(await evaluate(`document.querySelector('input[aria-label="Delivery stops"]').value`), '7');
  await screenshot('07-setup-mobile');
    partialFailure = true;
  await click('Generate Plan'); await waitFor(`document.querySelector('[role=alert]')?.textContent.includes('Refinement temporarily unavailable')`);
  assert.match(await evaluate(`document.querySelector('.route-summary').textContent`), /100.00 map units/);
  partialFailure = false; await click('2-Opt'); await waitFor(`document.querySelector('.route-summary')?.textContent.includes('80.00 map units')`); check('Partial routing failures retain usable results and retry successfully');
  await click('Evolution','nav a');await screenshot('09-strategy-experiments-mobile');await click('Apply to current plan');await waitFor(`document.querySelector('.map-panel select')?.value==='strategy'`);
  assert.equal(requests.filter(r=>r.pathname==='/api/optimization/jobs').at(-1).body.instance_id,'plan-2'); check('Same winner recomputes against a different selected instance');
  assert.equal(blocked.length, 0); check('Synthetic workflow loads no external browser resources');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await click('Edit Plan'); await evaluate(`document.querySelectorAll('input[name="route-mode"]')[1].click()`);
  await fill(labelInput('Delivery stops'), 5); await fillLabel('Depot longitude', 13.4); await fillLabel('Depot latitude', 52.5); await fillLabel('How to add stops', 'manual');
  for (let i = 0; i < 5; i++) { await click('Add stop'); await fill(`#lon-${i}`, 13.41 + i / 1000); await fill(`#lat-${i}`, 52.51 + i / 1000); }
  await fillLabel('How to add stops', 'map'); await waitFor(`document.querySelectorAll('.leaflet-marker-icon').length === 6`);
   await click('Home','nav a');await click('Route Plan','nav a'); assert.equal(await evaluate(`document.querySelectorAll('.leaflet-marker-icon').length`), 6); check('Road map/manual coordinates and markers persist across navigation');
  await screenshot('08-road-setup-offline');
    roadFailure = true; await click('Generate Plan');
  await waitFor(`document.querySelector('[role=alert]')?.textContent.includes('Road routing service unavailable')`);
  assert.equal(await evaluate(`!!document.querySelector('.planning-column')`), true);
  assert.equal(instances.size, 2); check('Road failure stays explicit and preserves the draft without synthetic fallback');
  roadFailure = false; await click('Generate Plan'); await waitFor(`document.querySelector('.route-summary')?.textContent.includes('80 m')`);
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
