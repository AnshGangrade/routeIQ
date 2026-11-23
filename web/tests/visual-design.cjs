// Presentation regressions, loaded after the existing TypeScript/React setup.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
const {Home}=require('../src/components/Home.tsx');
const {FitnessPlot,Lineage,ResearchVisuals,ComparisonBars,CandidateComparison}=require('../src/components/ResearchVisuals.tsx');
const {driverColor,finiteSeries,sourceLabel}=require('../src/services/presentation.ts');
const {ConfirmationProvider}=require('../src/components/Design.tsx');
const el=(component,props)=>render(React.createElement(component,props));

test('home illustration is explicitly decorative and cannot be mistaken for route evidence',()=>{
 const html=el(Home,{hasInstance:false});
 assert.match(html,/Illustration only/);assert.match(html,/not a geographic map or route result/);
 assert.match(html,/Create route plan/);assert.match(html,/href="#lab"/);
 assert.doesNotMatch(html,/\d+\.\d+ km|% improvement|<input/);
});
test('driver colors remain consistent and distinct for the first ten drivers',()=>{
 assert.equal(new Set(Array.from({length:10},(_,i)=>driverColor(i))).size,10);
 assert.equal(driverColor(0),driverColor(10));assert.match(driverColor(-1),/^#[0-9a-f]{6}$/i);
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
 return el(CompareScreen,{instance:{instance_id:'a',mode:'synthetic',num_stops:5,num_drivers:2,matrix_fingerprint:'m',problem_fingerprint:'p'},comparison:{instance_id:'a',matrix_fingerprint:'m',problem_fingerprint:'p',comparisons:rows},loading:false,error:null,busy:false,evolution:null,onRetry(){},onRun(){},onView(){}});
}
const quietRow=(method,distance,status='completed')=>({method,total_distance:distance,longest_route_distance:distance,computation_time:.01,feasible:true,matrix_fingerprint:'m',problem_fingerprint:'p',execution:{status,termination:'budget_exhausted',operations:100}});
test('Quiet Atlas highlights the shortest valid incomplete incumbent with honest status',()=>{
 const html=quietComparison([quietRow('nearest_neighbor',100),quietRow('vnd',80,'incomplete')]);
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
