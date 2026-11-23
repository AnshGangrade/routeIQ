import { BrandMark, Icon } from './Design';

/** Original decorative SVG study. Deliberately isolated from all geographic views. */
export function AtlasArtwork() {
  const colors = ['#c7b6d9','#d9c9b6','#d7dfc6','#d0d9dc','#e6c9bb'];
  return <svg className="atlas-art" viewBox="0 0 640 520" role="img" aria-label="Decorative watercolor city study, not a geographic map or route result">
    <defs><filter id="pigment"><feTurbulence type="fractalNoise" baseFrequency=".028" numOctaves="3" seed="8" result="grain"/><feDisplacementMap in="SourceGraphic" in2="grain" scale="2.8"/></filter><pattern id="paper" width="80" height="80" patternUnits="userSpaceOnUse"><path d="M0 20h80M20 0v80" stroke="#a8a38e" strokeOpacity=".08"/></pattern></defs>
    <rect width="640" height="520" rx="28" fill="#f2ecdc"/><rect width="640" height="520" fill="url(#paper)"/>
    <g transform="translate(-30 -25) rotate(-13 320 260)" filter="url(#pigment)">
      {Array.from({length:80},(_,i)=>{const x=35+(i%10)*68,y=28+Math.floor(i/10)*68;return <g key={i}><path d={`M${x+3} ${y+3}l${46+(i%3)*3} 1 -2 43 -45 2Z`} fill={colors[i%5]} fillOpacity=".68" stroke="#728179" strokeWidth=".65"/><path d={`M${x+9} ${y+10}h21v27H${x+9}ZM${x+35} ${y+9}h9v19h-9Z`} fill="#f9f4e6" stroke="#6d7774" strokeWidth=".6" opacity=".8"/></g>})}
      <path d="M-30 300C90 410 165 226 296 270S441 380 490 212 595 80 720 150" fill="none" stroke="#f6f0df" strokeWidth="88"/>
      <path d="M-30 300C90 410 165 226 296 270S441 380 490 212 595 80 720 150" fill="none" stroke="#6fa5ad" strokeOpacity=".65" strokeWidth="60"/>
      <path d="M-30 300C90 410 165 226 296 270S441 380 490 212 595 80 720 150" fill="none" stroke="#82b4b5" strokeWidth="38" strokeOpacity=".6"/>
      <path d="m170 187 44 83M420 270l65 23" stroke="#f9f5e8" strokeWidth="16"/><path d="m170 187 44 83M420 270l65 23" stroke="#7b8c8b" strokeWidth="1.3"/>
      <path d="m280 70 102-8 13 87-113 7Z" fill="#a4b58a" fillOpacity=".8" stroke="#72866c"/>
      {[0,1,2,3,4,5].map(i=><g key={i} transform={`translate(${295+i%3*30} ${89+Math.floor(i/3)*33})`}><circle r="12" fill="#859e74" opacity=".7"/><path d="M0 8V-3m0 2-6-3m6 6 5-3" stroke="#6a7e66" strokeWidth=".8"/></g>)}
      <path d="M140 170 235 150 265 208 372 183 418 244" fill="none" stroke="#287776" strokeWidth="4" strokeLinecap="round" strokeDasharray="1 9"/>
      {[[140,170],[235,150],[372,183],[418,244]].map(([x,y],i)=><g key={i}><circle cx={x} cy={y} r="10" fill="#fbf7ed" stroke={i===0?'#b95e42':'#287776'} strokeWidth="3"/><circle cx={x} cy={y} r="3" fill={i===0?'#b95e42':'#287776'}/></g>)}
    </g><path d="M20 22h32M20 22v32M620 498h-32m32 0v-32" fill="none" stroke="#314e6a" opacity=".45"/>
  </svg>;
}
export function Home({ hasInstance }: { hasInstance: boolean }) {
  return <section className="home">
    <div className="home-hero"><div className="hero-copy"><p className="eyebrow"><span className="ink-rule"/> The art of a better route</p><h1>A clearer path.<br/><em>Every doorstep.</em></h1><p className="home-intro">Turn a map full of delivery stops into a thoughtful plan for your entire fleet.</p><div className="actions"><a className="button primary" href="#setup">Create route plan <Icon name="arrow" size={18}/></a>{hasInstance && <a className="text-button" href="#routes">Return to current routes</a>}</div><p className="hero-footnote">Explore a synthetic demo, or plan on real roads.</p><div className="hero-tags"><span><Icon name="map" size={16}/> Real road routing</span><span><Icon name="drivers" size={16}/> Balanced fleets</span></div></div>
    <figure className="hero-atlas"><AtlasArtwork/><div className="atlas-note"><BrandMark/><span>A little less distance.<br/><strong>A lot more clarity.</strong></span></div><figcaption><span>ROUTEIQ / MAP STUDY 01</span><span>Illustration only</span></figcaption></figure></div>
    <section className="home-features" aria-label="What you can do"><div className="feature-intro"><p className="eyebrow">From places to possibilities</p><h2>One plan.<br/><em>Many better ways.</em></h2><p>Start with your deliveries. Explore what changes when you route them differently.</p></div><div className="feature-list">{[
      ['route','01','Find a shorter way','Compare trusted starting routes with bounded fleet optimization. Every distance is measured on your plan.','#setup'],
      ['drivers','02','Give every driver a clear plan','Balance stop counts, focus individual routes, and follow every delivery back to the depot.','#setup'],
      ['lab','03','Make room for discovery','Explore strategy evolution in a separate research workspace, with visible budgets and honest evidence.','#lab'],
    ].map(([icon,n,title,copy,href])=><a href={href} className="feature-row" key={n}><span className="feature-symbol"><Icon name={icon as 'route'|'drivers'|'lab'} size={25}/></span><div><p className="eyebrow">{n}</p><h3>{title}</h3><p>{copy}</p></div><Icon name="arrow" size={18}/></a>)}</div></section>
  </section>;
}
