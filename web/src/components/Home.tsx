import { Icon } from './Design';

/** Original decorative SVG study. Deliberately isolated from all geographic views. */
export function AtlasArtwork() {
  const points=[[70,250],[180,120],[240,340],[350,200],[420,80],[490,310]];
  return <svg className="atlas-art" viewBox="0 0 560 440" role="img" aria-label="Decorative route network, not a geographic map or route result">
    <circle className="network-orbit" cx="280" cy="220" r="180"/><circle className="network-orbit" cx="280" cy="220" r="120"/>
    <path d="M70 250 180 120 350 200 420 80M70 250 240 340 490 310 350 200 240 340M180 120 240 340" fill="none" stroke="#E1DFD7" strokeWidth="1.5"/>
    <path d="M70 250Q90 110 180 120T350 200Q440 190 490 310" fill="none" stroke="#191919" strokeWidth="2.5"/>
    {points.map(([x,y],i)=><g key={i}><circle cx={x} cy={y} r={i===0?14:8} fill={i===0?'#D9B65A':'#F6F5F0'} stroke="#191919" strokeWidth="2"/><circle cx={x} cy={y} r="2" fill="#191919"/></g>)}
  </svg>;
}

export function Home({ hasInstance }: { hasInstance: boolean }) {
  return <section className="home"><div className="home-hero"><div className="hero-copy"><h1>RouteIQ</h1><p className="home-intro">Plan deliveries across drivers using road distances or a synthetic demo.</p><div className="actions"><a className="button primary" href="#setup">Create route plan <Icon name="arrow" size={18}/></a>{hasInstance && <a className="text-button" href="#routes">Return to current routes</a>}</div><p className="hero-footnote">Compare validated routes, inspect each driver's itinerary, and test routing strategies.</p><a className="text-button" href="#lab">Strategy Experiments</a></div><figure className="hero-atlas"><AtlasArtwork/><figcaption>Illustration only</figcaption></figure></div></section>;
}
