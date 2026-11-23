import { Icon, useConfirm } from './Design';
import { useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { LocationPicker } from './LocationPicker';
import { parseCoordinatePair } from '../services/inputs';
import { validatePlan } from '../services/workflow';
import type { PlanDraft } from '../services/workflow';

const steps = ['Routing mode', 'Depot & stops', 'Drivers', 'Review'];
interface Props { draft: PlanDraft; setDraft: Dispatch<SetStateAction<PlanDraft>>; step: number;
  setStep: (step: number) => void; onGenerate: () => void; busy: boolean; hasInstance: boolean; }

export function SetupWizard({ draft, setDraft, step, setStep, onGenerate, busy, hasInstance }: Props) {
  const confirm = useConfirm();
  const [error, setError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const patch = (values: Partial<PlanDraft>) => setDraft(previous => ({ ...previous, ...values }));
  const move = (next: number) => { setError(null); setStep(next); };
  const locate = () => {
    if (!navigator.geolocation) { setError('Location is unavailable. Enter the depot coordinates instead.'); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(position => {
      patch({ depotLat: position.coords.latitude.toFixed(6), depotLon: position.coords.longitude.toFixed(6) });
      setLocating(false);
    }, () => { setError('Could not get your location. You can enter coordinates or choose a depot on the map.'); setLocating(false); }, { timeout: 10000 });
  };
  const nearby = async () => {
    const depot = parseCoordinatePair(draft.depotLon, draft.depotLat);
    if (!depot || !Number.isFinite(draft.radius) || draft.radius < 1 || draft.radius > 50 || !Number.isInteger(draft.numStops) || draft.numStops < 5 || draft.numStops > 99) {
      setError('Set a valid depot, 5–99 stops, and a radius between 1 and 50 km first.'); return;
    }
    if (draft.stops.length && !await confirm('Replace the existing stops with new sample locations?')) return;
    patch({ stops: Array.from({ length: draft.numStops }, () => {
      const angle = Math.random() * Math.PI * 2;
      const radius = Math.sqrt(Math.random()) * draft.radius / 111;
      return { lon: (depot[0] + radius * Math.cos(angle)).toFixed(6), lat: (depot[1] + radius * Math.sin(angle)).toFixed(6) };
    }) });
    setError(null);
  };
  const summary = <dl className="plan-facts">
    <div><dt>Routing mode</dt><dd>{draft.mode === 'road' ? 'Real road routing' : 'Synthetic demo'}</dd></div>
    <div><dt>Delivery stops</dt><dd>{draft.numStops || 'Not set'}{draft.mode === 'road' && ` · ${draft.stops.length} placed`}</dd></div>
    <div><dt>Drivers</dt><dd>{draft.numDrivers || 'Not set'}</dd></div>
    <div><dt>Depot</dt><dd>{draft.mode === 'synthetic' ? 'Generated automatically' : parseCoordinatePair(draft.depotLon, draft.depotLat) ? `${draft.depotLat}, ${draft.depotLon}` : 'Not set'}</dd></div>
    <div><dt>Distances</dt><dd>{draft.mode === 'road' ? 'Road distance · m / km' : 'Straight-line · map units'}</dd></div>
  </dl>;

  return <section className={`setup-screen setup-step-${step}`} aria-labelledby="setup-title">
    <div className="page-heading"><div><p className="eyebrow">Build your route plan</p><h1 id="setup-title">A few details. A clear plan.</h1><p>Set up your deliveries in four short steps.</p></div>{hasInstance && <a className="button secondary" href="#routes">Back to current routes</a>}</div>
    <ol className="stepper" aria-label="Setup progress">{steps.map((name, index) => <li key={name} aria-current={step === index ? 'step' : undefined}>
      <button type="button" disabled={index > step || busy} onClick={() => move(index)}><span>{index < step ? <Icon name="check" size={15}/> : index + 1}</span><span>{name}</span></button>
    </li>)}</ol>
    <div className="wizard-layout">
      <form className="panel wizard-panel" onSubmit={async event => {
        event.preventDefault(); const invalid = validatePlan(draft, step); setError(invalid);
        if (!invalid) { if (step < 3) move(step + 1); else if (!hasInstance || await confirm('Generate a new selected plan? The current displayed routes will be replaced.')) onGenerate(); }
      }} noValidate>
        <fieldset disabled={busy}>
          <legend className="eyebrow">Step {step + 1} of 4</legend>
          <h2>{['How would you like to plan?', 'Where are your deliveries?', 'Who is making the deliveries?', 'Ready to generate your routes?'][step]}</h2>
          {step === 0 && <div className="mode-options">
            {(['synthetic', 'road'] as const).map(mode => <label key={mode} className={`choice-card ${draft.mode === mode ? 'chosen' : ''}`}>
              <input type="radio" name="route-mode" checked={draft.mode === mode} onChange={() => patch({ mode })} />
              <span className="mode-icon"><Icon name={mode === "road" ? "map" : "route"} size={27}/></span><span><strong>{mode === 'synthetic' ? 'Synthetic Demo' : 'Real Road Routing'}</strong><small>{mode === 'synthetic' ? 'Try a generated depot and sample stops. No addresses needed. Distances use a simple coordinate map.' : 'Choose real locations and calculate distances along roads. Requires the road-routing service and internet access.'}</small></span>
            </label>)}
          </div>}
          {step === 1 && <div className="stack">
            <p className="muted">{draft.mode === 'synthetic' ? 'We’ll generate one depot and delivery stops for you. A depot is where every driver starts and finishes.' : 'Every route starts and finishes at your depot. Place stops on the map or enter their coordinates.'}</p>
            <div className="form-grid"><label>Delivery stops<input aria-label="Delivery stops" type="number" min="5" max={draft.mode === 'road' ? 99 : 200} value={draft.numStops || ''} onChange={e => patch({ numStops: Number(e.target.value) })} /><small>{draft.mode === 'road' ? '5–99' : '5–200'} stops, excluding the depot</small></label>
              {draft.mode === 'synthetic' && <label>Stop layout<select value={draft.layout} onChange={e => patch({ layout: e.target.value as PlanDraft['layout'] })}><option value="uniform">Spread across the map</option><option value="clustered">Grouped in neighborhoods</option></select></label>}
            </div>
            {draft.mode === 'road' && <>
              <div className="form-grid"><label>Depot longitude<input value={draft.depotLon} onChange={e => patch({ depotLon: e.target.value })} placeholder="−180 to 180" /></label><label>Depot latitude<input value={draft.depotLat} onChange={e => patch({ depotLat: e.target.value })} placeholder="−90 to 90" /></label></div>
              <p className="small muted">Choose locations on the map or enter longitude/latitude. Address lookup is not configured. Your location is requested only when you press the button below.</p>
              <button className="button secondary fit" type="button" disabled={locating} onClick={locate}>{locating ? 'Finding your location…' : 'Use my current location'}</button>
              <label>How to add stops<select value={draft.stopEntry} onChange={e => patch({ stopEntry: e.target.value as PlanDraft['stopEntry'] })}><option value="map">Place on map</option><option value="manual">Enter coordinates</option><option value="nearby">Generate sample stops nearby</option></select></label>
              {draft.stopEntry === 'map' && <LocationPicker depotLat={draft.depotLat} depotLon={draft.depotLon} stops={draft.stops}
                onDepotChange={(lat, lon) => patch({ depotLat: String(lat), depotLon: String(lon) })}
                onDepotClear={async () => { if (await confirm('Clear the selected depot?')) patch({ depotLat: '', depotLon: '' }); }}
                onStopsClear={async () => { if (await confirm('Remove all delivery stops?')) patch({ stops: [] }); }}
                onStopAdd={(lat, lon) => { if (draft.stops.length >= 99) { setError('Road mode supports up to 99 stops.'); return; } setDraft(prev => ({ ...prev, stops: [...prev.stops, { lat: String(lat), lon: String(lon) }] })); }}
                onStopRemove={async index => { if (await confirm(`Remove delivery stop ${index + 1}?`)) setDraft(prev => ({ ...prev, stops: prev.stops.filter((_, i) => i !== index) })); }}
                onStopMove={(index, lat, lon) => setDraft(prev => ({ ...prev, stops: prev.stops.map((stop, i) => i === index ? { lat: String(lat), lon: String(lon) } : stop) }))} />}
              {draft.stopEntry === 'nearby' && <div className="notice"><p>These are simulated delivery locations near your depot, not customer addresses. They still use road routing.</p><label>Radius in kilometers<input type="number" min="1" max="50" value={draft.radius || ''} onChange={e => patch({ radius: Number(e.target.value) })} /></label><button type="button" className="button secondary" onClick={nearby}>Generate {draft.numStops} sample stops</button></div>}
              {draft.stopEntry !== 'map' && <div className="stop-editor"><p>{draft.stops.length} of {draft.numStops} stops placed</p>{draft.stops.map((stop, index) => <div className="stop-row" key={index}>
                <span>{index + 1}</span><label className="sr-only" htmlFor={`lon-${index}`}>Stop {index + 1} longitude</label><input id={`lon-${index}`} value={stop.lon} placeholder="Longitude" onChange={e => patch({ stops: draft.stops.map((s, i) => i === index ? { ...s, lon: e.target.value } : s) })} />
                <label className="sr-only" htmlFor={`lat-${index}`}>Stop {index + 1} latitude</label><input id={`lat-${index}`} value={stop.lat} placeholder="Latitude" onChange={e => patch({ stops: draft.stops.map((s, i) => i === index ? { ...s, lat: e.target.value } : s) })} />
                <button type="button" aria-label={`Remove stop ${index + 1}`} className="text-button" onClick={async () => { if (await confirm(`Remove delivery stop ${index + 1}?`)) patch({ stops: draft.stops.filter((_, i) => i !== index) }); }}>Remove</button>
              </div>)}<button className="button secondary" type="button" disabled={draft.stops.length >= 99} onClick={() => patch({ stops: [...draft.stops, { lon: '', lat: '' }] })}>Add stop</button></div>}
            </>}
            <details><summary>Reproducibility options</summary><label>Random seed<input value={draft.seed} onChange={e => patch({ seed: e.target.value })} /><small>The same seed recreates a synthetic layout. Leave blank for a new random layout. Zero is valid.</small></label></details>
          </div>}
          {step === 2 && <div className="stack"><p className="muted">Stops are divided between drivers. Every driver returns to the same depot.</p><label className="narrow-field">Number of drivers<input type="number" min="1" max="20" value={draft.numDrivers || ''} onChange={e => patch({ numDrivers: Number(e.target.value) })} /></label><p className="notice">{draft.numStops} delivery stops · {draft.numDrivers || 'No'} drivers{draft.numDrivers > draft.numStops ? '. Some drivers will have no deliveries.' : ''}</p>
            <label>Workload policy<select value={draft.workloadMode || 'balanced'} onChange={e => patch({ workloadMode: e.target.value as PlanDraft['workloadMode'] })}><option value="balanced">Balanced range for every driver</option><option value="fixed">Fixed balanced counts by driver</option></select></label>
            {draft.numDrivers > 0 && <p className="small muted">Each driver serves {Math.floor(draft.numStops / draft.numDrivers)}–{Math.ceil(draft.numStops / draft.numDrivers)} stops. {draft.workloadMode === 'fixed' ? 'Any extra stops go to the first driver slots; their exact counts are fixed.' : 'The optimizer can exchange stops within this range.'} Empty routes are allowed. Capacity and time windows are not supported.</p>}
          </div>}
          {step === 3 && <div className="stack">{summary}<p className="notice">We’ll calculate a quick starting route (Nearest Neighbor), then try shortening it with 2-Opt. You can compare the actual results afterwards.</p>{hasInstance && <p className="muted">Generating replaces the selected plan and its displayed routes. Your evolution run stays available.</p>}</div>}
          {step === 3 && draft.mode === 'road' && <div className="review-map"><h3>Review your locations</h3><p className="small muted">Location preview only. Road routes are calculated after generation.</p><LocationPicker readOnly depotLat={draft.depotLat} depotLon={draft.depotLon} stops={draft.stops} onDepotChange={() => {}} onStopAdd={() => {}} onStopRemove={() => {}} onStopMove={() => {}} /></div>}
          {error && <p className="notice error" role="alert">{error}</p>}
          <div className="wizard-actions"><button type="button" className="button secondary" onClick={() => step > 0 ? move(step - 1) : window.location.assign('#home')}>Back</button><button className="button primary" type="submit">{busy ? 'Working…' : step === 3 ? 'Generate routes' : 'Continue'}</button></div>
        </fieldset>
      </form>
      <aside className="panel draft-summary"><Icon name="map" size={32}/><div className="summary-rule"/><p className="eyebrow">Your plan so far</p>{summary}<p className={`draft-validation ${validatePlan(draft) ? "pending" : "valid"}`}><Icon name={validatePlan(draft) ? "info" : "check"} size={16}/>{validatePlan(draft) ? "A few details still need attention" : "Ready to generate"}</p><p className="muted small">Your entries stay here when you move between screens. Keep this tab open to retain your work.</p></aside>
    </div>
  </section>;
}
