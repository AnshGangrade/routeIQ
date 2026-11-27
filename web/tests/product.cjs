// Loaded by workflow.cjs after its TypeScript/React test setup.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { validateRouteResult, watchTask } = require('../src/services/product.ts');
const { initialPlan, planRequest, generatePlan } = require('../src/services/workflow.ts');
const { api } = require('../src/services/api.ts');
const { CompareScreen } = require('../src/components/CompareScreen.tsx');
const { StrategyLab } = require('../src/components/StrategyLab.tsx');
const { OptimizationDetails } = require('../src/components/OptimizationDetails.tsx');
const flush = () => new Promise(setImmediate);
const instance = { instance_id: 'plan', problem_fingerprint: 'problem', matrix_fingerprint: 'matrix', distance_units:'map_units', mode: 'synthetic', num_stops: 3, num_drivers: 2,
  stops: [1,2,3].map(stop_id => ({ stop_id })), workload: { minimum_stops: [1,1], maximum_stops: [2,2] } };
const result = { instance_id: 'plan', problem_fingerprint: 'problem', matrix_fingerprint: 'matrix', distance_units:'map_units', method: 'vnd', feasible: true,
  total_distance: 12, longest_route_distance: 8, computation_time: .1,
  drivers: [{driver_id: 0, route: [0,1,2,0], distance: 8}, {driver_id: 1, route: [0,3,0], distance: 4}] };

test('unreadable backend responses give a safe retry message', async t => {
  t.mock.method(global,'fetch',async()=>({ok:true,status:200,json:async()=>{throw new SyntaxError('fixture body');}}));
  await assert.rejects(api.healthCheck(), /unreadable response/);
});

test('application results require exact matrix/problem identity and complete feasible coverage', () => {
  assert.doesNotThrow(() => validateRouteResult(instance, result));
  for (const patch of [{matrix_fingerprint:'other'}, {problem_fingerprint:'other'}, {instance_id:'other'}, {total_distance:NaN}, {feasible:false}])
    assert.throws(() => validateRouteResult(instance, {...result,...patch}));
  for (const routes of [[[0,1,1,0],[0,3,0]], [[0,1,2],[0,3,0]], [[0,1,2,3,0],[0,0]], [[0,1,0,2,0],[0,3,0]]])
    assert.throws(() => validateRouteResult(instance, {...result, drivers: result.drivers.map((d,i) => ({...d,route:routes[i]}))}), /validation/);
});

test('application permits empty driver routes and enforces fixed workloads', () => {
  const problem = {...instance, num_stops:1, stops:[{stop_id:1}], workload:{minimum_stops:[1,0],maximum_stops:[1,0]}};
  const solved = {...result, total_distance:8, drivers:[{driver_id:0,route:[0,1,0],distance:8},{driver_id:1,route:[0,0],distance:0}]};
  assert.doesNotThrow(() => validateRouteResult(problem, solved));
  assert.throws(() => validateRouteResult(problem, {...solved, drivers:solved.drivers.map(d=>({...d,driver_id:1-d.driver_id}))}), /validation/);
});

test('fixed workload request remains balanced with more drivers than stops', () => {
  assert.deepEqual(planRequest({...initialPlan,numStops:5,numDrivers:7,workloadMode:'fixed'}).workload,
    {policy:'balanced_stop_count',minimum_stops:[1,1,1,1,1,0,0],maximum_stops:[1,1,1,1,1,0,0]});
});

test('initial methods cannot mix matrices even when instance identifiers agree', async t => {
  t.mock.method(api, 'createInstance', async () => instance);
  t.mock.method(api, 'solveRouting', async req => ({...result,method:req.method,matrix_fingerprint:'other'}));
  const generated = await generatePlan(initialPlan,()=>{});
  assert.equal(generated.results.size,0);
  assert.equal(generated.errors.length,2);
});

test('job polling retries failures and reaches cancelled without another poll', async t => {
  const queued=[], updates=[], errors=[];
  t.mock.method(global,'setTimeout',fn=>{queued.push(fn);return queued.length;});
  t.mock.method(global,'clearTimeout',()=>{});
  let calls=0;
  const stop=watchTask('job',async (id,signal)=>{
    assert.equal(id,'job'); assert.ok(signal instanceof AbortSignal);
    if (++calls===1) throw new Error('temporarily unavailable');
    return {job_id:id,status:calls===2?'cancelling':'cancelled'};
  },value=>updates.push(value.status),value=>errors.push(value));
  await flush(); await queued.shift()(); await queued.shift()();
  assert.deepEqual(updates,['cancelling','cancelled']); assert.equal(errors.length,1); assert.equal(queued.length,0); stop();
});

test('job polling rejects a wrong identity and aborts late results on cleanup', async t => {
  t.mock.method(global,'setTimeout',()=>1); t.mock.method(global,'clearTimeout',()=>{});
  const errors=[];
  const stop=watchTask('expected',async()=>({job_id:'other',status:'completed'}),()=>assert.fail('wrong identity'),e=>errors.push(e));
  await flush(); stop(); assert.match(errors[0],/identity/);
  let resolve, signal;
  const cleanup=watchTask('old',(_,s)=>{signal=s;return new Promise(r=>resolve=r);},()=>assert.fail('late result'),()=>assert.fail('late error'));
  cleanup(); resolve({job_id:'old',status:'completed'}); await flush(); assert.equal(signal.aborted,true);
});

test('missing jobs after a restart terminate polling instead of locking the UI forever', async t => {
  const timer=t.mock.method(global,'setTimeout',()=>assert.fail('Permanent missing job must not retry'));
  const errors=[];
  const stop=watchTask('lost',async()=>{throw Object.assign(new Error('Job not found'),{status:404});},()=>assert.fail('No result'),(message,terminal)=>errors.push({message,terminal}));
  await flush(); stop(); assert.deepEqual(errors,[{message:'Job not found',terminal:true}]); assert.equal(timer.mock.callCount(),0);
});

test('optimization and strategy service calls preserve scoped identifiers and budgets', async t => {
  const calls=[];
  t.mock.method(global,'fetch',async(url,options)=>{calls.push([url,options]);return {ok:true,json:async()=>({})};});
  const request={instance_id:'plan',method:'strategy',strategy_job_id:'experiment',strategy_id:'candidate',operations:0,seconds:0,search_seed:0};
  await api.startOptimization(request); await api.cancelOptimization('job'); await api.cancelStrategy('experiment');
  assert.equal(calls[0][0],'/api/optimization/jobs'); assert.deepEqual(JSON.parse(calls[0][1].body),request);
  assert.equal(calls[1][0],'/api/optimization/jobs/job/cancel');
  assert.equal(calls[2][0],'/api/strategy-experiments/experiment/cancel');
});

test('comparison excludes mismatched matrices while labeling incomplete valid plans', () => {
  const comparison={instance_id:'plan',matrix_fingerprint:'matrix',problem_fingerprint:'problem',comparisons:[
    {...result,method:'nearest_neighbor',total_distance:10,longest_route_distance:6,drivers:result.drivers.map((d,i)=>({...d,distance:i?4:6})),server_verified:true,execution:{status:'completed',termination:'historical_baseline_complete'}},
    {...result,server_verified:true,execution:{status:'incomplete',termination:'operation_budget',operations:100,budget_exhausted:true}},
    {...result,method:'portfolio',matrix_fingerprint:'other',total_distance:1}]};
  const html=renderToStaticMarkup(React.createElement(CompareScreen,{instance,comparison}));
  assert.doesNotMatch(html.split('<details')[0],/12.00|20.0% longer/);assert.match(html,/12.00 map units/); assert.match(html,/incomplete/); assert.match(html,/budget exhausted/);
  assert.match(html,/Unverified or mismatched records/); assert.doesNotMatch(html,/90.0% shorter/);
});

test('execution details distinguish retained and raw distances with honest budget status', () => {
  const html=renderToStaticMarkup(React.createElement(OptimizationDetails,{mode:'synthetic',result:{...result,server_verified:true,execution:{status:'incomplete',termination:'operation_budget',initial_distance:12,final_distance:12,improvement_percent:0,operations:0,operation_limit:0,budget_exhausted:true,accepted_moves:0,operator_calls:0,ils_iterations:0,constructors:[],raw_events:[{stage:'test',method:'candidate',status:'rejected',raw_distance:20,retained_distance:12,accepted:false}]}}}));
  assert.match(html,/incomplete/i); assert.match(html,/20.00 map units/); assert.match(html,/12.00 map units/);
  assert.match(html,/constructor/i); assert.doesNotMatch(html,/66.7%/);
});

test('product evolution defaults to one real Ollama method and no research choices', () => {
  const html=renderToStaticMarkup(React.createElement(StrategyLab,{hasInstance:false,applying:false,onApply(){},onStatus(){}}));
  assert.match(html,/AI-guided strategy/);assert.match(html,/qwen3:1.7b/);assert.match(html,/Check Ollama/);
  assert.match(html,/trusted routing engine/);assert.match(html,/does not guarantee an optimal solution/);
  assert.doesNotMatch(html,/<select|type="radio"|Random baseline|Hand-authored portfolio|Offline fixture|Apply to current plan|<details open/);
});
