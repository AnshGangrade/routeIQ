import { useEffect, useRef, useState } from 'react';
import { ScaleControl, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Icon } from './Design';

const pin = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="48" viewBox="0 0 40 48"><path d="M20 46S3 29 3 20a17 17 0 1 1 34 0c0 9-17 26-17 26Z" fill="#B95E42" stroke="#fffaf0" stroke-width="2.5"/><path d="m10 20 10-9 10 9M13 18v12h14V18M18 30v-8h5v8" fill="none" stroke="#fffaf0" stroke-width="2" stroke-linejoin="round"/></svg>';
export const atlasDepotIcon = L.icon({iconUrl:'data:image/svg+xml;charset=UTF-8,'+encodeURIComponent(pin),iconSize:[40,48],iconAnchor:[20,46],popupAnchor:[0,-40],className:'atlas-depot'});
export const atlasStopIcon = (number: number, color = '#287776', selected = true) => L.divIcon({
  className: `atlas-stop ${selected ? 'emphasized' : 'subdued'}`,
  html:`<span style="--marker-color:${/^#[0-9a-f]{6}$/i.test(color)?color:'#287776'}">${Number.isInteger(number)?number:''}</span>`,
  iconSize:[32,32],iconAnchor:[16,16],popupAnchor:[0,-16],
});
export const tileURL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

/** Bounds are always obtained from actual points or returned geometry. */
export function MapUtilities({ points, autoFit = true }: { points: Array<[number,number]>; autoFit?: boolean }) {
  const map = useMap();
  const controls = useRef<HTMLDivElement>(null);
  const [natural, setNatural] = useState(false);
  const valid = points.filter(p => p.every(Number.isFinite));
  const signature = JSON.stringify(valid);
  const fit = () => { if (valid.length) map.fitBounds(valid, {padding:[38,38],maxZoom:16,animate:false}); };
  useEffect(() => { if (autoFit) fit(); }, [map, signature, autoFit]);
  useEffect(() => {
    const container = map.getContainer();
    const observer = new ResizeObserver(() => map.invalidateSize({pan:false}));
    observer.observe(container);
    if (controls.current) { L.DomEvent.disableClickPropagation(controls.current); L.DomEvent.disableScrollPropagation(controls.current); }
    return () => observer.disconnect();
  }, [map]);
  useEffect(() => { map.getContainer().classList.toggle('map-natural',natural); },[map,natural]);
  return <><ScaleControl position="bottomleft" imperial={false}/><div ref={controls} className="map-tools leaflet-top leaflet-right"><button type="button" onClick={fit} disabled={!valid.length} aria-label="Fit selected locations" title="Fit selected locations"><Icon name="focus"/></button><button type="button" aria-pressed={natural} aria-label="Original map colors" title="Toggle original map colors" onClick={()=>setNatural(v=>!v)}><Icon name="layers"/></button></div></>;
}
