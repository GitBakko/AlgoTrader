// PositionCard.jsx — la card ricca per ogni posizione aperta
// Campi richiesti dall'utente:
//   1. Entry value
//   2. SL value (€ + %)
//   3. TP value (€ + %)
//   4. Trend della posizione (sparkline + direzione)
//   5. Age (tempo dall'apertura)
//   6. Trailing stop on/off
//   7. Current value (€ + %)

function PositionCard({ p, density='comfortable' }) {
  const inProfit = p.cur_eur >= 0;
  const profitColor = inProfit ? '#39FF14' : '#FF3D57';
  const dirColor_ = dirColor(p.dir);
  // Risk:Reward
  const risk = Math.abs(p.sl_eur);
  const reward = Math.abs(p.tp_eur);
  const rr = (reward / risk).toFixed(2);
  // % distance to SL / TP from current
  const distToSL = Math.abs((p.sl - p.current) / p.current * 100);
  const distToTP = Math.abs((p.tp - p.current) / p.current * 100);

  return <div style={{
    background:'#161b22',
    border:`1px solid rgba(${inProfit?'57,255,20':'255,61,87'},0.18)`,
    borderLeft:`3px solid ${profitColor}`,
    borderRadius:6, padding:'12px 14px',
    display:'grid', gridTemplateColumns:'180px 1fr 200px 180px 140px', gap:18,
    alignItems:'center', position:'relative',
  }}>
    {/* COLUMN 1 — Asset + dir + size + age */}
    <div style={{display:'flex',flexDirection:'column',gap:6}}>
      <div style={{display:'flex',alignItems:'center',gap:8}}>
        <AssetGlyph epic={p.epic} size={28}/>
        <div style={{display:'flex',flexDirection:'column',lineHeight:1}}>
          <span style={{fontSize:14,fontWeight:700,color:'#fff',fontFamily:'var(--mantis-font-mono)',letterSpacing:'0.02em'}}>{p.epic}</span>
          <span style={{fontSize:9,color:'rgba(255,255,255,0.4)',marginTop:2,fontFamily:'var(--mantis-font-mono)',letterSpacing:'0.1em',textTransform:'uppercase'}}>conf {p.confidence}%</span>
        </div>
      </div>
      <div style={{display:'flex',alignItems:'center',gap:5}}>
        <span style={{
          padding:'2px 7px', borderRadius:3, fontSize:9, fontWeight:700, letterSpacing:'0.12em',
          background: `${dirColor_}1a`, color: dirColor_, border:`1px solid ${dirColor_}33`,
          fontFamily:'var(--mantis-font-mono)',
        }}>{p.dir}</span>
        <span style={{fontSize:10,color:'rgba(255,255,255,0.55)',fontFamily:'var(--mantis-font-mono)',fontFeatureSettings:'"tnum" 1'}}>
          {typeof p.size==='number' && p.size>=100 ? p.size.toLocaleString('it-IT') : p.size}
        </span>
      </div>
      <div style={{display:'flex',alignItems:'center',gap:6,fontFamily:'var(--mantis-font-mono)',fontSize:9}}>
        <span style={{color:'rgba(255,255,255,0.35)',letterSpacing:'0.1em',textTransform:'uppercase',fontWeight:700}}>age</span>
        <span style={{color:'rgba(255,255,255,0.7)'}}>{fmtAge(p.age_min)}</span>
        {p.trailing && <span style={{
          padding:'1px 5px',borderRadius:2,fontSize:8,fontWeight:700,letterSpacing:'0.1em',
          background:'rgba(0,229,255,0.1)',color:'#00E5FF',border:'1px solid rgba(0,229,255,0.3)',
        }}>TRAIL ●</span>}
        {!p.trailing && <span style={{
          padding:'1px 5px',borderRadius:2,fontSize:8,fontWeight:700,letterSpacing:'0.1em',
          background:'rgba(139,148,158,0.08)',color:'rgba(255,255,255,0.35)',border:'1px solid rgba(255,255,255,0.08)',
        }}>TRAIL ○</span>}
      </div>
    </div>

    {/* COLUMN 2 — SL ←→ Entry ←→ Current ←→ TP visualization */}
    <div style={{display:'flex',flexDirection:'column',gap:5}}>
      <PositionRange entry={p.entry} current={p.current} sl={p.sl} tp={p.tp} dir={p.dir} w={260}/>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:6,fontFamily:'var(--mantis-font-mono)'}}>
        <div style={{display:'flex',flexDirection:'column'}}>
          <span style={{fontSize:8,letterSpacing:'0.12em',color:'#FF3D57',textTransform:'uppercase',fontWeight:700}}>STOP LOSS</span>
          <span style={{fontSize:11,color:'#fff',fontWeight:700,fontFeatureSettings:'"tnum" 1'}}>{p.sl}</span>
          <span style={{fontSize:9,color:'#FF3D57',fontFeatureSettings:'"tnum" 1'}}>{fmtEur(p.sl_eur)} · {fmtPct(p.sl_pct)}</span>
        </div>
        <div style={{display:'flex',flexDirection:'column',borderLeft:'1px solid rgba(255,255,255,0.08)',borderRight:'1px solid rgba(255,255,255,0.08)',padding:'0 8px'}}>
          <span style={{fontSize:8,letterSpacing:'0.12em',color:'rgba(255,255,255,0.5)',textTransform:'uppercase',fontWeight:700}}>ENTRY</span>
          <span style={{fontSize:11,color:'#fff',fontWeight:700,fontFeatureSettings:'"tnum" 1'}}>{p.entry}</span>
          <span style={{fontSize:9,color:'rgba(255,255,255,0.4)'}}>marker ⬤</span>
        </div>
        <div style={{display:'flex',flexDirection:'column'}}>
          <span style={{fontSize:8,letterSpacing:'0.12em',color:'#39FF14',textTransform:'uppercase',fontWeight:700}}>TAKE PROFIT</span>
          <span style={{fontSize:11,color:'#fff',fontWeight:700,fontFeatureSettings:'"tnum" 1'}}>{p.tp}</span>
          <span style={{fontSize:9,color:'#39FF14',fontFeatureSettings:'"tnum" 1'}}>{fmtEur(p.tp_eur)} · {fmtPct(p.tp_pct)}</span>
        </div>
      </div>
    </div>

    {/* COLUMN 3 — Trend (sparkline + direction we're betting) */}
    <div style={{display:'flex',flexDirection:'column',gap:4}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
        <span style={{fontSize:9,fontWeight:700,letterSpacing:'0.14em',textTransform:'uppercase',color:'rgba(255,255,255,0.5)',fontFamily:'var(--mantis-font-mono)'}}>Trend 1H</span>
        <span style={{
          fontSize:9,fontFamily:'var(--mantis-font-mono)',fontWeight:700,
          color: (p.trendDir==='down'&&p.dir==='SELL')||(p.trendDir==='up'&&p.dir==='BUY') ? '#39FF14' : '#FF3D57',
        }}>
          {p.trendDir==='up' ? '↗ UP' : p.trendDir==='down' ? '↘ DOWN' : '→ FLAT'}
          <span style={{marginLeft:4,color:'rgba(255,255,255,0.4)'}}>vs {p.dir}</span>
        </span>
      </div>
      <Sparkline data={p.trend} w={200} h={36} color={inProfit?'#39FF14':'#FF3D57'}/>
      <div style={{display:'flex',justifyContent:'space-between',fontFamily:'var(--mantis-font-mono)',fontSize:8,color:'rgba(255,255,255,0.4)'}}>
        <span>min {Math.min(...p.trend).toFixed(p.epic==='NVDA'?2:3)}</span>
        <span>max {Math.max(...p.trend).toFixed(p.epic==='NVDA'?2:3)}</span>
      </div>
    </div>

    {/* COLUMN 4 — Current value (the headline number) */}
    <div style={{display:'flex',flexDirection:'column',gap:4,padding:'8px 12px',background:`${profitColor}0a`,border:`1px solid ${profitColor}1f`,borderRadius:4}}>
      <span style={{fontSize:9,fontWeight:700,letterSpacing:'0.14em',textTransform:'uppercase',color:profitColor,fontFamily:'var(--mantis-font-mono)'}}>P&L corrente</span>
      <span style={{fontSize:22,fontWeight:700,color:profitColor,fontFamily:'var(--mantis-font-mono)',fontFeatureSettings:'"tnum" 1',lineHeight:1}}>{fmtEur(p.cur_eur)}</span>
      <span style={{fontSize:11,color:profitColor,fontWeight:700,fontFamily:'var(--mantis-font-mono)',fontFeatureSettings:'"tnum" 1'}}>{fmtPct(p.cur_pct,3)}</span>
      <span style={{fontSize:8,color:'rgba(255,255,255,0.45)',fontFamily:'var(--mantis-font-mono)',marginTop:2}}>quote {p.current}</span>
    </div>

    {/* COLUMN 5 — meta + actions */}
    <div style={{display:'flex',flexDirection:'column',gap:4,fontFamily:'var(--mantis-font-mono)'}}>
      <div style={{display:'flex',justifyContent:'space-between',fontSize:9}}>
        <span style={{color:'rgba(255,255,255,0.4)',letterSpacing:'0.08em',textTransform:'uppercase',fontWeight:700}}>R:R</span>
        <span style={{color:'#fff',fontWeight:700}}>1:{rr}</span>
      </div>
      <div style={{display:'flex',justifyContent:'space-between',fontSize:9}}>
        <span style={{color:'rgba(255,255,255,0.4)',letterSpacing:'0.08em',textTransform:'uppercase',fontWeight:700}}>→ SL</span>
        <span style={{color:'#FF3D57',fontWeight:700}}>{distToSL.toFixed(2)}%</span>
      </div>
      <div style={{display:'flex',justifyContent:'space-between',fontSize:9}}>
        <span style={{color:'rgba(255,255,255,0.4)',letterSpacing:'0.08em',textTransform:'uppercase',fontWeight:700}}>→ TP</span>
        <span style={{color:'#39FF14',fontWeight:700}}>{distToTP.toFixed(2)}%</span>
      </div>
      <button style={{
        marginTop:2,padding:'4px 8px',borderRadius:3,fontSize:9,fontWeight:700,letterSpacing:'0.08em',
        background:'rgba(255,61,87,0.08)',color:'#FF3D57',border:'1px solid rgba(255,61,87,0.25)',
        fontFamily:'var(--mantis-font-mono)',cursor:'pointer',
      }}>CLOSE NOW</button>
    </div>
  </div>;
}

// ─────────────────────────────────────────────────────────────
// PositionsList — header + cards
// ─────────────────────────────────────────────────────────────

function PositionsList({ positions = OPEN_POSITIONS, totalPnl }) {
  const total = totalPnl ?? positions.reduce((s,p)=>s+p.cur_eur,0);
  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)', borderRadius:6,
    padding:'10px 12px', display:'flex', flexDirection:'column', gap:8,
  }}>
    <div style={{display:'flex',alignItems:'baseline',justifyContent:'space-between'}}>
      <Label>Posizioni Aperte <span style={{
        marginLeft:6,padding:'1px 6px',background:'rgba(0,229,255,0.1)',color:'#00E5FF',borderRadius:2,
        border:'1px solid rgba(0,229,255,0.3)',fontSize:9,fontWeight:700,
      }}>{positions.length}</span></Label>
      <div style={{display:'flex',alignItems:'baseline',gap:6,fontFamily:'var(--mantis-font-mono)'}}>
        <span style={{fontSize:9,letterSpacing:'0.14em',textTransform:'uppercase',color:'rgba(255,255,255,0.5)',fontWeight:700}}>P&L Totale</span>
        <span style={{fontSize:14,fontWeight:700,color:total>=0?'#39FF14':'#FF3D57',fontFeatureSettings:'"tnum" 1'}}>{fmtEur(total)}</span>
      </div>
    </div>
    <div style={{display:'flex',flexDirection:'column',gap:8}}>
      {positions.map((p,i) => <PositionCard key={i} p={p}/>)}
    </div>
  </div>;
}

Object.assign(window, { PositionCard, PositionsList });
