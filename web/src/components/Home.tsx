import { Icon } from './Design';

/** Original decorative SVG study. Deliberately isolated from all geographic views. */
export function AtlasArtwork() {
  const points=[[70,250],[180,120],[240,340],[350,200],[420,80],[490,310]];
  return <svg className="atlas-art" viewBox="0 0 560 440" role="img" aria-label="Decorative route network, not a geographic map or route result">
    <circle className="network-orbit" cx="280" cy="220" r="180"/><circle className="network-orbit" cx="280" cy="220" r="120"/>
    <path d="M70 250 180 120 350 200 420 80M70 250 240 340 490 310 350 200 240 340M180 120 240 340" fill="none" stroke="#b8d3c4" strokeWidth="1.5"/>
    <path d="M70 250Q90 110 180 120T350 200Q440 190 490 310" fill="none" stroke="#173F3A" strokeWidth="2.5"/>
    {points.map(([x,y],i)=><g key={i}><circle cx={x} cy={y} r={i===0?14:8} fill={i===0?'#39C99A':'#F3F7F4'} stroke="#173F3A" strokeWidth="2"/><circle cx={x} cy={y} r="2" fill="#173F3A"/></g>)}
  </svg>;
}

export function Home({ hasInstance }: { hasInstance: boolean }) {
  return <section className="home">
    <div className="home-hero"><div className="hero-copy"><p className="eyebrow"><span className="ink-rule"/> The art of a better route</p><h1>A clearer path.<br/><em>Every doorstep.</em></h1><p className="home-intro">Turn a map full of delivery stops into a thoughtful plan for your entire fleet.</p><div className="actions"><a className="button primary" href="#setup">Create route plan <Icon name="arrow" size={18}/></a>{hasInstance && <a className="text-button" href="#routes">Return to current routes</a>}</div><p className="hero-footnote">Explore a synthetic demo, or plan on real roads.</p><div className="hero-tags"><span><Icon name="map" size={16}/> Real road routing</span><span><Icon name="drivers" size={16}/> Balanced fleets</span></div></div>
    <figure className="hero-atlas"><AtlasArtwork/><figcaption><span>QUIET ATLAS / CONNECTIONS</span><span>Illustration only</span></figcaption></figure></div>
    <section className="home-features" aria-label="What you can do"><div className="feature-intro"><p className="eyebrow">From places to possibilities</p><h2>One plan.<br/><em>Many better ways.</em></h2><p>Start with your deliveries. Explore what changes when you route them differently.</p></div><div className="feature-list">{[
      ['route','01','Find a shorter way','Compare trusted starting routes with bounded fleet optimization. Every distance is measured on your plan.','#setup'],
      ['drivers','02','Give every driver a clear plan','Balance stop counts, focus individual routes, and follow every delivery back to the depot.','#setup'],
      ['lab','03','Make room for discovery','Explore strategy evolution in a separate research workspace, with visible budgets and honest evidence.','#lab'],
    ].map(([icon,n,title,copy,href])=><a href={href} className="feature-row" key={n}><span className="feature-symbol"><Icon name={icon as 'route'|'drivers'|'lab'} size={25}/></span><div><p className="eyebrow">{n}</p><h3>{title}</h3><p>{copy}</p></div><Icon name="arrow" size={18}/></a>)}</div></section>
  </section>;
}
