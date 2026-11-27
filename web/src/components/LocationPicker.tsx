import { useEffect, useState } from 'react';
import { parseCoordinatePair } from '../services/inputs';
import 'leaflet/dist/leaflet.css';
import { MapContainer, TileLayer, Marker, useMapEvents, useMap, Popup } from 'react-leaflet';
import { atlasDepotIcon as depotIcon, atlasStopIcon as stopIcon, MapUtilities, SelectedLocation, tileURL } from './MapDesign';
import { Icon } from './Design';

interface LocationPickerProps {
  selectedStop?: number | null;
  onStopSelect?: (index: number) => void;
  readOnly?: boolean;
  depotLat: string;
  depotLon: string;
  stops: Array<{ lon: string; lat: string }>;
  onDepotChange: (lat: number, lon: number) => void;
  onStopAdd: (lat: number, lon: number) => void;
  onStopRemove: (index: number) => void;
  onDepotClear?: () => void;
  onStopsClear?: () => void;
  onStopMove: (index: number, lat: number, lon: number) => void;
}

function MapClickHandler({
  mode,
  onDepotClick,
  onStopClick,
}: {
  mode: 'depot' | 'stop' | 'none';
  onDepotClick: (lat: number, lon: number) => void;
  onStopClick: (lat: number, lon: number) => void;
}) {
  useMapEvents({
    click(e) {
      if (mode === 'depot') {
        onDepotClick(e.latlng.lat, e.latlng.lng);
      } else if (mode === 'stop') {
        onStopClick(e.latlng.lat, e.latlng.lng);
      }
    },
  });
  return null;
}

export function LocationPicker({
  depotLat,
  depotLon,
  stops,
  onDepotChange,
  onStopAdd,
  onStopRemove,
  onStopMove,
  onDepotClear,
  onStopsClear,
  readOnly = false,
  selectedStop = null,
  onStopSelect,
}: LocationPickerProps) {
  const [clickMode, setClickMode] = useState<'depot' | 'stop' | 'none'>('none');
  const [tileError, setTileError] = useState(false);

  const depot = parseCoordinatePair(depotLon, depotLat);
  const hasValidDepot = !!depot;
  // Neutral world overview is a viewport, never a selected default depot.
  const centerLat = depot?.[1] ?? 0;
  const centerLon = depot?.[0] ?? 0;

  return (
    <div className="location-picker stack">
      {!hasValidDepot && <p className="small muted">World view — no depot selected. Zoom to your area, enter coordinates, or explicitly use your current location.</p>}
      {tileError && <p className="notice" role="status">Map background unavailable. You can still enter coordinates manually or move existing markers.</p>}
      {/* Mode buttons */}
      {!readOnly && <div className="map-mode-controls">
        <button
          type="button"
          aria-pressed={clickMode === 'depot'}
          onClick={() => setClickMode(clickMode === 'depot' ? 'none' : 'depot')}
          className={`flex-1 px-3 py-2 text-sm rounded-md border transition-colors ${
            clickMode === 'depot'
              ? 'bg-[var(--color-primary)] text-[var(--color-text)] border-[var(--color-text)]'
              : 'bg-white text-[var(--color-text)] border-[var(--color-border)] hover:bg-[var(--color-surface-secondary)]'
          }`}
        >
          {clickMode === 'depot' ? 'Click map for depot' : 'Set Depot'}
        </button>
        <button
          type="button"
          aria-pressed={clickMode === 'stop'}
          disabled={stops.length >= 99}
          onClick={() => setClickMode(clickMode === 'stop' ? 'none' : 'stop')}
          className={`flex-1 px-3 py-2 text-sm rounded-md border transition-colors ${
            clickMode === 'stop'
              ? 'bg-[var(--color-primary)] text-[var(--color-text)] border-[var(--color-text)]'
              : 'bg-white text-[var(--color-text)] border-[var(--color-border)] hover:bg-[var(--color-surface-secondary)]'
          }`}
        >
          {clickMode === 'stop' ? 'Click map for stops' : 'Add Stops'}
        </button>
        {clickMode !== 'none' && (
          <button
            type="button"
            onClick={() => setClickMode('none')}
            className="px-3 py-2 text-sm rounded-md border border-[var(--color-border)] bg-white text-[var(--color-text)] hover:bg-[var(--color-surface-secondary)]"
          >
            Cancel
          </button>
        )}
      </div>}

      {/* Instruction text */}
      {!readOnly && clickMode !== 'none' && (
        <div className="text-xs text-[var(--color-text)] bg-[var(--color-surface-secondary)] border border-[var(--color-border)] rounded p-2">
          {clickMode === 'depot' 
            ? 'Click anywhere on the map to set the depot location'
            : 'Click anywhere on the map to add a delivery stop'
          }
        </div>
      )}

      {/* Map */}
      <div className="location-map" role="region" aria-label="Depot and delivery stop editor">
        <MapContainer
          center={[centerLat, centerLon]}
          zoom={hasValidDepot ? 13 : 2}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            eventHandlers={{ tileerror: () => setTileError(true) }}
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url={tileURL}
          />
          
          <MapUtilities autoFit={true} points={[...(depot ? [[depot[1],depot[0]] as [number,number]] : []), ...stops.map(s => parseCoordinatePair(s.lon,s.lat)).filter((p): p is [number,number] => !!p).map(([lon,lat]) => [lat,lon] as [number,number])]}/>{!readOnly && <Recenter lat={centerLat} lon={centerLon} selected={hasValidDepot} />}
          <MapClickHandler
            mode={readOnly ? 'none' : clickMode}
            onDepotClick={(lat, lon) => {
              onDepotChange(lat, lon);
              setClickMode('none');
            }}
            onStopClick={(lat, lon) => {
              onStopAdd(lat, lon);
            }}
          />
          <SelectedLocation point={selectedStop != null && stops[selectedStop] ? (() => { const p=parseCoordinatePair(stops[selectedStop].lon,stops[selectedStop].lat);return p ? [p[1],p[0]] : null; })() : null}/>

          {/* Depot marker */}
          {hasValidDepot && (
            <Marker
              position={[parseFloat(depotLat), parseFloat(depotLon)]}
              icon={depotIcon}
              title="Depot"
              alt="Depot"
              draggable={!readOnly}
              eventHandlers={{
                dragend: (e) => {
                  const marker = e.target;
                  const position = marker.getLatLng();
                  onDepotChange(position.lat, position.lng);
                },
              }}
            >
              <Popup>
                <div className="text-sm">
                  <strong className="text-[var(--color-text)]">Depot</strong>
                  <br />
                  {readOnly ? 'Selected depot' : 'Drag to reposition'}
                </div>
              </Popup>
            </Marker>
          )}

          {/* Stop markers */}
          {stops.map((stop, idx) => {
            const pair = parseCoordinatePair(stop.lon, stop.lat);
            if (!pair) return null;
            const [lon, lat] = pair;

            return (
              <Marker
                key={idx}
                position={[lat, lon]}
                icon={stopIcon(idx + 1, undefined, true, selectedStop === idx)}
                title={`Delivery stop ${idx + 1}`}
                alt={`Delivery stop ${idx + 1}`}
                draggable={!readOnly}
                eventHandlers={{
                  click: () => onStopSelect?.(idx),
                  dragend: (e) => {
                    const marker = e.target;
                    const position = marker.getLatLng();
                    onStopMove(idx, position.lat, position.lng);
                  },
                }}
              >
                <Popup>
                  <div className="text-sm">
                    <strong>Stop {idx + 1}</strong>
                    <br />
                    Lat: {lat.toFixed(6)}
                    <br />
                    Lon: {lon.toFixed(6)}
                    <br />
                    {!readOnly && <button
                      type="button"
                      onClick={() => onStopRemove(idx)}
                      className="mt-2 text-xs text-[var(--color-text)] hover:underline underline"
                    >
                      Remove
                    </button>}
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MapContainer>
      </div>

      {/* Summary */}
      <div className="text-sm text-[var(--color-text-muted)] space-y-1">
        <div className="flex items-center justify-between">
          <span>Depot: {hasValidDepot ? 'Set' : 'Not set'}</span>
          {hasValidDepot && !readOnly && onDepotClear && (
            <button
              type="button"
              onClick={onDepotClear}
              className="text-xs text-[var(--color-text)] hover:underline"
            >
              <Icon name="close" size={14}/> Clear
            </button>
          )}
        </div>
        <div className="flex items-center justify-between">
          <span>Stops: {stops.filter(s => s.lat && s.lon).length} placed</span>
          {stops.length > 0 && !readOnly && (
            <button
              type="button"
              onClick={() => {
                if (onStopsClear) { onStopsClear(); return; }
                for (let i = stops.length - 1; i >= 0; i--) {
                  onStopRemove(i);
                }
              }}
              className="text-xs text-[var(--color-text)] hover:underline"
            >
              Clear All
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Recenter({ lat, lon, selected }: { lat: number; lon: number; selected: boolean }) {
  const map = useMap();
  useEffect(() => { map.setView([lat, lon], selected ? Math.max(12, map.getZoom()) : 2); }, [map, lat, lon, selected]);
  return null;
}
