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
  assert.match(html,/<h1>Strategy Experiments<\/h1>/);
  assert.match(html,/The LLM proposes strategy configurations. It does not calculate routes or guarantee an optimal solution./);
  assert.doesNotMatch(html,/Legacy heuristic lab|role="tab"|Evolution Lab/);
  assert.match(html,/Random baseline/);assert.match(html,/AI-guided/);assert.match(html,/Run experiment/);
});
test('provider checks require exact model, coherent status and valid payload',()=>{
  const available={configured:true,reachable:true,available:true,model:'qwen3:1.7b',status:'available',message:'Ready'};
  assert.ok(validProviderCheck(available,available.model));
  assert.ok(!validProviderCheck(available,'another'));
  assert.ok(!validProviderCheck({...available,status:'unreachable'},available.model));
  assert.ok(!validProviderCheck({...available,message:null},available.model));
  assert.ok(!validProviderCheck({},available.model));
});
const record=(source,parents=[],eligible=true)=>({creation_method:source,parents,fitness:{eligible,mean_distance:10,completed:1,incomplete:1,failed:0}});
test('evidence counts missing and attributes live evaluated ancestry, not fixtures or fallback',()=>{
  const state={manifest:{provider_mode:'ollama'},reserved_evaluations:8,best_id:'child',records:{seed:record('seed'),llm:record('llm'),child:record('mutation',['llm'])}};
  assert.deepEqual(experimentEvidence(state),{completed:3,incomplete:3,failed:0,missing:2,acceptedLLM:1,evaluatedLLM:1,winnerLLM:true});
  assert.equal(experimentEvidence({...state,best_id:'seed'}).winnerLLM,false);
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
