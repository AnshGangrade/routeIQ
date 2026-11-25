const {test}=require('node:test');
const assert=require('node:assert/strict');
const {draftIdentity,completeDuration}=require('../src/services/planning.ts');
const {initialPlan}=require('../src/services/workflow.ts');

test('plan invalidation covers every problem-defining draft change',()=>{
  const base={...initialPlan,mode:'road',depotLon:'20',depotLat:'10',stops:[{lon:'20.1',lat:'10.1'}]};
  for(const change of [{mode:'synthetic'},{numStops:9},{numDrivers:4},{seed:'0'},{layout:'clustered'},{workloadMode:'fixed'},{depotLon:'21'},{depotLat:'11'},{stops:[]},{stops:[{lon:'20.2',lat:'10.1'}]}])
    assert.notEqual(draftIdentity(base),draftIdentity({...base,...change}));
  assert.equal(draftIdentity(base),draftIdentity(structuredClone(base)));
});
test('entry method and sample radius do not invalidate unchanged route coordinates',()=>{
  assert.equal(draftIdentity(initialPlan),draftIdentity({...initialPlan,stopEntry:'manual',radius:20}));
});
test('duration is absent unless supplied and complete for every active driver',()=>{
  const result=drivers=>({drivers});
  const active=duration=>({route:[0,1,0],duration});
  assert.equal(completeDuration(result([active(null)])),null);
  assert.equal(completeDuration(result([active(60),active(null)])),null);
  assert.equal(completeDuration(result([active(60),active(120),{route:[0,0],duration:null}])),180);
  assert.equal(completeDuration(result([active(0)])),0);
  assert.equal(completeDuration(result([active(Infinity)])),null);
  assert.equal(completeDuration(result([active(-1)])),null);
});
