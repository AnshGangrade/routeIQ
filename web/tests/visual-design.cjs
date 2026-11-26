// Presentation regressions, loaded after the existing TypeScript/React setup.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
const {Home}=require('../src/components/Home.tsx');
const {FitnessPlot,Lineage,ResearchVisuals,ComparisonBars,CandidateComparison}=require('../src/components/ResearchVisuals.tsx');
const {driverColor,finiteSeries,sourceLabel,mapRouteStyle}=require('../src/services/presentation.ts');
const {ConfirmationProvider}=require('../src/components/Design.tsx');
const {ControllerEvidence}=require('../src/components/OptimizationDetails.tsx');
const el=(component,props)=>render(React.createElement(component,props));

test('adaptive evidence distinguishes offline proposals, fallback and measured units',()=>{
 const html=el(ControllerEvidence,{evidence:{mode:'offline fixture',model:'fixture-model',calls:2,reserved_tokens:10000,reported_tokens:0,usage_known:false,model_seconds:.2,problem:{distance_units:'meters'},decisions:[
  {stage:'initial',source:'offline fixture',accepted:true,request:{},proposal:{rationale:'<script>not executable</script>'}},
  {stage:'checkpoint',source:'deterministic fallback',accepted:false,request:{error:'timeout'},telemetry:{best_distance:100,improvement_since_checkpoint:0,stagnated:true,remaining_operations:12,operator_statistics:{swap:{attempts:2,accepted_improvements:0,rejected_moves:2,operations:3,distance_reduction:0}}}}
 ]}});
 assert.match(html,/offline fixture/);assert.match(html,/deterministic fallback/);assert.match(html,/meters/);
 assert.match(html,/incomplete reporting/);assert.match(html,/Rejected/);assert.match(html,/timeout/);
 assert.doesNotMatch(html,/<script>|trained itself|LLM proposal/);
});

test('home illustration is explicitly decorative and cannot be mistaken for route evidence',()=>{
 const html=el(Home,{hasInstance:false});
 assert.match(html,/Illustration only/);assert.match(html,/not a geographic map or route result/);
 assert.match(html,/Create route plan/);assert.match(html,/href="#lab"/);
 assert.doesNotMatch(html,/\d+\.\d+ km|% improvement|<input/);
});
test('driver colors remain consistent and distinct for the all twenty supported drivers',()=>{
 assert.equal(new Set(Array.from({length:20},(_,i)=>driverColor(i))).size,20);
 assert.equal(driverColor(0),driverColor(20));assert.match(driverColor(-1),/^#[0-9a-f]{6}$/i);
});

test('driver colors survive selection and baseline patterns in map styles',()=>{
 for (let id=0;id<20;id++) for (const method of ['nearest_neighbor','2opt','portfolio','vnd','vnd_ils','strategy','adaptive']) {
  const selected=mapRouteStyle(method,true,id),other=mapRouteStyle(method,false,id);
  assert.equal(selected.color,driverColor(id));assert.equal(other.color,selected.color);
  assert.ok(selected.weight>other.weight);assert.ok(selected.opacity>other.opacity);
  if(['nearest_neighbor','2opt'].includes(method))assert.equal(selected.dashArray,'8 6');
 }
 assert.ok(new Set(Array.from({length:20},(_,i)=>driverColor(i))).size===20);
});
test('palette uses distinct muted colors and chart nodes preserve source labels',()=>{
 for(let i=0;i<20;i++)assert.ok(new Set(driverColor(i).slice(1).match(/../g)).size>1);
 const html=el(Lineage,{records:[{strategy_id:'winner',generation:0,creation_method:'seed',parents:[]}],bestId:'winner',offline:true});
 assert.match(html,/fill="#D9B65A"/);assert.match(html,/Hand-authored/);
});
test('chart statistics ignore failed, nonfinite and negative observations but retain zero',()=>{
 assert.deepEqual(finiteSeries([null,NaN,Infinity,-1,0,12]),{min:0,max:12,count:2});
 assert.deepEqual(finiteSeries([]),{min:0,max:0,count:0});
});
for (const values of [[0],[12,12],[20,null,10],[null,NaN]]) test(`fitness chart safely renders ${JSON.stringify(values)} without interpolating missing evidence`,()=>{
 const html=el(FitnessPlot,{history:values.map((best_so_far,generation)=>({generation,best_so_far}))});
 assert.doesNotMatch(html,/NaN|Infinity|undefined/);
 if(values.every(v=>v==null||!Number.isFinite(v))) assert.match(html,/No measured fitness/);
 else assert.match(html,/lower is better/);
 if(values.length===3) assert.match(html,/d="M[^L"]+ M/);
});
test('lineage draws only recorded relationships, and distinguishes offline fixture proposals',()=>{
 const seed={strategy_id:'parent',generation:0,creation_method:'seed',parents:[]};
 const child={strategy_id:'child',generation:1,creation_method:'llm',parents:['parent','unavailable']};
 const html=el(Lineage,{records:[seed,child],bestId:'child',offline:true});
 assert.equal((html.match(/<path /g)||[]).length,1);
 assert.match(html,/Hand-authored/);assert.match(html,/Offline fixture/);assert.doesNotMatch(html,/LLM proposal/);
 assert.equal(sourceLabel('llm',false),'LLM proposal');assert.equal(sourceLabel('mutation',true),'Mutation');
});
test('distance chart preserves zero and incomplete status without inventing percent gains',()=>{
 const html=el(ComparisonBars,{mode:'road',busy:false,onView(){},rows:[{method:'nearest_neighbor',total_distance:0},{method:'vnd',total_distance:1000,execution:{status:'incomplete'}},{method:'2opt',total_distance:NaN}]});
 assert.match(html,/0 m/);assert.match(html,/1.00 km/);assert.match(html,/Incomplete search/);
 assert.doesNotMatch(html,/NaN|2-Opt|% shorter/);assert.match(html,/width:0%/);
});
test('empty research notebook discloses missing validation and held-out evidence',()=>{
 const html=el(ResearchVisuals,{state:null});
 assert.match(html,/Not supplied by this API/);assert.match(html,/No new held-out evaluation/);
 assert.match(html,/No evaluated generations/);assert.doesNotMatch(html,/<circle/);
});
test('confirmation shell has accessible labels and a safe non-destructive action',()=>{
 const html=el(ConfirmationProvider,{children:'Application'});
 assert.match(html,/aria-labelledby="confirm-title"/);assert.match(html,/aria-describedby="confirm-copy"/);
 assert.match(html,/Keep current plan/);assert.match(html,/Confirm change/);assert.doesNotMatch(html,/<dialog[^>]* open/);
});

test('candidate comparison retains failed evaluations and separate measured work and runtime',()=>{
 const html=el(CandidateComparison,{offline:true,records:[{strategy_id:'failed-candidate',creation_method:'llm',fitness:{mean_distance:null,eligible:false,completed:0,incomplete:1,failed:1,operations:100,seconds:2}}]});
 assert.match(html,/Ineligible/);assert.match(html,/Unavailable/);assert.match(html,/0 \/ 1 \/ 1/);
 assert.match(html,/100/);assert.match(html,/2.000 s/);assert.match(html,/Offline fixture/);
 assert.doesNotMatch(html,/improved|% shorter/);
});

test('candidate comparison handles a pending record before evaluation fields arrive',()=>{
 const html=el(CandidateComparison,{offline:true,records:[{strategy_id:'pending',creation_method:'seed',fitness:{}}]});
 assert.match(html,/Pending evaluation/);assert.match(html,/Unavailable/);assert.doesNotMatch(html,/NaN|undefined|0.000 s/);
});

const {CompareScreen}=require('../src/components/CompareScreen.tsx');
function quietComparison(rows) {
 return el(CompareScreen,{instance:{instance_id:'a',mode:'synthetic',num_stops:5,num_drivers:2,distance_units:'map_units',matrix_fingerprint:'m',problem_fingerprint:'p'},comparison:{instance_id:'a',matrix_fingerprint:'m',problem_fingerprint:'p',comparisons:rows},loading:false,error:null,busy:false,evolution:null,onRetry(){},onRun(){},onView(){}});
}
const quietRow=(method,distance,status='completed')=>({method,total_distance:distance,longest_route_distance:distance,computation_time:.01,feasible:true,distance_units:'map_units',matrix_fingerprint:'m',problem_fingerprint:'p',execution:{status,termination:'budget_exhausted',operations:100}});
test('Quiet Atlas highlights the shortest valid incomplete incumbent with honest status',()=>{
 const html=quietComparison([quietRow('nearest_neighbor',100,'incomplete'),quietRow('portfolio',80,'incomplete')]);
 const hero=html.slice(html.indexOf('aria-label="Best valid measured result"'),html.indexOf('aria-label="Measured fleet distance chart"'));
 assert.match(hero,/80.00 map units/);assert.match(hero,/incomplete/);assert.match(hero,/20.0% shorter/);assert.match(hero,/stopped before completion/);
 assert.match(html,/<details class="comparison-diagnostics">/);
});
test('Quiet Atlas excludes failed and mismatched results from best measured selection',()=>{
 const bad=quietRow('vnd_ils',1);bad.matrix_fingerprint='other';
 const html=quietComparison([quietRow('nearest_neighbor',100),quietRow('vnd',2,'failed'),bad]);
 const hero=html.slice(html.indexOf('aria-label="Best valid measured result"'),html.indexOf('aria-label="Measured fleet distance chart"'));
 assert.match(hero,/100.00 map units/);assert.doesNotMatch(hero,/2.00 map units|1.00 map units/);assert.match(html,/Failed evaluation/);assert.match(html,/Unverified result/);
});

test('completed comparison result takes recommendation priority over a shorter incomplete incumbent',()=>{
 const html=quietComparison([quietRow('nearest_neighbor',100),quietRow('portfolio',80,'incomplete')]);
 const hero=html.slice(html.indexOf('aria-label="Best valid measured result"'),html.indexOf('aria-label="Measured fleet distance chart"'));
 assert.match(hero,/100.00 map units/);assert.match(html,/80.00 map units/);assert.match(html,/incomplete/);
});
test('no valid comparison result is actionable and never creates a recommendation',()=>{
 const html=quietComparison([quietRow('portfolio',1,'failed')]);
 assert.doesNotMatch(html,/aria-label="Best valid measured result"/);assert.match(html,/No validated comparison result/);assert.match(html,/Run route comparison/);
});

const {ComparisonRun}=require('../src/services/comparison.ts');
const presetInstance={instance_id:'a',num_stops:1,num_drivers:1,stops:[{stop_id:1}],matrix_fingerprint:'m',problem_fingerprint:'p'};
const presetResult=method=>({instance_id:'a',method,feasible:true,total_distance:2,matrix_fingerprint:'m',problem_fingerprint:'p',drivers:[{driver_id:0,route:[0,1,0],distance:2}],execution:{status:'completed'}});
test('one comparison invocation uses one identity, fixed budgets and rejects repeated starts',async()=>{
 const calls=[],received=[],progress=[];
 const client={solveRouting:async body=>{calls.push(body);return presetResult(body.method);},startOptimization:async body=>{calls.push(body);return {job_id:'j',instance_id:'a',method:'portfolio'};},optimizationStatus:async()=>({job_id:'j',instance_id:'a',method:'portfolio',matrix_fingerprint:'m',problem_fingerprint:'p',status:'completed',result:presetResult('portfolio')})};
 const run=new ComparisonRun(presetInstance,p=>progress.push(p),r=>received.push(r),client);
 await Promise.all([run.run(),run.run()]);
 assert.equal(calls.length,3);assert.equal(received.length,3);assert.ok(calls.every(c=>c.instance_id==='a'));
 assert.equal(calls[2].operations,100000);assert.equal(calls[2].search_seed,0);assert.equal(progress.at(-1).status,'completed');
});
test('comparison cancellation during a baseline prevents later jobs and publishing late results',async()=>{
 let release;const received=[],progress=[],calls=[];
 const client={solveRouting:body=>{calls.push(body);return new Promise(r=>{release=r});}};
 const run=new ComparisonRun(presetInstance,p=>progress.push(p),r=>received.push(r),client);
 const pending=run.run();await run.cancel();release(presetResult('nearest_neighbor'));await pending;
 assert.equal(calls.length,1);assert.equal(received.length,0);assert.equal(progress.at(-1).status,'cancelled');
});
test('comparison retains errors instead of inventing success when no method can run',async()=>{
 const progress=[],received=[];
 const client={solveRouting:async()=>{throw Error('offline');},startOptimization:async()=>{throw Error('offline');}};
 await new ComparisonRun(presetInstance,p=>progress.push(p),r=>received.push(r),client).run();
 assert.equal(received.length,0);assert.equal(progress.at(-1).errors.length,3);assert.equal(progress.at(-1).status,'failed');
});

test('comparison cancels only its active optimizer identity and reaches terminal cancelled',async()=>{
 let release;let calls=[];let progress=[];
 const client={solveRouting:async body=>presetResult(body.method),startOptimization:async()=>({job_id:'mine',instance_id:'a',method:'portfolio'}),optimizationStatus:()=>new Promise(r=>release=r),cancelOptimization:async id=>{calls.push(id);return {job_id:id,instance_id:'a',status:'cancelling'};}};
 const run=new ComparisonRun(presetInstance,p=>progress.push(p),()=>{},client);const pending=run.run();
 while(!release) await new Promise(r=>setImmediate(r));
 await run.cancel();release({job_id:'mine',instance_id:'a',method:'portfolio',matrix_fingerprint:'m',problem_fingerprint:'p',status:'cancelled'});await pending;
 assert.deepEqual(calls,['mine']);assert.equal(progress.at(-1).status,'cancelled');
});
test('comparison rejects wrong matrix even for an otherwise feasible route',async()=>{
 const received=[],progress=[];
 const client={solveRouting:async body=>({...presetResult(body.method),matrix_fingerprint:'wrong'}),startOptimization:async()=>{throw Error('offline');}};
 await new ComparisonRun(presetInstance,p=>progress.push(p),r=>received.push(r),client).run();
 assert.equal(received.length,0);assert.equal(progress.at(-1).status,'failed');assert.equal(progress.at(-1).errors.length,3);
});

test('completed experiment loop never hides incomplete or failed evaluations in the result headline',()=>{
 const {experimentStatus}=require('../src/services/presentation.ts');
 assert.equal(experimentStatus({status:'completed',records:{a:{fitness:{incomplete:2,failed:0}}}}),'Finished with incomplete evaluations');
 assert.equal(experimentStatus({status:'completed',records:{a:{fitness:{incomplete:0,failed:1}}}}),'Finished with evaluation failures');
 assert.equal(experimentStatus({status:'cancelled',records:{}}),'cancelled');
});
