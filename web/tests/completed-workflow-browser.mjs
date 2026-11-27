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
const output = path.resolve(process.argv[3]);
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
let limitNextApplication = false;
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
        else {
          const pathname=new URL(request.url).pathname;
          if (pathname.startsWith('/api/')) requests.push({pathname, body:request.postData?JSON.parse(request.postData):null});
          if (limitNextApplication && pathname==='/api/optimization/jobs' && request.method==='POST') {
            limitNextApplication=false;
            const body={...JSON.parse(request.postData),operations:0,seconds:0};
            await send('Fetch.continueRequest',{requestId,postData:Buffer.from(JSON.stringify(body)).toString('base64')});
          } else await send('Fetch.continueRequest',{requestId});
        }
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

  const json = async (url, body) => {
    const response=await fetch(base+url,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
    assert.ok(response.ok,`${url}: ${response.status}`);return response.json();
  };
  const planId=()=>evaluate(`document.querySelector('.instance-id')?.title`);
  const strategyResult=async()=> (await json(`/api/results/${await planId()}/comparison`)).comparisons.find(r=>r.method==='strategy');
  await send('Page.navigate',{url:base});
  await waitFor(`document.querySelector('h1')?.textContent.includes('RouteIQ')`);
  await delay(1500);
  await click('Create route plan');
  await fill(labelInput('Delivery stops'),10);
  await fillLabel('Number of drivers',2);
  await click('Generate Plan');
  await waitFor(`document.querySelector('.route-summary')?.textContent.includes('map units')`);
  const firstPlan=await planId();
  check('Generate Plan returns a completed independently validated baseline');
  await click('Evolution','nav a');
  await waitFor(`document.querySelector('.strategy-config button[type="submit"]')?.disabled===false`);
  assert.equal(await evaluate(`document.querySelectorAll('.strategy-lab select,.strategy-lab input[type="radio"]').length`),0);
  assert.equal(await evaluate(`document.querySelector('.strategy-lab h1').textContent`),'AI-guided strategy');
  await click('Check Ollama');
  await waitFor(`document.querySelector('.strategy-config button[type="submit"]')?.disabled===false`);
  check('Evolution exposes only AI-guided strategy with provider availability checking');
  await click('Run evolution');
  await waitFor(`document.querySelector('.strategy-progress')?.textContent.includes('Evaluating strategies')`);
  await waitFor(`document.querySelector('.winner-card')?.textContent.includes('2 of 2 cases completed')`);
  const start=requests.find(r=>r.pathname==='/api/strategy-experiments' && r.body);
  assert.equal(start.body.workflow,'ai_product');assert.equal(start.body.mode,'ollama');assert.equal(start.body.arm,'llm');
  await screenshot('01-completed-strategy');
  check('Actual engine evaluates mocked LLM proposals and publishes one complete-panel strategy');
  await click('Apply to current plan');
  await waitFor(`location.hash==='#routes' && document.querySelector('select[aria-label="Displayed route method"]')?.value==='strategy' `);
  const firstResult=await strategyResult();
  assert.equal(firstResult.execution.status,'completed');assert.equal(firstResult.execution.independently_validated,true);
  await screenshot('02-applied-route');
  check('Applying recomputes and independently validates selected-instance routes');
  await click('Evolution','nav a');
  limitNextApplication=true;
  await click('Apply to current plan');
  await waitFor(`document.body.innerText.includes('No new completed result was produced')`);
  assert.deepEqual(await strategyResult(),firstResult);
  assert.equal(await evaluate(`document.querySelector('select[aria-label="Displayed route method"]').value==='strategy' `),true);
  await screenshot('03-incomplete-retains-route');
  check('Actual zero-budget application retains previous completed route in UI and backend');
  await click('Edit Plan');
  await fill(labelInput('Delivery stops'),8);
  await click('Generate Plan');
  await waitFor(`document.querySelector('.route-summary')?.textContent.includes('map units')`);
  assert.notEqual(await planId(),firstPlan);
  await click('Evolution','nav a');await click('Apply to current plan');
  await waitFor(`location.hash==='#routes' && document.querySelector('select[aria-label="Displayed route method"]')?.value==='strategy' `);
  const secondResult=await strategyResult();
  assert.notEqual(secondResult.problem_fingerprint,firstResult.problem_fingerprint);
  assert.equal(secondResult.drivers.reduce((n,d)=>n+d.route.length-2,0),8);
  check('Same winner recomputes routes for a different plan and fingerprint');
  await click('Evolution','nav a');await click('Run evolution');
  await waitFor(`document.querySelector('.strategy-progress')?.textContent.includes('Cancel evolution')`);
  await click('Cancel evolution');
  await waitFor(`document.querySelector('.strategy-progress')?.textContent.includes('Evolution was cancelled')`);
  assert.equal(await evaluate(`document.querySelector('.winner-card')===null`),true);
  check('Cancellation reaches terminal state with no applyable winner');
  assert.deepEqual(errors,[]);check('No browser runtime exceptions');
  writeFileSync(path.join(output,'results.json'),JSON.stringify({checks,failures:[],provider:'MockTransport Ollama fixture; not live',actualSolver:true,blockedExternalRequests:blocked.length},null,2));
  console.log(`Completed workflow browser: ${checks.length} passed, 0 failed`);
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
