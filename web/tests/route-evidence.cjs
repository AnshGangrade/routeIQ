const {test}=require('node:test');
const assert=require('node:assert/strict');
const React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
const {savings,savingsText,routeInsights,completionText}=require('../src/services/routeEvidence.ts');
const {CompactResults}=require('../src/components/CompactResults.tsx');
const {RouteExplanation}=require('../src/components/RouteExplanation.tsx');
const {CompareScreen}=require('../src/components/CompareScreen.tsx');
const instance={instance_id:'plan',problem_fingerprint:'problem',matrix_fingerprint:'matrix',distance_units:'meters',mode:'road',num_stops:3,num_drivers:2,stops:[1,2,3].map(stop_id=>({stop_id}))};
const baseline={...instance,method:'nearest_neighbor',feasible:true,total_distance:1000,longest_route_distance:600,computation_time:.1,execution:{status:'completed'},drivers:[{driver_id:0,route:[0,1,2,0],distance:600,duration:120},{driver_id:1,route:[0,3,0],distance:400,duration:60}]};
const result={...baseline,method:'vnd',total_distance:800,longest_route_distance:400,computation_time:.25,drivers:baseline.drivers.map(d=>({...d,distance:400})),execution:{status:'incomplete',termination:'operation_budget',budget_exhausted:true,raw_events:[
 {stage:'construction',method:'legacy_2opt',raw_distance:1000,retained_distance:1000,accepted:true,status:'completed'},
 {stage:'vnd',method:'cross_relocate',raw_distance:800,retained_distance:800,accepted:true,status:'completed'},
 {stage:'vnd',method:'two_opt',raw_distance:800,retained_distance:800,accepted:false,status:'completed'}
]}};
const el=(component,props)=>render(React.createElement(component,props));

test('savings name a fixed baseline and calculate absolute and relative distance from matching evidence',()=>{
 assert.deepEqual(savings(instance,result,baseline),{absolute:200,percent:20,baseline:1000,comparison:'20.0% shorter'});
 assert.match(savingsText(instance,{...result,total_distance:1200},baseline),/200 m longer.*20.0% longer/);
 assert.match(savingsText(instance,{...result,total_distance:1000},baseline),/0 m saved.*Same distance/);
});
test('missing, failed, unverified, mismatched or nonfinite comparisons never produce savings',()=>{
 for(const change of [{instance_id:'wrong'},{problem_fingerprint:'wrong'},{matrix_fingerprint:'wrong'},{distance_units:'map_units'},{feasible:false},{feasible:null},{total_distance:NaN},{total_distance:-1},{execution:{status:'failed'}},{execution:{status:'running'}}]) {
  assert.equal(savings(instance,result,{...baseline,...change}),null);
  assert.equal(savings(instance,{...result,...change},baseline),null);
 }
 assert.equal(savings(instance,result),null);
 assert.equal(savings({...instance,matrix_fingerprint:null},result,baseline),null);
 assert.equal(savings(instance,result,{...baseline,method:'2opt'}),null);
});
test('zero baseline never produces a percentage, including ties',()=>{
 for(const total_distance of [0,1]) {
  const b={...baseline,total_distance:0};
  assert.equal(savings(instance,{...result,total_distance},b).percent,null);
  assert.doesNotMatch(savingsText(instance,{...result,total_distance},b),/%/);
 }
});
test('summary shows measured savings, feasibility, workload, available driving time and incomplete status',()=>{
 const html=el(CompactResults,{result,instance,results:new Map([['nearest_neighbor',baseline]])});
 for(const pattern of [/Nearest Neighbor \(historical\)/,/1.00 km/,/200 m saved/,/20.0% shorter/,/3 \/ 3/,/every stop served exactly once/,/Driver 1: 2 stops/,/Driver 2: 1 stops/,/3 min summed/,/0.250 s/,/search budget reached/]) assert.match(html,pattern);
 assert.doesNotMatch(html,/Calculation completed/);
});
test('summary omits incomplete duration and invalid percentages and rejects duplicate coverage',()=>{
 const partial={...result,drivers:result.drivers.map((d,i)=>({...d,duration:i?null:120}))};
 const html=el(CompactResults,{result:partial,instance,results:new Map()});
 assert.doesNotMatch(html,/Driving time:|%/);assert.match(html,/Savings unavailable/);
 const bad={...result,drivers:result.drivers.map(d=>({...d,route:[0,1,0]}))};
 assert.match(el(CompactResults,{result:bad,instance,results:new Map()}),/Not verified/);
});
test('why route uses retained engine gains and measured driver differences, never model prose',()=>{
 const r={...result,execution:{...result.execution,controller:{decisions:[{proposal:{rationale:'Fabricated 99% improvement'}}]}}};
 const insights=routeInsights(instance,r,baseline);
 assert.match(insights[0].text,/Cross-driver relocation.*200 m/);
 assert.match(insights[1].text,/last recorded 2-Opt pass did not improve/);
 assert.equal(insights[2].driverId,0);assert.match(insights[2].text,/same stops/);
 assert.doesNotMatch(JSON.stringify(insights),/Fabricated|99%|optimal solution/);
});
test('worse raw candidates, failed events and unrelated traces cannot invent gains',()=>{
 for(const raw_events of [
  [{stage:'vnd',method:'swap',raw_distance:1200,retained_distance:800,accepted:false,status:'completed'}],
  result.execution.raw_events.map(e=>({...e,status:'failed'})),
  result.execution.raw_events.map(e=>({...e,retained_distance:e.retained_distance+1}))
 ]) assert.equal(routeInsights(instance,{...result,execution:{...result.execution,raw_events}}).length,0);
 assert.equal(routeInsights(instance,{...result,feasible:false},baseline).length,0);
});
test('insight controls focus the measured driver or the fleet, with no invented driver attribution',()=>{
 const tree=RouteExplanation({instance,result,baseline,onFocus:id=>selected.push(id)});
 const selected=[];
 const list=tree.props.children[1];
 for(const li of list.props.children) li.props.children[1].props.onClick();
 assert.deepEqual(selected,[null,null,0]);
 assert.match(el(RouteExplanation,{instance,result:{...result,execution:null},onFocus(){}}),/No measured move-level explanation/);
});
test('comparison highlights the shortest valid result even when its search is incomplete',()=>{
 const comparison={...instance,comparisons:[baseline,result,{...result,method:'adaptive',total_distance:1,feasible:false}]};
 const html=el(CompareScreen,{instance,comparison});
 assert.match(html,/Shortest validated route found/);assert.match(html,/800 m/);assert.match(html,/Valid incumbent/);
 assert.match(html,/200 m saved/);assert.doesNotMatch(html,/99.9% shorter|<details[^>]* open/);
 assert.match(completionText(result),/budget reached/);
});
test('legacy comparisons without fingerprints or feasibility cannot display percentage savings',()=>{
 const legacy={instance_id:'plan',mode:'road',num_stops:3,num_drivers:2};
 const comparison={instance_id:'plan',comparisons:[{method:'nearest_neighbor',total_distance:1000,longest_route_distance:600,computation_time:.1},{method:'2opt',total_distance:800,longest_route_distance:400,computation_time:.1}]};
 assert.doesNotMatch(el(CompareScreen,{instance:legacy,comparison}),/20.0% shorter/);
});
