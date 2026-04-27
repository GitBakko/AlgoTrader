// SignalsAndFeed.jsx — SignalsPerAsset (heatmap-style grid) + FeedSegnali (timeline)

// ─────────────────────────────────────────────────────────────
// SignalsPerAsset — compact heatmap grid (decided for user)
// ─────────────────────────────────────────────────────────────

function SignalsPerAsset({ filter='all' }) {
  // Three states: hold (gray), executed (green glow), rejected (red), closed (cyan)
  const items = ASSET_UNIVERSE.map(a => ({
    ...a,
    last: LAST_SIGNALS[a.epic] || { dir:'HOLD', conf:0, state:'hold', time:'--' },
  }));
  const filtered = filter==='all' ? items
    : filter==='active' ? items.filter(i=>['executed','rejected','closed'].includes(i.last.state))
    : items.filter(i=>i.last.state===filter);

  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)', borderRadius:6,
    padding:'10px 12px', display:'flex', flexDirection:'column', gap:8,
  }}>
    <Label right={<div style={{display:'flex',gap:6,fontFamily:'var(--mantis-font-mono)'}}>
      <FilterChip active={filter==='all'} label="ALL"/>
      <FilterChip active={filter==='active'} label="ACTIVE"/>
      <FilterChip active={filter==='hold'} label="HOLD"/>
    </div>}>Ultimo Segnale per Asset · {filtered.length}</Label>
    <div style={{display:'grid',gridTemplateColumns:'repeat(3, 1fr)',gap:6}}>
      {filtered.map(item => <SignalCell key={item.epic} item={item}/>)}
    </div>
  </div>;
}

function FilterChip({ active, label }) {
  return <span style={{
    padding:'2px 6px',borderRadius:3,fontSize:9,fontWeight:700,letterSpacing:'0.1em',
    fontFamily:'var(--mantis-font-mono)',cursor:'pointer',
    background: active ? 'rgba(57,255,20,0.1)' : 'rgba(255,255,255,0.03)',
    color: active ? '#39FF14' : 'rgba(255,255,255,0.5)',
    border: `1px solid ${active?'rgba(57,255,20,0.3)':'rgba(255,255,255,0.08)'}`,
  }}>{label}</span>;
}

function SignalCell({ item }) {
  const sc = stateColor(item.last.state);
  const dc = dirColor(item.last.dir);
  const isActive = ['executed','rejected','closed'].includes(item.last.state);
  return <div style={{
    background: isActive ? `${sc}0a` : 'rgba(255,255,255,0.015)',
    border: `1px solid ${isActive?`${sc}33`:'rgba(255,255,255,0.06)'}`,
    borderRadius: 4, padding: '6px 8px', display:'flex', alignItems:'center', gap:8,
    fontFamily:'var(--mantis-font-mono)', position:'relative',
  }}>
    <AssetGlyph epic={item.epic} size={20}/>
    <div style={{flex:1,minWidth:0,display:'flex',flexDirection:'column',gap:2}}>
      <div style={{display:'flex',alignItems:'center',gap:6}}>
        <span style={{fontSize:10,fontWeight:700,color:'#fff'}}>{item.epic}</span>
        <span style={{
          padding:'1px 4px',borderRadius:2,fontSize:8,fontWeight:700,letterSpacing:'0.08em',
          background:`${dc}14`,color:dc,border:`1px solid ${dc}26`,
        }}>{item.last.dir}</span>
        {isActive && <PulseDot color={sc} size={5}/>}
      </div>
      {/* Confidence bar */}
      <div style={{height:2,background:'rgba(255,255,255,0.06)',borderRadius:1,overflow:'hidden'}}>
        <div style={{width:`${item.last.conf}%`,height:'100%',background:item.last.conf>=50?'#39FF14':item.last.conf>=30?'#FFB020':'#8B949E'}}/>
      </div>
    </div>
    <div style={{display:'flex',flexDirection:'column',alignItems:'flex-end',gap:1}}>
      <span style={{fontSize:9,color:'rgba(255,255,255,0.5)',fontFeatureSettings:'"tnum" 1'}}>{item.last.conf}%</span>
      <span style={{fontSize:8,fontWeight:700,letterSpacing:'0.08em',textTransform:'uppercase',color:sc}}>{item.last.state}</span>
    </div>
  </div>;
}

// ─────────────────────────────────────────────────────────────
// FeedSegnali — timeline-style log (decided for user)
// ─────────────────────────────────────────────────────────────

function FeedSegnali({ feed = FEED, limit = 11 }) {
  const items = feed.slice(0, limit);
  const counts = items.reduce((acc,i)=>{acc[i.state]=(acc[i.state]||0)+1;return acc;},{});
  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)', borderRadius:6,
    padding:'10px 12px', display:'flex', flexDirection:'column', gap:8,
  }}>
    <Label right={<div style={{display:'flex',gap:6}}>
      <Chip label="EXEC" value={counts.executed||0} color="#39FF14" bg="rgba(57,255,20,0.08)" border="rgba(57,255,20,0.2)"/>
      <Chip label="REJ" value={counts.rejected||0} color="#FF3D57" bg="rgba(255,61,87,0.08)" border="rgba(255,61,87,0.2)"/>
      <Chip label="HOLD" value={counts.hold||0} color="#8B949E"/>
    </div>}>Feed Segnali · LIVE</Label>
    <div style={{display:'flex',flexDirection:'column',gap:0,position:'relative'}}>
      {/* timeline rail */}
      <div style={{position:'absolute',left:54,top:8,bottom:8,width:1,background:'rgba(255,255,255,0.06)'}}/>
      {items.map((s,i) => <FeedRow key={i} s={s} isLast={i===items.length-1}/>)}
    </div>
  </div>;
}

function FeedRow({ s, isLast }) {
  const sc = stateColor(s.state);
  const dc = dirColor(s.dir);
  const isImportant = s.state==='executed' || s.state==='rejected';
  return <div style={{
    display:'grid', gridTemplateColumns:'46px 16px 1fr', gap:8, alignItems:'center',
    padding:'7px 4px', borderBottom: isLast?'none':'1px solid rgba(255,255,255,0.04)',
    fontFamily:'var(--mantis-font-mono)',
    background: isImportant ? `${sc}06` : 'transparent',
  }}>
    {/* Time */}
    <span style={{fontSize:10,color:'rgba(255,255,255,0.5)',fontFeatureSettings:'"tnum" 1'}}>{s.time}</span>
    {/* Bullet on rail */}
    <div style={{display:'flex',justifyContent:'center',position:'relative',zIndex:1}}>
      <div style={{
        width:9,height:9,borderRadius:'50%', background:'#0d1117',
        border:`2px solid ${sc}`, boxShadow:isImportant?`0 0 8px ${sc}99`:'none',
      }}/>
    </div>
    {/* Content */}
    <div style={{display:'grid',gridTemplateColumns:'80px 1fr 50px 90px 90px 1fr',alignItems:'center',gap:10}}>
      <div style={{display:'flex',alignItems:'center',gap:6}}>
        <AssetGlyph epic={s.epic} size={16}/>
        <span style={{fontSize:10,fontWeight:700,color:'#fff'}}>{s.epic}</span>
      </div>
      <span style={{fontSize:9,color:'rgba(255,255,255,0.4)',padding:'1px 5px',background:'rgba(255,255,255,0.03)',border:'1px solid rgba(255,255,255,0.06)',borderRadius:2,letterSpacing:'0.05em',width:'fit-content'}}>{s.strategy}</span>
      <span style={{
        fontSize:9,fontWeight:700,padding:'1px 5px',borderRadius:2,letterSpacing:'0.08em',width:'fit-content',
        background:`${dc}1a`,color:dc,border:`1px solid ${dc}33`,
      }}>{s.dir}</span>
      <span style={{fontSize:10,color:s.conf>=50?'#39FF14':s.conf>=30?'#FFB020':'rgba(255,255,255,0.4)',fontWeight:700,fontFeatureSettings:'"tnum" 1'}}>{s.conf}%</span>
      <span style={{fontSize:10,color:'#fff',fontFeatureSettings:'"tnum" 1'}}>{typeof s.price === 'number' ? s.price : '—'}</span>
      <span style={{fontSize:9,color: isImportant ? sc : 'rgba(255,255,255,0.45)',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{s.detail}</span>
    </div>
  </div>;
}

// ─────────────────────────────────────────────────────────────
// ModelsChip — replaces the verbose 21-row table
// ─────────────────────────────────────────────────────────────

function ModelsChip() {
  const allOk = PAPER_STATE.modelsLoaded === PAPER_STATE.modelsTotal;
  return <button style={{
    display:'inline-flex',alignItems:'center',gap:8,padding:'6px 10px',
    background: allOk ? 'rgba(57,255,20,0.06)' : 'rgba(255,176,32,0.08)',
    border: `1px solid ${allOk?'rgba(57,255,20,0.25)':'rgba(255,176,32,0.3)'}`,
    borderRadius:4, fontFamily:'var(--mantis-font-mono)', cursor:'pointer',
  }}>
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="2" width="5" height="5" rx="1" fill={allOk?'#39FF14':'#FFB020'} opacity="0.8"/>
      <rect x="9" y="2" width="5" height="5" rx="1" fill={allOk?'#39FF14':'#FFB020'} opacity="0.8"/>
      <rect x="2" y="9" width="5" height="5" rx="1" fill={allOk?'#39FF14':'#FFB020'} opacity="0.8"/>
      <rect x="9" y="9" width="5" height="5" rx="1" fill={allOk?'#39FF14':'#FFB020'} opacity="0.8"/>
    </svg>
    <span style={{fontSize:9,letterSpacing:'0.14em',textTransform:'uppercase',color:'rgba(255,255,255,0.55)',fontWeight:700}}>Modelli ML</span>
    <span style={{fontSize:11,fontWeight:700,color:'#fff',fontFeatureSettings:'"tnum" 1'}}>{PAPER_STATE.modelsLoaded}/{PAPER_STATE.modelsTotal}</span>
    <span style={{fontSize:11,color:allOk?'#39FF14':'#FFB020'}}>{allOk?'✓':'!'}</span>
    <span style={{fontSize:9,color:'rgba(255,255,255,0.4)',marginLeft:2}}>v1 · 199 features · 26/04</span>
    <svg width="10" height="10" viewBox="0 0 10 10" style={{opacity:0.5,marginLeft:2}}><path d="M2 4l3 3 3-3" stroke="#fff" strokeWidth="1.4" fill="none" strokeLinecap="round"/></svg>
  </button>;
}

Object.assign(window, { SignalsPerAsset, FeedSegnali, ModelsChip });
