import { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, Pane, Polyline, Popup } from 'react-leaflet';
import L from 'leaflet';
import { atlasDepotIcon as depotIcon, atlasStopIcon as createStopIcon, MapUtilities, SelectedLocation, tileURL } from './MapDesign';
import { driverColor, mapRouteStyle } from '../services/presentation';
import 'leaflet/dist/leaflet.css';
import type { InstanceResponse, RoutingResultResponse } from '../types/api';

interface InteractiveMapProps {
  selectedStopId?: number | null;
  onStopSelect?: (id: number) => void;
  instance: InstanceResponse | null;
  routingResult: RoutingResultResponse | null;
  selectedDriverId: number | null;
  onDriverSelect: (driverId: number | null) => void;
  configVisible?: boolean; // Track config panel visibility for resize
}

export function InteractiveMap({
  instance,
  routingResult,
  selectedDriverId,
  onDriverSelect,
  configVisible,
  selectedStopId = null,
  onStopSelect,
}: InteractiveMapProps) {
  const mapRef = useRef<L.Map | null>(null);
  const [tileError, setTileError] = useState(false);

  // Invalidate map size when config panel visibility changes
  useEffect(() => {
    if (mapRef.current) {
      // Small delay to allow layout to settle
      setTimeout(() => {
        mapRef.current?.invalidateSize();
      }, 100);
    }
  }, [configVisible]);

  if (!instance || instance.mode !== 'road') {
    return null; // Don't show map for synthetic mode
  }

  // Get depot coordinates
  const depotLat = instance.depot.lat ?? instance.depot.y;
  const depotLon = instance.depot.lon ?? instance.depot.x;

  if (depotLat == null || depotLon == null || !Number.isFinite(depotLat) || !Number.isFinite(depotLon))
    return <p role="alert" className="notice error">The selected road plan has no valid depot. Create a valid plan before displaying its map.</p>;
  const center: L.LatLngTuple = [depotLat, depotLon];

  return (
    <div>
    {tileError && <p className="notice" role="status">Map background unavailable. Your location markers and route data are still shown.</p>}
    <div className="road-map">
      <MapContainer
        center={center}
        zoom={13}
        style={{ height: '100%', width: '100%' }}
        ref={(map) => { mapRef.current = map; }}
        whenReady={() => {
          // Ensure map is properly sized on initial load
          setTimeout(() => {
            mapRef.current?.invalidateSize();
          }, 100);
        }}
      >
        <TileLayer
          eventHandlers={{ tileerror: () => setTileError(true) }}
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url={tileURL}
        />

        <MapUtilities points={[
          [depotLat,depotLon],
          ...instance.stops.filter(s => selectedDriverId === null || routingResult?.drivers.find(d => d.driver_id === selectedDriverId)?.route.includes(s.stop_id)).map(s => [s.y,s.x] as [number,number]),
          ...(routingResult?.drivers.filter(d => selectedDriverId === null || d.driver_id === selectedDriverId).flatMap(d => !d.geometry_error ? (d.geometry || []).map(p => [p[0],p[1]] as [number,number]) : []) || []),
        ]}/>

        {/* Depot Marker */}
        <Marker 
          position={[depotLat, depotLon]} 
          icon={depotIcon}
          title="Depot"
          alt="Depot"
        >
          <Popup>
            <div className="text-sm">
              <strong className="text-[#151515]">Depot</strong>
              <br />
              Lat: {depotLat.toFixed(6)}
              <br />
              Lon: {depotLon.toFixed(6)}
            </div>
          </Popup>
        </Marker>

        {/* Stop Markers */}
        {instance.stops.map((stop) => {
          const stopLat = stop.y;
          const stopLon = stop.x;
          
          // Find which driver this stop belongs to
          const driver = instance.drivers.find(d => 
            routingResult?.drivers.find(dr => 
              dr.driver_id === d.driver_id && 
              dr.route.includes(stop.stop_id)
            )
          );
          
          const color = driver ? driverColor(driver.driver_id) : '#686868';
          const isSelected = driver && (selectedDriverId === null || selectedDriverId === driver.driver_id);
          
          return (
            <Marker
              key={stop.stop_id}
              position={[stopLat, stopLon]}
              icon={createStopIcon(stop.stop_id, color, !!isSelected, selectedStopId === stop.stop_id)}
              title={`Delivery stop ${stop.stop_id}`}
              alt={`Delivery stop ${stop.stop_id}`}
              eventHandlers={{
                click: () => { if (driver) onDriverSelect(driver.driver_id); onStopSelect?.(stop.stop_id); },
              }}
            >
              <Popup>
                <div className="text-sm">
                  <strong>Stop {stop.stop_id}</strong>
                  <br />
                  Lat: {stopLat.toFixed(6)}
                  <br />
                  Lon: {stopLon.toFixed(6)}
                  {driver && (
                    <>
                      <br />
                      <span style={{ color }}>
                        ● {driver.name}
                      </span>
                    </>
                  )}
                </div>
              </Popup>
            </Marker>
          );
        })}

        {/* Route Polylines - use OSRM geometry if available */}
        <Pane name="route-casings" style={{zIndex:410,pointerEvents:'none'}}>
          {routingResult?.drivers.map(driver => {
            const style=mapRouteStyle(routingResult.method,selectedDriverId===null || selectedDriverId===driver.driver_id);
            if(!style.casing || !driver.geometry || driver.geometry.length<2 || driver.geometry_error)return null;
            return <Polyline key={driver.driver_id} positions={driver.geometry.map(coord=>[coord[0],coord[1]])} pathOptions={{color:'#151515',weight:7,opacity:1,className:'route-casing'}} interactive={false}/>;
          })}
        </Pane>
        <Pane name="route-strokes" style={{zIndex:420}}>
        {routingResult && routingResult.drivers.map(driver => {
          const driverInfo = instance.drivers.find(d => d.driver_id === driver.driver_id);
          const isSelected = selectedDriverId === null || selectedDriverId === driver.driver_id;
          const style = mapRouteStyle(routingResult.method,isSelected);

          // Missing geometry stays missing: never draw straight-line road routes.
          if (!driver.geometry || driver.geometry.length < 2 || driver.geometry_error) return null;
          const positions: L.LatLngTuple[] = driver.geometry.map(coord => [coord[0], coord[1]]);

          const distanceKm = driver.distance >= 1000 
            ? (driver.distance / 1000).toFixed(2) + ' km'
            : driver.distance.toFixed(0) + ' m';
          
          const durationMin = driver.duration != null
            ? (driver.duration / 60).toFixed(0) + ' min'
            : null;
          
          const routingStatus = 'OSRM road geometry';

          return (
            <Polyline
              key={driver.driver_id}
              positions={positions}
              pathOptions={{color:style.color,weight:style.weight,opacity:style.opacity,dashArray:style.dashArray,className:'route-path'}}
              eventHandlers={{click:()=>onDriverSelect(driver.driver_id)}}
            >
              <Popup>
                <div className="text-sm">
                  <strong>{driverInfo?.name}</strong>
                  <br />
                  Distance: {distanceKm}
                  {durationMin && (
                    <>
                      <br />
                      Duration: {durationMin}
                    </>
                  )}
                  <br />
                  Stops: {driver.route.filter(id => id !== 0).length}
                  <br />
                  <span className="text-xs text-[#686868]">
                    {routingStatus}
                  </span>
                </div>
              </Popup>
            </Polyline>
          );
        })}
        </Pane>
        <SelectedLocation point={(() => {const s=instance.stops.find(s=>s.stop_id===selectedStopId);return s ? [s.y,s.x] : null;})()}/>
      </MapContainer>
    </div>
    </div>
  );
}
