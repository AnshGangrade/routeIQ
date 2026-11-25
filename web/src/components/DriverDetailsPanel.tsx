import { driverColor } from '../services/presentation';
import { formatDistance } from '../services/distance';
import type { RoutingResultResponse, InstanceResponse } from '../types/api';
interface Props { result: RoutingResultResponse; instance: InstanceResponse | null; selectedDriverId: number | null; onDriverSelect: (id: number | null) => void; selectedStopId?: number | null; onStopSelect?: (id:number)=>void; }
export function DriverDetailsPanel({ result, instance, selectedDriverId, onDriverSelect, selectedStopId, onStopSelect }: Props) {
  if (!instance) return null;
  return <aside className="panel driver-panel" aria-label="Driver routes"><div className="section-heading"><h2>Your drivers</h2>{selectedDriverId !== null && <button className="text-button" onClick={() => onDriverSelect(null)}>Show all</button>}</div><p className="small muted">Select a driver to focus the map.</p>
    <div className="driver-list">{result.drivers.map(driver => {
      const info = instance.drivers.find(d => d.driver_id === driver.driver_id);
      const selected = selectedDriverId === driver.driver_id;
      const stopCount = driver.route.filter(id => id !== 0).length;
      return <div key={driver.driver_id} className={`driver-item ${selected ? 'selected' : ''}`}><button className="driver-select" aria-pressed={selected} onClick={() => onDriverSelect(selected ? null : driver.driver_id)}><span className="driver-dot" style={{ background: driverColor(driver.driver_id) }} /><span><strong>{info?.name || `Driver ${driver.driver_id + 1}`}</strong><small>{stopCount} stops · {formatDistance(driver.distance, instance.mode)}</small></span><span aria-hidden="true">{selected ? '−' : '+'}</span></button>
        {selected && <div className="driver-itinerary"><h3>Stop sequence</h3><ol>{driver.route.map((stopId, index) => <li key={index}>{stopId === 0 ? index === 0 ? 'Start at depot' : 'Return to depot' : <button type="button" className="text-button" aria-pressed={selectedStopId===stopId} onClick={()=>onStopSelect?.(stopId)}>{`Delivery stop ${stopId}`}</button>}</li>)}</ol>{driver.duration != null && <p>{Math.round(driver.duration / 60)} min driving time</p>}{driver.geometry_error && <p className="small">Road path unavailable: {driver.geometry_error}</p>}</div>}
      </div>;
    })}</div>
  </aside>;
}
