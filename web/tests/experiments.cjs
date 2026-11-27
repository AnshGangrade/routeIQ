const {test}=require('node:test');
const assert=require('node:assert/strict');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const {StrategyLab}=require('../src/components/StrategyLab.tsx');
const {validProviderCheck,experimentEvidence,matchedRandom}=require('../src/services/experiments.ts');

test('provider checks keep a deadline as well as caller cancellation',async t=>{
  const {api}=require('../src/services/api.ts');
  const caller=new AbortController();caller.abort();
  const timeout=AbortSignal.timeout.bind(AbortSignal);const durations=[];
  t.mock.method(AbortSignal,'timeout',ms=>{durations.push(ms);return timeout(ms);});
  t.mock.method(global,'fetch',async (url,options)=>{
    assert.ok(options.signal.aborted);assert.notEqual(options.signal,caller.signal);
    return {ok:true,json:async()=>({})};
  });
  await api.checkStrategyProvider({model:'qwen3:1.7b'},caller.signal);
  assert.deepEqual(durations,[10000]);
});

test('single experiment page explains measured strategies and has no legacy tabs',()=>{
  const html=renderToStaticMarkup(React.createElement(StrategyLab,{hasInstance:false,applying:false,onApply(){},onStatus(){}}));
  assert.match(html,/<h1>AI-guided strategy<\/h1>/);
  assert.match(html,/The LLM proposes strategy configurations. The trusted routing engine evaluates them. It does not guarantee an optimal solution./);
  assert.doesNotMatch(html,/Legacy heuristic lab|role="tab"|Evolution Lab/);
  assert.doesNotMatch(html,/Random baseline|Offline fixture|<select/);assert.match(html,/Run evolution/);
});
test('provider checks require exact model, coherent status and valid payload',()=>{
  const available={configured:true,reachable:true,available:true,model:'qwen3:1.7b',status:'available',message:'Ready'};
  assert.ok(validProviderCheck(available,available.model));
  assert.ok(!validProviderCheck(available,'another'));
  assert.ok(!validProviderCheck({...available,status:'unreachable'},available.model));
  assert.ok(!validProviderCheck({...available,message:null},available.model));
  assert.ok(!validProviderCheck({},available.model));
});
const record=(source,parents=[],eligible=true)=>({creation_method:source,parents,fitness:{eligible,mean_distance:10,completed:2,incomplete:0,failed:0,cases:2,expected_cases:2,policy:'completed_panel/v1'}});
test('evidence counts missing and attributes live evaluated ancestry, not fixtures or fallback',()=>{
  const state={manifest:{provider_mode:'ollama',config:{case_ids:['a','b']}},proposal_events:[{source:'llm',outcome:'accepted',strategy_id:'llm'}],reserved_evaluations:8,best_id:'child',records:{seed:record('seed'),llm:record('llm'),child:record('mutation',['llm'])}};
  Object.assign(state.records.llm,{strategy_id:'llm',evaluation_history:[{rows:[{case_id:'a',status:'completed',feasible:true,independently_validated:true,termination:'local_search_complete'},{case_id:'b',status:'completed',feasible:true,independently_validated:true,termination:'local_search_complete'}]}]});
  assert.deepEqual(experimentEvidence(state),{completed:6,incomplete:0,failed:0,missing:2,acceptedLLM:1,evaluatedLLM:1,winnerLLM:true});
  assert.equal(experimentEvidence({...state,best_id:'seed'}).winnerLLM,false);
  assert.equal(experimentEvidence(state,'seed').winnerLLM,false,'Attribution follows the displayed completed recommendation, not the historical bounded winner');
  assert.equal(experimentEvidence({...state,manifest:{provider_mode:'offline'}}).acceptedLLM,0);
  assert.equal(experimentEvidence({...state,manifest:{provider_mode:'offline'}}).winnerLLM,false);
  state.records.llm.fitness.eligible=false;
  assert.equal(experimentEvidence(state).winnerLLM,false);
});
test('random comparison rejects unmatched inputs, running jobs and offline proposals',()=>{
  const state={status:'completed',manifest:{arm:'llm',provider_mode:'ollama',software:{v:1},panel:[1],config:{seed:0,case_ids:['x']}},best_id:'a',records:{a:record('seed')}};
  const random=structuredClone(state);random.manifest.arm='random';random.records.a.fitness.mean_distance=8;
  assert.equal(matchedRandom(state,[random]).difference,-2);
  assert.equal(matchedRandom(state,[random]).percentage,-25);
  assert.equal(matchedRandom({...state,status:'running'},[random]),null);
  assert.equal(matchedRandom({...state,manifest:{...state.manifest,provider_mode:'offline'}},[random]),null);
  random.manifest.config.seed=1;assert.equal(matchedRandom(state,[random]),null);
  random.manifest.config.seed=0;random.manifest.panel=[2];assert.equal(matchedRandom(state,[random]),null);
});

const {candidateRecommendation,completedCandidate}=require('../src/services/experiments.ts');
test('candidate recommendation prefers a complete panel and never falls back to an incomplete candidate',()=>{
 const make=(strategy_id,distance,complete)=>({strategy_id,fitness:{eligible:true,policy:'completed_panel/v1',mean_distance:distance,cases:2,expected_cases:2,completed:complete?2:0,incomplete:complete?0:2,failed:0}});
 const a=make('a',10,false),b=make('b',20,true);
 assert.equal(candidateRecommendation({records:{a,b}}),b);
 assert.equal(candidateRecommendation({records:{a}}),null);assert.equal(completedCandidate(a),false);
 assert.equal(candidateRecommendation({records:{a:{...a,fitness:{...a.fitness,eligible:false}}}}),null);
});
test('a live-tagged configuration without an evaluated accepted proposal is not LLM evidence',()=>{
 const state={manifest:{provider_mode:'ollama',config:{case_ids:['a']}},records:{a:{strategy_id:'a',...record('llm')}},best_id:'a'};
 assert.equal(experimentEvidence(state).acceptedLLM,0);assert.equal(experimentEvidence(state).winnerLLM,false);
});


test('accepted proposals and successfully evaluated proposals are distinct counts',()=>{
 const complete={strategy_id:'llm',...record('llm'),evaluation_history:[{rows:['a','b'].map(case_id=>({case_id,status:'completed',feasible:true,independently_validated:true,termination:'local_search_complete'}))}]};
 const state={manifest:{provider_mode:'ollama',config:{case_ids:['a','b'],proposal_policy:'llm_only'}},records:{llm:complete},proposal_events:[{source:'llm',outcome:'accepted',strategy_id:'llm'}],best_id:'llm'};
 assert.equal(experimentEvidence(state).acceptedLLM,1);assert.equal(experimentEvidence(state).evaluatedLLM,1);
 assert.equal(candidateRecommendation(state),complete);
 complete.evaluation_history[0].rows[1].status='incomplete';complete.fitness.incomplete=1;complete.fitness.completed=1;complete.fitness.eligible=false;
 assert.equal(experimentEvidence(state).acceptedLLM,1);assert.equal(experimentEvidence(state).evaluatedLLM,0);
 assert.equal(candidateRecommendation(state),null);
});

test('only complete validated strategy applications can replace the current result',()=>{
 const {completedOptimizationResult}=require('../src/services/product.ts');
 const instance={instance_id:'p',problem_fingerprint:'fp',matrix_fingerprint:'m',distance_units:'map_units',num_stops:1,num_drivers:1,stops:[{stop_id:1}]};
 const result={...instance,method:'strategy',feasible:true,total_distance:4,longest_route_distance:4,drivers:[{driver_id:0,route:[0,1,0],distance:4}],execution:{status:'completed',termination:'local_search_complete',schedule_completed:true,route_validity:'validated',independently_validated:true}};
 const job={...instance,method:'strategy',status:'completed',result};
 assert.equal(completedOptimizationResult(instance,job),result);
 for(const status of ['incomplete','cancelled','failed'])assert.equal(completedOptimizationResult(instance,{...job,status}),null);
 for(const change of [{matrix_fingerprint:'wrong'},{total_distance:3},{longest_route_distance:3},{feasible:false},{execution:{...result.execution,termination:'operation_budget'}},{execution:{...result.execution,independently_validated:false}}])
  assert.throws(()=>completedOptimizationResult(instance,{...job,result:{...result,...change}}));
 assert.equal(completedOptimizationResult(instance,{...job,published:false}),null);
});


test('trusted seed comparison requires verified same-panel evidence with honest loss, tie and zero arithmetic',()=>{
 const {trustedSeedComparison}=require('../src/services/experiments.ts');
 const winner={...record('llm'),strategy_id:'w'};
 for(const seed_mean of [0,5,10,20]) {
   const c={verified:true,winner_id:'w',seed_id:'seed',winner_mean:10,seed_mean,difference:seed_mean-10,
     percentage:seed_mean?(seed_mean-10)/seed_mean*100:null,cases:2,distance_units:'map_units'};
   assert.deepEqual(trustedSeedComparison({seed_comparison:c},winner),c);
   for(const patch of [{verified:false},{winner_id:'other'},{cases:1},{winner_mean:9},{seed_mean:NaN},{difference:999},{percentage:999},{distance_units:'meters'}])
     assert.equal(trustedSeedComparison({seed_comparison:{...c,...patch}},winner),null);
   assert.equal(trustedSeedComparison({seed_comparison:c},{...winner,fitness:{...winner.fitness,incomplete:1}}),null);
 }
 assert.equal(trustedSeedComparison({},winner),null);
});


test('equal-score recommendations use the engine configuration-fingerprint tie break',()=>{
 const {candidateRecommendation}=require('../src/services/experiments.ts');
 const a={...record('seed'),strategy_id:'a',configuration_fingerprint:'fff'};
 const b={...record('seed'),strategy_id:'b',configuration_fingerprint:'000'};
 assert.equal(candidateRecommendation({records:{a,b}}).strategy_id,'b');
});
