import { RouteExplanation } from './RouteExplanation';
import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { LocationPicker } from './LocationPicker';
import { RouteVisualization } from './RouteVisualization';
import { DriverDetailsPanel } from './DriverDetailsPanel';
import { CompactResults } from './CompactResults';
import { OptimizationControls, type Budget } from './OptimizationControls';
import { OptimizationDetails } from './OptimizationDetails';
import { useConfirm } from './Design';
import { parseCoordinatePair } from '../services/inputs';
import { validatePlan, type PlanDraft, type Method } from '../services/workflow';
import { activeStatus, statusText } from '../services/product';
import type { InstanceResponse, RoutingResultResponse, OptimizationJob } from '../types/api';

interface Props {
  draft: PlanDraft; setDraft: Dispatch<SetStateAction<PlanDraft>>;
  instance: InstanceResponse | null; result: RoutingResultResponse | null; results: Map<string,RoutingResultResponse>;
  stale: boolean; busy: boolean; method: Method; onMethod: (method:Method)=>void;
  driver: number|null; onDriver:(id:number|null)=>void; onGenerate:()=>void; onRun:(method:Method)=>void;
  budget: Budget; setBudget: Dispatch<SetStateAction<Budget>>; job: OptimizationJob|null;
  optimizationError: string|null; onCancel:()=>void;
}

export function PlanningWorkspace(p: Props) {
  const confirm=useConfirm();
  const [editing,setEditing]=useState(!p.instance);
  const [expanded,setExpanded]=useState(true);
  const [selectedStop,setSelectedStop]=useState<number|null>(null);
  const [error,setError]=useState<string|null>(null);
  const [locating,setLocating]=useState(false);
  const list=useRef<HTMLDivElement>(null);
  const {draft,instance}=p;
  const current=!!instance && !p.stale;
  const result=current ? p.result : null;
  const editingMap=editing || !current || !result;
  const patch=(values:Partial<PlanDraft>)=>{p.setDraft(d=>({...d,...values}));setError(null);};
  useEffect(()=>{setSelectedStop(null);setEditing(!instance);},[instance?.instance_id]);
  useEffect(()=>{if(p.result && !p.stale)setEditing(false);},[p.result]);
  useEffect(()=>{if(p.stale)setEditing(true);},[p.stale]);
  useEffect(()=>{
    if(!result)return;
    const scroll=list.current?.closest<HTMLElement>('.planning-scroll');
    const summary=scroll?.querySelector<HTMLElement>('.workspace-results');
    if(scroll && summary)scroll.scrollTop+=summary.getBoundingClientRect().top-scroll.getBoundingClientRect().top;
  },[result]);
  const selectStop=(id:number)=>{
    setSelectedStop(id);
    if(result && !editingMap) {
      const driver=result.drivers.find(d=>d.route.includes(id));
      if(driver)p.onDriver(driver.driver_id);
    }
    list.current?.querySelector<HTMLElement>(`[data-stop="${id}"]`)?.scrollIntoView({block:'nearest'});
  };
  const selectDriver=(id:number|null)=>{setSelectedStop(null);if(result)setEditing(false);p.onDriver(id);};
  const remove=async(index:number)=>{
    if(await confirm(`Remove delivery stop ${index+1}?`)) {
      p.setDraft(d=>({...d,stops:d.stops.filter((_,i)=>i!==index)}));
      setSelectedStop(null);
    }
  };
  const locate=()=>{
    if(!navigator.geolocation){setError('Location unavailable. Enter coordinates or select the depot on the map.');return;}
    setLocating(true);
    navigator.geolocation.getCurrentPosition(position=>{patch({depotLat:position.coords.latitude.toFixed(6),depotLon:position.coords.longitude.toFixed(6)});setLocating(false);},
      ()=>{setError('Could not get your location. Enter coordinates or use the map.');setLocating(false);},{timeout:10000});
  };
  const nearby=async()=>{
    const depot=parseCoordinatePair(draft.depotLon,draft.depotLat);
    if(!depot || !Number.isInteger(draft.numStops) || draft.numStops<5 || draft.numStops>99 || !Number.isFinite(draft.radius) || draft.radius<1 || draft.radius>50){setError('Set a valid depot, 5–99 stops and a radius of 1–50 km.');return;}
    if(draft.stops.length && !await confirm('Replace the existing stops with new sample locations?'))return;
    patch({stops:Array.from({length:draft.numStops},()=>{
      const angle=Math.random()*Math.PI*2, radius=Math.sqrt(Math.random())*draft.radius/111;
      return {lon:(depot[0]+radius*Math.cos(angle)).toFixed(6),lat:(depot[1]+radius*Math.sin(angle)).toFixed(6)};
    })});setSelectedStop(null);
  };
  const generate=async()=>{
    const invalid=validatePlan(draft);setError(invalid);
    if(invalid)return;
    if(!instance || await confirm('Generate a new selected plan? The current calculated routes will be replaced.'))p.onGenerate();
  };
  const syntheticStops=current ? instance?.stops || [] : [];
  return <section className={`planning-workspace ${expanded?'panel-expanded':'panel-collapsed'}`} aria-label="Route Plan workspace">
    <button className="planning-toggle button secondary" aria-expanded={expanded} aria-controls="planning-column" onClick={()=>setExpanded(v=>!v)}>{expanded?'Hide planning panel':'Show planning panel'}</button>
    <aside id="planning-column" className="planning-column" aria-label="Planning controls and delivery stops">
      <div className="planning-scroll">
        <header><h1>Route Plan</h1></header>
        {p.stale && <p className="notice" role="status">Draft changed. Previous routes are stale and hidden. Generate Plan to calculate these changes.</p>}
        <fieldset disabled={p.busy} className="plan-settings">
          <legend>Plan settings</legend>
          <div className="routing-mode">{(['synthetic','road'] as const).map(mode=><label key={mode}><input type="radio" name="route-mode" checked={draft.mode===mode} onChange={()=>{patch({mode});setSelectedStop(null);}}/>{mode==='road'?'Real Road Routing':'Synthetic Demo'}</label>)}</div>
          {draft.mode==='road' && <><div className="form-grid"><label>Depot longitude<input value={draft.depotLon} onChange={e=>patch({depotLon:e.target.value})}/></label><label>Depot latitude<input value={draft.depotLat} onChange={e=>patch({depotLat:e.target.value})}/></label></div><button className="button secondary" type="button" disabled={locating} onClick={locate}>{locating?'Finding location…':'Use My Current Location'}</button><p className="small muted">Map selection or coordinates. Address lookup is not configured.</p></>}
          <div className="form-grid"><label>Delivery stops<input aria-label="Delivery stops" type="number" min="5" max={draft.mode==='road'?99:200} value={draft.numStops||''} onChange={e=>patch({numStops:Number(e.target.value)})}/><small>{draft.mode==='road'?'5–99':'5–200'} stops</small></label><label>Number of drivers<input type="number" min="1" max="20" value={draft.numDrivers||''} onChange={e=>patch({numDrivers:Number(e.target.value)})}/></label></div>
          <label>Workload policy<select value={draft.workloadMode||'balanced'} onChange={e=>patch({workloadMode:e.target.value as PlanDraft['workloadMode']})}><option value="balanced">Balanced range</option><option value="fixed">Fixed balanced counts</option></select></label>
          <p className="small muted">Empty driver routes are allowed. Capacity and time windows are not supported.</p>
          {draft.mode==='road' && <><label>How to add stops<select value={draft.stopEntry} onChange={e=>patch({stopEntry:e.target.value as PlanDraft['stopEntry']})}><option value="map">Map selection</option><option value="manual">Manual coordinates</option><option value="nearby">Nearby sample stops</option></select></label>{draft.stopEntry==='nearby' && <><label>Radius in kilometers<input type="number" min="1" max="50" value={draft.radius} onChange={e=>patch({radius:Number(e.target.value)})}/></label><button type="button" className="button secondary" onClick={nearby}>Generate {draft.numStops} sample stops</button><p className="small muted">Simulated locations, not customer addresses. Road routing still requires OSRM.</p></>}</>}
          <details><summary>Reproducibility options</summary>{draft.mode==='synthetic' && <label>Stop layout<select value={draft.layout} onChange={e=>patch({layout:e.target.value as PlanDraft['layout']})}><option value="uniform">Uniform</option><option value="clustered">Clustered</option></select></label>}<label>Random seed<input value={draft.seed} onChange={e=>patch({seed:e.target.value})}/></label><p className="small muted">Recreates generated synthetic locations. Zero is valid. Nearby road samples are random.</p></details>
        </fieldset>
        <section className="delivery-list" aria-label="Delivery stops"><h2>Delivery stops</h2><p className="small muted">{draft.mode==='road'?`${draft.stops.length} of ${draft.numStops} placed · Draft order`:'Generated synthetic coordinates'} — not the calculated driving sequence.</p>
          <div ref={list} className="delivery-rows">{draft.mode==='road' ? draft.stops.map((stop,index)=><div className={`stop-row delivery-row ${selectedStop===index+1?'selected':''}`} data-stop={index+1} key={index}>
            <button type="button" className="stop-focus" aria-label={`Focus delivery stop ${index+1}`} aria-pressed={selectedStop===index+1} onClick={()=>selectStop(index+1)}>{index+1}</button>
            <div className="stop-coordinates"><label htmlFor={`lon-${index}`}>Longitude</label><input id={`lon-${index}`} disabled={p.busy} value={stop.lon} onChange={e=>patch({stops:draft.stops.map((s,i)=>i===index?{...s,lon:e.target.value}:s)})}/><label htmlFor={`lat-${index}`}>Latitude</label><input id={`lat-${index}`} disabled={p.busy} value={stop.lat} onChange={e=>patch({stops:draft.stops.map((s,i)=>i===index?{...s,lat:e.target.value}:s)})}/></div>
            <button className="text-button" disabled={p.busy} aria-label={`Remove stop ${index+1}`} onClick={()=>void remove(index)}>Remove</button>
          </div>) : syntheticStops.map(stop=><button key={stop.stop_id} data-stop={stop.stop_id} className={`synthetic-stop ${selectedStop===stop.stop_id?'selected':''}`} aria-pressed={selectedStop===stop.stop_id} onClick={()=>selectStop(stop.stop_id)}><strong>{stop.stop_id}</strong><span>{stop.x.toFixed(2)}, {stop.y.toFixed(2)}</span></button>)}</div>
          {draft.mode==='road' ? <button type="button" className="button secondary" disabled={p.busy || draft.stops.length>=99} onClick={()=>patch({stops:[...draft.stops,{lon:'',lat:''}]})}>Add stop</button> : <p className="small muted">Generate Plan to create coordinates. Change the count, layout or seed to regenerate; arbitrary synthetic coordinate editing is not supported by the existing API.</p>}
        </section>
        {result && instance && <section className="workspace-results" aria-label="Calculated route results"><h2>Route results</h2>{editingMap && <button className="text-button" onClick={()=>setEditing(false)}>View calculated routes</button>}<CompactResults result={result} instance={instance} results={p.results}/><RouteExplanation instance={instance} result={result} baseline={p.results.get('nearest_neighbor')} onFocus={selectDriver}/><p className="small muted">Calculated sequence below. Draft order above is unchanged.</p><DriverDetailsPanel result={result} instance={instance} selectedDriverId={p.driver} onDriverSelect={selectDriver} selectedStopId={selectedStop} onStopSelect={selectStop}/></section>}
        {current && <details className="workspace-advanced"><summary>Advanced routing and diagnostics</summary><div className="actions">{(['nearest_neighbor','2opt'] as Method[]).map(method=><button key={method} className="button secondary" disabled={p.busy} onClick={()=>p.onRun(method)}>{method==='2opt'?'2-Opt':'Nearest Neighbor'}</button>)}</div><OptimizationControls budget={p.budget} setBudget={p.setBudget} busy={p.busy} job={p.job} error={p.optimizationError} onRun={p.onRun} onCancel={p.onCancel}/>{result && <OptimizationDetails result={result} mode={instance!.mode}/>}</details>}
        {error && <p role="alert" className="notice error">{error}</p>}
        {p.optimizationError && <p role="alert" className="notice error">{p.optimizationError}</p>}
        {p.job && <p role="status" className="small">{p.stale ? 'Previous optimization' : 'Optimization'} {statusText(p.job.status)} · {statusText(p.job.stage)}</p>}
      </div>
      <div className="planning-actions"><button className="button primary" disabled={p.busy||locating} onClick={()=>void generate()}>Generate Plan</button><button className="button primary" disabled={!current||!result||p.busy} onClick={()=>{setEditing(false);p.onRun('vnd');}}>Optimize Routes</button>{activeStatus(p.job?.status) ? <button className="button secondary" disabled={p.job?.status==='cancelling'} onClick={p.onCancel}>Cancel Optimization</button> : <button className="button secondary" disabled={!current||p.busy} onClick={()=>{setEditing(true);setExpanded(true);}}>Edit Plan</button>}</div>
    </aside>
    <div className="workspace-map" aria-label="Live plan map">
      {draft.mode==='road' && editingMap ? <LocationPicker readOnly={p.busy} selectedStop={selectedStop==null?null:selectedStop-1} onStopSelect={index=>selectStop(index+1)} depotLat={draft.depotLat} depotLon={draft.depotLon} stops={draft.stops}
        onDepotChange={(lat,lon)=>patch({depotLat:String(lat),depotLon:String(lon)})}
        onStopAdd={(lat,lon)=>{if(draft.stops.length<99)patch({stops:[...draft.stops,{lat:String(lat),lon:String(lon)}]});}}
        onStopMove={(index,lat,lon)=>patch({stops:draft.stops.map((s,i)=>i===index?{lat:String(lat),lon:String(lon)}:s)})}
        onStopRemove={index=>void remove(index)} onDepotClear={async()=>{if(await confirm('Clear the selected depot?'))patch({depotLat:'',depotLon:''});}}
        onStopsClear={async()=>{if(await confirm('Remove all delivery stops?')){patch({stops:[]});setSelectedStop(null);}}}/>
      : current ? <RouteVisualization instance={instance} routingResult={result} selectedMethod={p.method} availableMethods={[...p.results.keys()]} onMethodSelect={value=>p.onMethod(value as Method)} selectedDriverId={p.driver} onDriverSelect={selectDriver} selectedStopId={selectedStop} onStopSelect={selectStop}/>
      : <div className="synthetic-empty"><h2>Synthetic coordinate map</h2><p>Generate Plan to display the generated depot and stops.</p><p className="small">Cartesian coordinates · map units · not real streets</p></div>}
      {draft.mode==='road' && editingMap && <span className="map-state">Draft locations · road routes appear after calculation</span>}
    </div>
  </section>;
}
