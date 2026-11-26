// Browser acceptance capture only. Data comes from an audited saved live trial.
// This module is never imported by the product or its production entrypoint.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { ControllerEvidence } from '../src/components/OptimizationDetails';

const row = await (await fetch('/__quality/evidence')).json();
document.getElementById('root')!.style.display = 'none';
const host = document.createElement('div');
document.body.append(host);
createRoot(host).render(<main className="app-main"><section className="panel stack">
  <h1>Recorded adaptive search</h1>
  <p className="notice">Saved real Ollama development measurement · read-only evidence display.
    This is not a new inference request or a route result for the current plan.</p>
  <p>{row.case_id} · seed {row.seed} · {row.arm}</p>
  <p>{row.total_distance.toFixed(2)} map units · {row.operations.toLocaleString()} operations · {row.status}</p>
  <p className="small mono">Problem {row.problem_fingerprint}</p>
  <ControllerEvidence evidence={row.controller}/>
</section></main>);
