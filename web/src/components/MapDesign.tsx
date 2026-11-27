import { useEffect, useRef, useState } from 'react';
import { ScaleControl, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Icon } from './Design';

const pin = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="48" viewBox="0 0 40 48"><path d="M20 46S3 29 3 20a17 17 0 1 1 34 0c0 9-17 26-17 26Z" fill="#202326" stroke="#FFFFFF" stroke-width="2.5"/><circle cx="20" cy="19" r="7" fill="#16C65B"/></svg>';
export const atlasDepotIcon = L.icon({iconUrl:'data:image/svg+xml;charset=UTF-8,'+encodeURIComponent(pin),iconSize:[40,48],iconAnchor:[20,46],popupAnchor:[0,-40],className:'atlas-depot'});
export const atlasStopIcon = (number: number, color = '#08783D', selected = true, focused = false) => L.divIcon({
  className: `atlas-stop ${selected ? 'emphasized' : 'subdued'} ${focused ? 'focused-stop' : ''}`,
  html:`<span style="--driver-color:${/^#[0-9a-f]{6}$/i.test(color)?color:'#697078'}">${Number.isInteger(number)?number:''}</span>`,
  iconSize:[32,32],iconAnchor:[16,16],popupAnchor:[0,-16],
});
export const tileURL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

export function SelectedLocation({ point }: { point: [number,number] | null }) {
  const map = useMap();
  const signature = JSON.stringify(point);
  useEffect(() => { if (point) map.setView(point, Math.max(15, map.getZoom()), {animate:false}); }, [map, signature]);
  return null;
}

/** Bounds are always obtained from actual points or returned geometry. */
export function MapUtilities({ points, autoFit = true }: { points: Array<[number,number]>; autoFit?: boolean }) {
  const map = useMap();
  const controls = useRef<HTMLDivElement>(null);
  const [contrast, setContrast] = useState(false);
  const valid = points.filter(p => p.every(Number.isFinite));
  const signature = JSON.stringify(valid);
  const fit = () => { if (valid.length) map.fitBounds(valid, {padding:[38,38],maxZoom:16,animate:false}); };
  const resizeFit = useRef(() => {});
  resizeFit.current = () => { if (autoFit) fit(); };
  useEffect(() => { if (autoFit) fit(); }, [map, signature, autoFit]);
  useEffect(() => {
    const container = map.getContainer();
    const observer = new ResizeObserver(([entry]) => {
      if (!entry.contentRect.width || !entry.contentRect.height) return;
      map.invalidateSize({pan:false});
      resizeFit.current();
    });
    observer.observe(container);
    if (controls.current) { L.DomEvent.disableClickPropagation(controls.current); L.DomEvent.disableScrollPropagation(controls.current); }
    return () => observer.disconnect();
  }, [map]);
  useEffect(() => { map.getContainer().classList.toggle('map-contrast',contrast); },[map,contrast]);
  return <><ScaleControl position="bottomleft" imperial={false}/><div ref={controls} className="map-tools leaflet-top leaflet-right"><button type="button" onClick={fit} disabled={!valid.length} aria-label="Fit selected locations" title="Fit selected locations"><Icon name="focus"/></button><button type="button" aria-pressed={contrast} aria-label="Higher map contrast" title="Higher map contrast" onClick={()=>setContrast(v=>!v)}><Icon name="layers"/></button></div></>;
}
