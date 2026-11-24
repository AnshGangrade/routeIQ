// Real Chromium and real local API/solver; road service responses are fixtures. External requests
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
const output = path.resolve(root, '../runs/strategy-experiments-refinement/product-browser');
mkdirSync(output, { recursive: true });
const profile = mkdtempSync(path.join(output, 'browser-'));
const executable = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Google/Chrome/Application/chrome.exe'].find(existsSync);
assert.ok(executable, 'A locally installed Chromium browser is required');
const server = await createServer({ root, configFile: false, envFile: false, plugins: [react()],
  cacheDir: path.join(output, 'vite-cache'), optimizeDeps: { noDiscovery: true, include: ['react', 'react-dom/client', 'react/jsx-runtime', 'react-leaflet', 'leaflet'] },
  server: { host: '127.0.0.1', port: 0, proxy: { '/api': `http://127.0.0.1:${Number(process.argv[2])}` } }, logLevel: 'error' });
let browser, socket, send;
const requests = [], blocked = [], errors = [], checks = [];
let cancelledInterceptions = 0;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let acceptDialog = true;
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
    if (message.method === 'Page.javascriptDialogOpening') await send('Page.handleJavaScriptDialog', { accept: acceptDialog });
    if (message.method === 'Runtime.bindingCalled' && message.params.name === 'routeiqConfirm' && acceptDialog !== null) await send('Runtime.evaluate', { expression: `document.querySelector('dialog[open] ${acceptDialog ? '[data-confirm]' : 'button:not([data-confirm])'}')?.click()` });
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text + ': ' + (message.params.exceptionDetails.exception?.description || ''));
    if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params;
      try {
        if (!request.url.startsWith(base + '/')) { blocked.push(request.url); await send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }); }
        else { if (new URL(request.url).pathname.startsWith('/api/')) requests.push({pathname: new URL(request.url).pathname, body: request.postData ? JSON.parse(request.postData) : null}); await send('Fetch.continueRequest', { requestId }); }
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
  const waitFor = async expression => { for (let i = 0; i < 600; i++) { if (await evaluate(expression)) return; await delay(100); } throw new Error(`UI wait failed: ${expression}`); };
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
  const screenshot = async (name, fromTop = true) => { if (fromTop) await evaluate('window.scrollTo(0,0)'); await delay(200); const { data } = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }); writeFileSync(path.join(output, name + '.png'), Buffer.from(data, 'base64')); };
  const check = name => { checks.push(name); console.log('PASS ' + name); };
  const responsive = async name => {
    for (const width of [390,768,1280]) {
      await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false}); await delay(100);
      assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,`${name} page overflow at ${width}`);
      assert.equal(await evaluate('document.querySelector("nav").scrollWidth<=document.querySelector("nav").clientWidth'),true,`${name} navigation overflow at ${width}`);
      if(name==='lab') assert.ok(await evaluate(`document.querySelector('.experiment-choices .choice-card>span').getBoundingClientRect().width>180`),'Experiment choice text must use the card width');
      await screenshot(`${name}-${width}`);
    }
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    check(`${name} fits phone, tablet and laptop widths`);
  };

  const json = async (url, body) => {
    const response = await fetch(base + url, {method: body ? 'POST' : 'GET', headers: {'Content-Type':'application/json'}, body: body ? JSON.stringify(body) : undefined});
    assert.ok(response.ok, `${url}: ${response.status}`); return response.json();
  };
  const latestInstance = () => requests.filter(r=>r.pathname==='/api/instances').at(-1);
  const latestJob = async () => {
    const id = await evaluate(`document.querySelector('.instance-id')?.title`);
    const comparison = await json(`/api/results/${id}/comparison`);
    return {id,comparison};
  };
  assert.equal((await json('/api/health')).status,'ok'); check('Actual backend health and Vite proxy respond');
  await send('Page.navigate', {url:base});
  await waitFor(`document.querySelector('h1')?.textContent.includes('clearer path')`);
  // Vite may reload once after its initial dependency optimization.
  await delay(1500); await evaluate('document.fonts.ready'); await waitFor(`document.querySelector('h1')?.textContent.includes('clearer path')`);
  await screenshot('01-home'); await responsive('home'); check('Beginner home renders without configuration');
  await click('Create route plan'); await click('Continue');
  await fill(labelInput('Delivery stops'),5); await click('Reproducibility options','summary'); await fillLabel('Random seed',0);
  await click('Continue'); await fillLabel('Number of drivers',7); await fillLabel('Workload policy','fixed');
  await click('Home','nav a'); await click('Route Plan','nav a');
  assert.equal(await evaluate(`document.querySelector('input[type=number]').value`),'7');
  await click('Continue'); await screenshot('02-setup'); await responsive('setup'); await click('Generate routes');
  await waitFor(`document.querySelector('.route-summary')?.textContent.includes('map units')`);
  assert.equal(latestInstance().body.seed,0); assert.deepEqual(latestInstance().body.workload.minimum_stops,[1,1,1,1,1,0,0]);
  assert.equal(await evaluate(`document.querySelectorAll('.driver-select').length`),7);
  await evaluate(`document.querySelectorAll('.driver-select')[6].click()`);
  assert.equal(await evaluate(`document.querySelectorAll('.driver-itinerary li').length`),2);
  check('Real baseline routes support fixed workload, seed zero and empty drivers');
  await click('Search budget and reproducibility','summary'); await fillLabel('Operation limit',30000); await fillLabel('Solver time limit (seconds)',5);
  for (const [name,method] of [['Constructor portfolio','portfolio'],['Hybrid VND','vnd'],['Hybrid VND + ILS','vnd_ils']]) {
    await click(`Run ${name}`);
    await waitFor(`document.querySelector('.map-panel select')?.value===${JSON.stringify(method)} && !document.querySelector('.optimizer button:disabled')`);
    const {comparison} = await latestJob(); const row=comparison.comparisons.find(r=>r.method===method);
    assert.ok(row && row.feasible); assert.equal(row.matrix_fingerprint,comparison.matrix_fingerprint);
    assert.ok(['completed','incomplete'].includes(row.execution.status));
  }
  await screenshot('03-routes'); await responsive('routes'); check('All three hybrid methods run through the real API on the same matrix');
  await click('Compare','nav a'); await waitFor(`document.querySelectorAll('.comparison-table .badge').length===5`);
  const beforePreset=requests.filter(r=>r.pathname==='/api/optimization/jobs').length;
  await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Run route comparison').click(); [...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Run route comparison').click()`);
  await click('Home','nav a'); await click('Compare','nav a');
  await waitFor(`document.querySelector('.compare-screen')?.textContent.includes('Comparison complete.')`);
  assert.equal(requests.filter(r=>r.pathname==='/api/optimization/jobs').length,beforePreset+1);
  assert.equal(requests.filter(r=>r.pathname==='/api/optimization/jobs').at(-1).body.method,'portfolio');
  check('One-click comparison ignores repeated clicks and survives navigation with one scoped portfolio job');
  await screenshot('04-comparison'); await responsive('compare'); check('Comparison includes actual work, feasibility and termination for measured methods');
  await click('Strategy Experiments','nav a');
  const beforeAI=requests.filter(r=>r.pathname==='/api/strategy-experiments').length;
  await evaluate(`document.querySelectorAll('input[name="experiment-choice"]')[1].click()`);
  await waitFor(`document.querySelector('.strategy-lab [role="status"]')?.textContent.includes('Ollama unavailable')`);
  assert.equal(await evaluate(`document.querySelector('.strategy-lab button[type="submit"]').disabled`),true);
  assert.equal(await evaluate(`document.querySelectorAll('.lab-tabs,.legacy-lab').length`),0);
  assert.equal(await evaluate(`document.querySelectorAll('nav a[href="#lab"]').length`),1);
  assert.equal(requests.filter(r=>r.pathname==='/api/strategy-experiments').length,beforeAI);
  await evaluate(`document.querySelectorAll('input[name="experiment-choice"]')[0].click()`);
  check('Unavailable Ollama prevents AI job creation; quick non-LLM choice remains available');
  await click('Run experiment');
  await waitFor(`!!document.querySelector('[aria-label="Strategy experiment progress"]')`);
  await click('Cancel strategy experiment');
  await waitFor(`document.querySelector('[aria-label="Strategy experiment progress"] h2')?.textContent==='cancelled'`);
  check('Real strategy experiment cancellation reaches a terminal state');
  await screenshot('11-experiment-choices');
  await click('Run experiment');
  await waitFor(`!!document.querySelector('[aria-label="Strategy Experiments"] .winner-card button:not(:disabled)')`);
  assert.equal(requests.filter(r=>r.pathname==='/api/strategy-experiments').at(-1).body.arm,'random');
  assert.equal(requests.filter(r=>r.pathname==='/api/strategy-experiments').at(-1).body.mode,'offline');
  await evaluate(`document.querySelector('.strategy-progress').scrollIntoView({block:'start'})`);
  await screenshot('12-quick-result',false);
  check('Quick non-LLM experiment completes with eligible development evidence using defaults');

  await fillLabel('Search control','hand'); await click('Advanced experiment settings','summary'); await fillLabel('Generations',1);
  await click('Run experiment');
  await waitFor(`!!document.querySelector('[aria-label="Strategy Experiments"] .winner-card button:not(:disabled)')`);
  const firstStrategy = requests.filter(r=>r.pathname==='/api/strategy-experiments').at(-1);
  assert.equal(firstStrategy.body.arm,'hand'); assert.equal(firstStrategy.body.mode,'offline');
  assert.match(await evaluate(`document.querySelector('[aria-label="Strategy Experiments"]').textContent`),/Hand-authored/);
  await click('Home','nav a'); await click('Strategy Experiments','nav a');
  assert.ok(await evaluate(`!!document.querySelector('[aria-label="Strategy Experiments"] .winner-card')`));
  await screenshot('05-strategy-lab'); await responsive('lab'); check('Real Phase 6 hand control evaluates, exposes history and survives navigation');
  await evaluate(`document.querySelector('[aria-label="Strategy experiment progress"]').scrollIntoView({block:'start'})`);
  await screenshot('05b-strategy-evidence', false);
  await click('Apply strategy to current plan'); await waitFor(`document.querySelector('.map-panel select')?.value==='strategy'`);
  const first = await latestJob(); const firstApplied=first.comparison.comparisons.find(r=>r.method==='strategy');
  assert.equal(firstApplied.feasible,true); assert.ok(firstApplied.execution.strategy_fingerprint);
  check('Validated strategy recomputes an actual current-plan result');
  await click('Edit plan'); await click('Continue'); await fill(labelInput('Delivery stops'),200);
  await click('Continue'); await click('Continue');
  acceptDialog=null;
  await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Generate routes').focus()`);
  await click('Generate routes'); await waitFor(`!!document.querySelector('dialog[open]')`);
  assert.equal(await evaluate(`document.activeElement.textContent.trim()`),'Keep current plan');
  await screenshot('confirmation-keyboard');
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  assert.equal(await evaluate(`document.activeElement.hasAttribute('data-confirm')`),true);
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await waitFor(`!document.querySelector('dialog[open]')`);
  assert.equal(await evaluate(`document.activeElement.textContent.trim()`),'Generate routes');
  assert.equal(requests.filter(r=>r.pathname==='/api/instances').length,1);
  check('Confirmation supports keyboard focus, Escape cancellation and focus restoration');
  acceptDialog=false; await click('Generate routes');
  assert.equal(await evaluate(`!!document.querySelector('.wizard-panel')`),true);
  assert.equal(requests.filter(r=>r.pathname==='/api/instances').length,1);
  acceptDialog=true; await click('Generate routes'); await waitFor(`document.querySelector('.context-bar')?.textContent.includes('200 stops') && !!document.querySelector('.route-summary')`);
  check('Replacing a plan requires confirmation and creates a separate instance');
  await click('Search budget and reproducibility','summary'); await fillLabel('Operation limit',500000); await fillLabel('Solver time limit (seconds)',30);
  await click('Run Hybrid VND + ILS'); await waitFor(`!!document.querySelector('.optimizer .busy')`);
  await click('Cancel optimization'); await waitFor(`document.querySelector('.optimizer')?.textContent.includes('Optimization cancelled')`);
  assert.notEqual(await evaluate(`document.querySelector('.map-panel select').value`),'vnd_ils');
  check('Real optimization cancellation preserves the previous selected routes');
  await fillLabel('Operation limit',0); await fillLabel('Solver time limit (seconds)',0);
  await click('Strategy Experiments','nav a'); await click('Apply strategy to current plan');
  await waitFor(`document.querySelector('.map-panel select')?.value==='strategy'`);
  const second=await latestJob(); const secondApplied=second.comparison.comparisons.find(r=>r.method==='strategy');
  assert.notEqual(second.id,first.id); assert.notEqual(secondApplied.matrix_fingerprint,firstApplied.matrix_fingerprint);
  assert.equal(secondApplied.execution.strategy_fingerprint,firstApplied.execution.strategy_fingerprint);
  assert.equal(secondApplied.execution.operations,0); assert.equal(secondApplied.execution.status,'incomplete');
  assert.equal(secondApplied.drivers.reduce((n,d)=>n+d.route.length-2,0),200);
  check('Same strategy recomputes another instance; zero-budget result is explicitly incomplete');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await click('Compare','nav a'); await waitFor(`document.querySelectorAll('.comparison-table .badge').length===3 && !document.body.textContent.includes('Loading comparisons...')`);
  assert.equal(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),true); await screenshot('06-comparison-mobile');
  await click('Strategy Experiments','nav a'); assert.equal(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),true); await screenshot('07-lab-mobile');
  check('Comparison and strategy lab fit a 390-pixel viewport');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await click('Route Plan','nav a'); await click('Edit plan'); await evaluate(`document.querySelectorAll('input[name="route-mode"]')[1].click()`); await click('Continue');
  await fill(labelInput('Delivery stops'),5);
  assert.match(await evaluate('document.body.textContent'),/no depot selected/);
  assert.equal(await evaluate(`document.querySelectorAll('.leaflet-marker-icon').length`),0);
  await send('Browser.grantPermissions',{origin:base,permissions:['geolocation']});
  await send('Emulation.setGeolocationOverride',{latitude:10,longitude:20,accuracy:5});
  await click('Use my current location'); await waitFor(`document.querySelectorAll('.leaflet-marker-icon').length===1`);
  await click('Add Stops');
  await evaluate(`document.querySelector('.leaflet-container').scrollIntoView({block:'center'})`); await delay(200);
  const mapRect=await evaluate(`(() => {const r=document.querySelector('.leaflet-container').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
  for(const [dx,dy] of [[-70,-40],[80,-50],[-90,60],[80,70],[0,100]]) {
    await send('Input.dispatchMouseEvent',{type:'mousePressed',x:mapRect.x+dx,y:mapRect.y+dy,button:'left',clickCount:1});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:mapRect.x+dx,y:mapRect.y+dy,button:'left',clickCount:1}); await delay(100);
  }
  await waitFor(`document.querySelectorAll('.leaflet-marker-icon').length===6`);
  await click('Cancel');
  await evaluate(`document.querySelector('[aria-label="Original map colors"]').click()`);
  assert.equal(await evaluate(`document.querySelector('.leaflet-container').classList.contains('map-natural')`),true);
  await evaluate(`document.querySelector('[aria-label="Original map colors"]').click(); document.querySelector('[aria-label="Fit selected locations"]').click()`);
  assert.equal(await evaluate(`document.querySelectorAll('.leaflet-marker-icon').length`),6);
  check('Map color and fit controls preserve actual placed locations');
  // Drag an actual Leaflet stop, then independently inspect its coordinate input.
  await fillLabel('How to add stops','manual'); const beforeMove=await evaluate(`document.querySelector('#lon-0').value`);
  await fillLabel('How to add stops','map');
  await evaluate(`document.querySelector('.leaflet-container').scrollIntoView({block:'center'})`); await delay(200);
  const marker=await evaluate(`(() => {const r=document.querySelector('[title="Delivery stop 1"]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',...marker});
  await send('Input.dispatchMouseEvent',{type:'mousePressed',...marker,button:'left',clickCount:1});
  for(let i=1;i<=5;i++) await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:marker.x+i*8,y:marker.y+i*4,button:'left',buttons:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:marker.x+40,y:marker.y+20,button:'left',clickCount:1});
  await fillLabel('How to add stops','manual');
  assert.notEqual(await evaluate(`document.querySelector('#lon-0').value`),beforeMove);
  acceptDialog=false; await evaluate(`document.querySelector('[aria-label="Remove stop 5"]').click()`); await delay(100);
  assert.equal(await evaluate(`document.querySelectorAll('.stop-row').length`),5);
  acceptDialog=true; await evaluate(`document.querySelector('[aria-label="Remove stop 5"]').click()`); await delay(100);
  assert.equal(await evaluate(`document.querySelectorAll('.stop-row').length`),4);
  await click('Add stop'); await fill('#lon-4',20.01); await fill('#lat-4',10.01);
  check('No default depot; explicit location, map placement, dragging and confirmed removal work');
  await click('Continue'); await fillLabel('Number of drivers',2); await click('Continue');
  await waitFor(`document.querySelectorAll('.review-map .leaflet-marker-icon').length===6`);
  assert.equal(await evaluate(`!!document.querySelector('.review-map .leaflet-marker-draggable')`),false);
  await screenshot('08-road-location-review'); check('Road locations are previewed before route calculation');
  await click('Generate routes'); await waitFor(`document.querySelector('.route-summary')?.textContent.includes('m') && !!document.querySelector('.road-map')`);
  await waitFor(`document.body.textContent.includes('Road geometry unavailable')`);
  const road=await latestJob();
  // The backend stores both historical methods. One driver has unavailable geometry.
  for(const row of road.comparison.comparisons) {
    assert.equal(row.distance_units,'meters'); assert.ok(row.drivers.some(d=>d.geometry_error));
    assert.ok(row.drivers.some(d=>d.geometry?.length>2));
  }
  assert.equal(await evaluate(`document.querySelectorAll('.road-map path.leaflet-interactive').length`),1);
  assert.equal(await evaluate(`document.querySelectorAll('.road-map path[stroke-dasharray]').length`),0);
  await evaluate(`document.querySelectorAll('.driver-select')[1].click()`); await screenshot('09-road-routes-offline-fixtures');
  check('Returned geometry is rendered, unavailable paths stay absent, and road matrix units remain correct');
  await click('Strategy Experiments','nav a'); await fillLabel('Search control','llm'); await fillLabel('Generations',2);
  assert.equal(await evaluate(`document.querySelector('[aria-label="Strategy Experiments"] select')?.value`),'llm');
  await click('Run experiment');
  await waitFor(`!!document.querySelector('[aria-label="Strategy Experiments"] .winner-card button:not(:disabled)')`);
  const proposalRun = requests.filter(r=>r.pathname==='/api/strategy-experiments').at(-1);
  assert.equal(proposalRun.body.mode,'offline'); assert.equal(proposalRun.body.arm,'llm');
  assert.match(await evaluate(`document.querySelector('[aria-label="Strategy Experiments"]').textContent`),/Offline fixture \(not an LLM\)/);
  assert.match(await evaluate(`document.querySelector('[aria-label="Strategy Experiments"]').textContent`),/Mutation|Crossover/);
  check('Offline proposal fixtures and deterministic offspring are labeled separately from live LLM reasoning');
  await evaluate(`document.querySelector('.research-details').open=true; document.querySelector('.lineage-panel').open=true; document.querySelector('.candidate-comparison').open=true; document.querySelector('.research-observatory').scrollIntoView({block:'start'})`);
  assert.ok(await evaluate(`document.querySelectorAll('.lineage-scroll svg path').length>0`));
  assert.ok(await evaluate(`document.querySelectorAll('.candidate-comparison tbody tr').length>0`));
  await screenshot('10-research-evidence',false);
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('.button')).transitionDuration`),'0s');
  check('Recorded lineage and candidate measurements render; reduced motion is honored');
  assert.deepEqual(errors,[]); check('No browser runtime exceptions');
  writeFileSync(path.join(output,'results.json'),JSON.stringify({checks,failures:[],blockedExternalRequests:blocked.length,roadService:'explicit offline fixtures',actualBackend:true},null,2));
  console.log(`Redesign real-backend browser: ${checks.length} passed, 0 failed; external requests blocked: ${blocked.length}`);
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
