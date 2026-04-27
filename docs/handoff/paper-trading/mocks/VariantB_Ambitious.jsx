// VariantB_Ambitious.jsx — Cockpit-style novel layout for Paper Trading.
// Key novel patterns:
//  • Left rail "Bot Vitals" with vertical heartbeat + risk gauges stack
//  • Center: large position cards (full-width, hero treatment) with timeline
//  • Right rail: live feed timeline + signals heatmap as compact 21-cell mosaic
//  • Top: KPI hex-strip with mini-charts integrated, no separate sections

function PaperVariantB() {
  return <div data-screen-label="02 Paper Trading · B — Ambitious" style={{
    fontFamily:'var(--mantis-font-ui)', background:'#0d1117', color:'#fff', minHeight:'100%',
    display:'flex', flexDirection:'column',
  }}>
    <CockpitHeader/>

    <div style={{padding:'14px',display:'grid',gridTemplateColumns:'260px 1fr 360px',gap:12,flex:1}}>

      {/* LEFT RAIL — Bot Vitals + Risk gauges */}
      <div style={{display:'flex',flexDirection:'column',gap:10}}>
        <BotVitalsPanel/>
        <RiskGaugeStack/>
        <ModelsHealthPanel/>
      </div>

      {/* CENTER — KPI strip + Positions cockpit */}
      <div style={{display:'flex',flexDirection:'column',gap:12}}>
        <KpiStripCompact/>
        <ActivePositionsCockpit/>
        <SignalsHeatmap/>
      </div>

      {/* RIGHT RAIL — Live feed timeline */}
      <div style={{display:'flex',flexDirection:'column',gap:10}}>
        <LiveFeedTimeline/>
      </div>
    </div>

    <Footer/>
  </div>;
}

// ─────────────────────────────────────────────────────────────
// LEFT — Bot Vitals
// ─────────────────────────────────────────────────────────────

function BotVitalsPanel() {
  return <div style={{
    background:'#161b22', border:'1px solid rgba(57,255,20,0.18)', borderRadius:6,
    padding:'12px', display:'flex', flexDirection:'column', gap:10,
    boxShadow:'0 0 24px rgba(57,255,20,0.04) inset',
  }}>
    <div style={{display:'flex',alignItems:'center',gap:8}}>
      <PulseDot color="#39FF14" size={8}/>
      <span style={{fontSize:10,fontWeight:700,letterSpacing:'0.18em',textTransform:'uppercase',color:'#39FF14',fontFamily:'var(--mantis-font-mono)'}}>BOT VITALS</span>
    </div>
    {/* Heartbeat ECG line */}
    <div style={{position:'relative',height:48,background:'#0d1117',border:'1px solid rgba(255,255,255,0.04)',borderRadius:3,overflow:'hidden'}}>
      <svg width="100%" height="48" preserveAspectRatio="none" viewBox="0 0 240 48">
        <line x1="0" y1="24" x2="240" y2="24" stroke="rgba(57,255,20,0.08)" strokeWidth="1"/>
        <polyline points="0,24 30,24 35,24 40,16 45,32 50,8 55,40 60,24 80,24 110,24 115,24 120,16 125,32 130,8 135,40 140,24 170,24 200,24 205,24 210,16 215,32 220,8 225,40 230,24 240,24"
          fill="none" stroke="#39FF14" strokeWidth="1.5" style={{filter:'drop-shadow(0 0 4px rgba(57,255,20,0.6))'}}/>
      </svg>
      <span style={{position:'absolute',top:4,left:6,fontSize:8,color:'rgba(57,255,20,0.6)',fontFamily:'var(--mantis-font-mono)',letterSpacing:'0.1em'}}>HEARTBEAT</span>
      <span style={{position:'absolute',bottom:4,right:6,fontSize:9,color:'#39FF14',fontWeight:700,fontFamily:'var(--mantis-font-mono)'}}>{PAPER_STATE.lastTickAgo.toFixed(1)}s</span>
    </div>
    {/* Iterations & uptime stack */}
    <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:6,fontFamily:'var(--mantis-font-mono)'}}>
      <Stat label="ITER" value={PAPER_STATE.iterations} sub="completed"/>
      <Stat label="INTERVAL" value={`${PAPER_STATE.intervalSec}s`} sub="check pl"/>
      <Stat label="UPTIME" value={PAPER_STATE.uptime} sub="since boot"/>
      <Stat label="ERRORS" value={PAPER_STATE.errors} sub="last 24h" color={PAPER_STATE.errors>0?'#FF3D57':'#39FF14'}/>
    </div>
    {/* Signals donut */}
    <div style={{display:'flex',alignItems:'center',gap:10,padding:'8px',background:'rgba(255,255,255,0.015)',border:'1px solid rgba(255,255,255,0.04)',borderRadius:4}}>
      <SignalsDonut/>
      <div style={{display:'flex',flexDirection:'column',gap:2,flex:1,fontFamily:'var(--mantis-font-mono)'}}>
        <span style={{fontSize:8,letterSpacing:'0.14em',textTransform:'uppercase',color:'rgba(255,255,255,0.5)',fontWeight:700}}>SEGNALI / TRADE</span>
        <span style={{fontSize:18,fontWeight:700,color:'#fff'}}>{PAPER_STATE.signals.total}<span style={{color:'rgba(255,255,255,0.4)',fontSize:11}}> / {PAPER_STATE.signals.executed}</span></span>
        <span style={{fontSize:9,color:'#00E5FF'}}>conv {PAPER_STATE.signals.conversion.toFixed(1)}%</span>
      </div>
    </div>
  </div>;
}

function Stat({ label, value, sub, color='#fff' }) {
  return <div style={{
    background:'rgba(255,255,255,0.015)',border:'1px solid rgba(255,255,255,0.04)',
    borderRadius:3,padding:'6px 8px',display:'flex',flexDirection:'column',gap:2,
  }}>
    <span style={{fontSize:8,letterSpacing:'0.14em',textTransform:'uppercase',color:'rgba(255,255,255,0.5)',fontWeight:700}}>{label}</span>
    <span style={{fontSize:13,fontWeight:700,color,fontFeatureSettings:'"tnum" 1',lineHeight:1}}>{value}</span>
    <span style={{fontSize:8,color:'rgba(255,255,255,0.4)'}}>{sub}</span>
  </div>;
}

function SignalsDonut() {
  // 64 total: 2 executed, 5 rejected, 57 hold
  const total = 64, exec = 2, rej = 5, hold = 57;
  const r = 22, c = 2*Math.PI*r;
  const seg = (n) => (n/total)*c;
  return <svg width="56" height="56" viewBox="0 0 56 56">
    <circle cx="28" cy="28" r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="6"/>
    <circle cx="28" cy="28" r={r} fill="none" stroke="#39FF14" strokeWidth="6"
      strokeDasharray={`${seg(exec)} ${c-seg(exec)}`} transform="rotate(-90 28 28)"/>
    <circle cx="28" cy="28" r={r} fill="none" stroke="#FF3D57" strokeWidth="6"
      strokeDasharray={`${seg(rej)} ${c-seg(rej)}`} strokeDashoffset={-seg(exec)} transform="rotate(-90 28 28)"/>
    <circle cx="28" cy="28" r={r} fill="none" stroke="#8B949E" strokeWidth="6" opacity="0.4"
      strokeDasharray={`${seg(hold)} ${c-seg(hold)}`} strokeDashoffset={-(seg(exec)+seg(rej))} transform="rotate(-90 28 28)"/>
    <text x="28" y="32" textAnchor="middle" fill="#fff" fontSize="13" fontFamily="var(--mantis-font-mono)" fontWeight="700">{total}</text>
  </svg>;
}

// ─────────────────────────────────────────────────────────────
// LEFT — Risk Gauge stack
// ─────────────────────────────────────────────────────────────

function RiskGaugeStack() {
  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)', borderRadius:6,
    padding:'12px', display:'flex', flexDirection:'column', gap:8,
  }}>
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
      <span style={{fontSize:10,fontWeight:700,letterSpacing:'0.18em',textTransform:'uppercase',color:'rgba(57,255,20,0.7)',fontFamily:'var(--mantis-font-mono)'}}>RISK COCKPIT</span>
      <span style={{fontSize:9,color:'rgba(255,255,255,0.5)',fontFamily:'var(--mantis-font-mono)'}}>4 rules</span>
    </div>
    <RiskGauge label="Circuit Breakers" value="0/6" pct={0} color="#39FF14" status="ARMED"/>
    <RiskGauge label="Equity Filter" value="19.4%" sub="DD vs 20% cap" pct={97} color="#FFB020" status="WARN"/>
    <RiskGauge label="Kelly Sizing" value="14%" sub="avg · win 60.4%" pct={14} color="#00E5FF" status="ATTIVO"/>
    <RiskGauge label="Trading Stops" value="0" sub="active stops" pct={0} color="#39FF14" status="OK"/>
  </div>;
}

function RiskGauge({ label, value, sub, pct, color, status }) {
  return <div style={{
    background:'rgba(255,255,255,0.015)',border:'1px solid rgba(255,255,255,0.05)',
    borderLeft:`2px solid ${color}`,borderRadius:3,padding:'7px 10px',
    display:'flex',flexDirection:'column',gap:5,fontFamily:'var(--mantis-font-mono)',
  }}>
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
      <span style={{fontSize:9,fontWeight:700,letterSpacing:'0.12em',textTransform:'uppercase',color:'rgba(255,255,255,0.6)'}}>{label}</span>
      <span style={{fontSize:8,fontWeight:700,letterSpacing:'0.1em',color,padding:'1px 5px',background:`${color}1a`,borderRadius:2}}>{status}</span>
    </div>
    <div style={{display:'flex',alignItems:'baseline',gap:5}}>
      <span style={{fontSize:15,fontWeight:700,color:'#fff',fontFeatureSettings:'"tnum" 1',lineHeight:1}}>{value}</span>
      {sub && <span style={{fontSize:8,color:'rgba(255,255,255,0.4)'}}>{sub}</span>}
    </div>
    {pct > 0 && <div style={{height:2,background:'rgba(255,255,255,0.06)',borderRadius:1,overflow:'hidden'}}>
      <div style={{width:`${Math.min(pct,100)}%`,height:'100%',background:color,boxShadow:`0 0 6px ${color}`}}/>
    </div>}
  </div>;
}

function ModelsHealthPanel() {
  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)', borderRadius:6,
    padding:'12px', display:'flex', flexDirection:'column', gap:8,
  }}>
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
      <span style={{fontSize:10,fontWeight:700,letterSpacing:'0.18em',textTransform:'uppercase',color:'rgba(57,255,20,0.7)',fontFamily:'var(--mantis-font-mono)'}}>ML MODELS</span>
      <span style={{fontSize:9,color:'#39FF14',fontWeight:700,fontFamily:'var(--mantis-font-mono)'}}>{PAPER_STATE.modelsLoaded}/{PAPER_STATE.modelsTotal} ✓</span>
    </div>
    {/* 21 cells grid 7×3 */}
    <div style={{display:'grid',gridTemplateColumns:'repeat(7,1fr)',gap:3}}>
      {ASSET_UNIVERSE.map((a,i) => <div key={a.epic} title={a.epic} style={{
        aspectRatio:'1',
        background:`linear-gradient(135deg, ${a.color}33, ${a.color}11)`,
        border:`1px solid ${a.color}55`,
        borderRadius:2, display:'flex',alignItems:'center',justifyContent:'center',
        fontSize:7,fontWeight:700,fontFamily:'var(--mantis-font-mono)',color:a.color,
        position:'relative',
      }}>
        {a.epic.slice(0,3)}
        <span style={{position:'absolute',top:1,right:1,width:3,height:3,borderRadius:'50%',background:'#39FF14',boxShadow:'0 0 3px #39FF14'}}/>
      </div>)}
    </div>
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',fontFamily:'var(--mantis-font-mono)',fontSize:9,color:'rgba(255,255,255,0.5)',paddingTop:4,borderTop:'1px solid rgba(255,255,255,0.04)'}}>
      <span>199 features</span>
      <span>v1</span>
      <span>26/04/26</span>
    </div>
  </div>;
}

// ─────────────────────────────────────────────────────────────
// CENTER — KPI compact strip
// ─────────────────────────────────────────────────────────────

function KpiStripCompact() {
  return <KpiStrip/>;
}

// ─────────────────────────────────────────────────────────────
// CENTER — Active positions cockpit (hero treatment)
// ─────────────────────────────────────────────────────────────

function ActivePositionsCockpit() {
  const total = OPEN_POSITIONS.reduce((s,p)=>s+p.cur_eur,0);
  return <div style={{
    background:'#161b22',
    border:'1px solid rgba(0,217,126,0.15)',
    borderRadius:6, padding:'14px', display:'flex', flexDirection:'column', gap:10,
    position:'relative', overflow:'hidden',
  }}>
    {/* Subtle scan line */}
    <div style={{position:'absolute',inset:0,background:'linear-gradient(180deg, rgba(57,255,20,0.02) 0%, transparent 30%)',pointerEvents:'none'}}/>
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',position:'relative'}}>
      <div style={{display:'flex',alignItems:'center',gap:8}}>
        <PulseDot color="#39FF14" size={7}/>
        <span style={{fontSize:11,fontWeight:700,letterSpacing:'0.2em',textTransform:'uppercase',color:'#fff',fontFamily:'var(--mantis-font-mono)'}}>POSIZIONI APERTE</span>
        <span style={{padding:'2px 7px',background:'rgba(0,229,255,0.1)',color:'#00E5FF',border:'1px solid rgba(0,229,255,0.3)',borderRadius:2,fontSize:10,fontWeight:700,fontFamily:'var(--mantis-font-mono)'}}>{OPEN_POSITIONS.length}</span>
      </div>
      <div style={{display:'flex',alignItems:'baseline',gap:6,fontFamily:'var(--mantis-font-mono)'}}>
        <span style={{fontSize:9,letterSpacing:'0.14em',textTransform:'uppercase',color:'rgba(255,255,255,0.5)',fontWeight:700}}>P&L Totale</span>
        <span style={{fontSize:18,fontWeight:700,color:total>=0?'#39FF14':'#FF3D57',fontFeatureSettings:'"tnum" 1'}}>{fmtEur(total)}</span>
      </div>
    </div>
    <div style={{display:'flex',flexDirection:'column',gap:8}}>
      {OPEN_POSITIONS.map((p,i) => <PositionCardHero key={i} p={p}/>)}
    </div>
  </div>;
}

// Hero version of position card — fills more width, bigger trend chart
function PositionCardHero({ p }) {
  const inProfit = p.cur_eur >= 0;
  const profitColor = inProfit ? '#39FF14' : '#FF3D57';
  const dirColor_ = dirColor(p.dir);
  const risk = Math.abs(p.sl_eur), reward = Math.abs(p.tp_eur);
  const rr = (reward/risk).toFixed(2);
  const distToSL = Math.abs((p.sl - p.current) / p.current * 100);
  const distToTP = Math.abs((p.tp - p.current) / p.current * 100);

  return <div style={{
    background:`linear-gradient(135deg, ${profitColor}08 0%, transparent 60%)`,
    border:`1px solid ${profitColor}26`,
    borderLeft:`3px solid ${profitColor}`,
    borderRadius:5, padding:'14px',
    display:'grid', gridTemplateColumns:'200px 1fr 220px', gap:18,
    position:'relative',
  }}>
    {/* Col 1 — identity + age + trailing */}
    <div style={{display:'flex',flexDirection:'column',gap:8}}>
      <div style={{display:'flex',alignItems:'center',gap:10}}>
        <AssetGlyph epic={p.epic} size={36}/>
        <div style={{display:'flex',flexDirection:'column',lineHeight:1}}>
          <span style={{fontSize:18,fontWeight:700,color:'#fff',fontFamily:'var(--mantis-font-mono)',letterSpacing:'0.02em'}}>{p.epic}</span>
          <span style={{fontSize:9,color:'rgba(255,255,255,0.4)',marginTop:4,fontFamily:'var(--mantis-font-mono)',letterSpacing:'0.1em'}}>conf {p.confidence}%</span>
        </div>
      </div>
      <div style={{display:'flex',alignItems:'center',gap:5}}>
        <span style={{padding:'3px 8px',borderRadius:3,fontSize:10,fontWeight:700,letterSpacing:'0.14em',background:`${dirColor_}1a`,color:dirColor_,border:`1px solid ${dirColor_}33`,fontFamily:'var(--mantis-font-mono)'}}>{p.dir}</span>
        <span style={{fontSize:11,color:'rgba(255,255,255,0.6)',fontFamily:'var(--mantis-font-mono)',fontFeatureSettings:'"tnum" 1'}}>{typeof p.size==='number' && p.size>=100 ? p.size.toLocaleString('it-IT') : p.size}</span>
      </div>
      <div style={{display:'flex',gap:6,fontFamily:'var(--mantis-font-mono)'}}>
        <Chip label="AGE" value={fmtAge(p.age_min)}/>
        {p.trailing
          ? <Chip label="TRAIL" value="ON" color="#00E5FF" bg="rgba(0,229,255,0.08)" border="rgba(0,229,255,0.3)"/>
          : <Chip label="TRAIL" value="OFF"/>
        }
      </div>
      <div style={{display:'flex',gap:6,fontFamily:'var(--mantis-font-mono)'}}>
        <Chip label="R:R" value={`1:${rr}`} color="#fff"/>
      </div>
    </div>

    {/* Col 2 — SL/Entry/TP visualization + distances */}
    <div style={{display:'flex',flexDirection:'column',gap:8}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
        <span style={{fontSize:9,fontWeight:700,letterSpacing:'0.18em',textTransform:'uppercase',color:'rgba(255,255,255,0.55)',fontFamily:'var(--mantis-font-mono)'}}>STOP LOSS · ENTRY · TAKE PROFIT</span>
        <span style={{fontSize:9,color:'rgba(255,255,255,0.4)',fontFamily:'var(--mantis-font-mono)'}}>quote {p.current}</span>
      </div>
      <PositionRange entry={p.entry} current={p.current} sl={p.sl} tp={p.tp} dir={p.dir} w={400}/>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:8,fontFamily:'var(--mantis-font-mono)'}}>
        <PriceTile label="SL" price={p.sl} delta_eur={p.sl_eur} delta_pct={p.sl_pct} color="#FF3D57"/>
        <PriceTile label="ENTRY" price={p.entry} delta_eur={null} delta_pct={null} color="#fff"/>
        <PriceTile label="TP" price={p.tp} delta_eur={p.tp_eur} delta_pct={p.tp_pct} color="#39FF14"/>
      </div>
      <div style={{display:'flex',gap:14,fontSize:9,color:'rgba(255,255,255,0.5)',fontFamily:'var(--mantis-font-mono)',paddingTop:4,borderTop:'1px solid rgba(255,255,255,0.05)'}}>
        <span>distanza → SL <span style={{color:'#FF3D57',fontWeight:700,marginLeft:4}}>{distToSL.toFixed(2)}%</span></span>
        <span>distanza → TP <span style={{color:'#39FF14',fontWeight:700,marginLeft:4}}>{distToTP.toFixed(2)}%</span></span>
        <div style={{flex:1}}/>
        <span>trend 1H <span style={{color: (p.trendDir==='down'&&p.dir==='SELL')||(p.trendDir==='up'&&p.dir==='BUY') ? '#39FF14' : '#FF3D57',fontWeight:700,marginLeft:4}}>{p.trendDir==='up'?'↗':p.trendDir==='down'?'↘':'→'} vs {p.dir}</span></span>
      </div>
    </div>

    {/* Col 3 — P&L corrente hero + trend mini */}
    <div style={{display:'flex',flexDirection:'column',gap:8,padding:'10px 14px',background:`${profitColor}0d`,border:`1px solid ${profitColor}26`,borderRadius:4}}>
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
        <span style={{fontSize:9,fontWeight:700,letterSpacing:'0.18em',textTransform:'uppercase',color:profitColor,fontFamily:'var(--mantis-font-mono)'}}>P&L CORRENTE</span>
        <PulseDot color={profitColor} size={6}/>
      </div>
      <div style={{display:'flex',alignItems:'baseline',gap:8,fontFamily:'var(--mantis-font-mono)'}}>
        <span style={{fontSize:30,fontWeight:700,color:profitColor,fontFeatureSettings:'"tnum" 1',lineHeight:1}}>{fmtEur(p.cur_eur)}</span>
      </div>
      <div style={{fontSize:13,color:profitColor,fontWeight:700,fontFamily:'var(--mantis-font-mono)',fontFeatureSettings:'"tnum" 1'}}>{fmtPct(p.cur_pct,3)}</div>
      <div style={{borderTop:`1px solid ${profitColor}1f`,paddingTop:6,marginTop:2}}>
        <Sparkline data={p.trend} w={180} h={32} color={profitColor}/>
      </div>
      <button style={{
        padding:'6px 8px',borderRadius:3,fontSize:10,fontWeight:700,letterSpacing:'0.12em',
        background:'rgba(255,61,87,0.1)',color:'#FF3D57',border:'1px solid rgba(255,61,87,0.3)',
        fontFamily:'var(--mantis-font-mono)',cursor:'pointer',marginTop:2,
      }}>CLOSE NOW</button>
    </div>
  </div>;
}

function PriceTile({ label, price, delta_eur, delta_pct, color }) {
  return <div style={{
    background:'rgba(255,255,255,0.02)',border:'1px solid rgba(255,255,255,0.05)',
    borderRadius:3,padding:'5px 8px',display:'flex',flexDirection:'column',gap:2,
  }}>
    <span style={{fontSize:8,letterSpacing:'0.14em',textTransform:'uppercase',fontWeight:700,color}}>{label}</span>
    <span style={{fontSize:12,fontWeight:700,color:'#fff',fontFeatureSettings:'"tnum" 1',lineHeight:1}}>{price}</span>
    {delta_eur !== null && <span style={{fontSize:9,color,fontFeatureSettings:'"tnum" 1'}}>{fmtEur(delta_eur)} · {fmtPct(delta_pct)}</span>}
  </div>;
}

// ─────────────────────────────────────────────────────────────
// CENTER — Signals heatmap (21 cells)
// ─────────────────────────────────────────────────────────────

function SignalsHeatmap() {
  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)', borderRadius:6,
    padding:'12px', display:'flex', flexDirection:'column', gap:10,
  }}>
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
      <div style={{display:'flex',alignItems:'center',gap:8}}>
        <span style={{fontSize:11,fontWeight:700,letterSpacing:'0.2em',textTransform:'uppercase',color:'#fff',fontFamily:'var(--mantis-font-mono)'}}>SEGNALI PER ASSET</span>
        <span style={{padding:'2px 6px',background:'rgba(57,255,20,0.08)',color:'#39FF14',border:'1px solid rgba(57,255,20,0.25)',borderRadius:2,fontSize:9,fontWeight:700,fontFamily:'var(--mantis-font-mono)'}}>{ASSET_UNIVERSE.length} ATTIVI</span>
      </div>
      <Legend/>
    </div>
    <div style={{display:'grid',gridTemplateColumns:'repeat(7,1fr)',gap:6}}>
      {ASSET_UNIVERSE.map(a => {
        const last = LAST_SIGNALS[a.epic] || {dir:'HOLD',conf:0,state:'hold',time:'—'};
        return <HeatmapCell key={a.epic} a={a} last={last}/>;
      })}
    </div>
  </div>;
}

function HeatmapCell({ a, last }) {
  const sc = stateColor(last.state);
  const isActive = ['executed','rejected','closed'].includes(last.state);
  const dc = dirColor(last.dir);
  return <div style={{
    background: isActive ? `${sc}10` : 'rgba(255,255,255,0.02)',
    border: `1px solid ${isActive?`${sc}40`:'rgba(255,255,255,0.06)'}`,
    borderRadius:3,padding:'7px 8px',display:'flex',flexDirection:'column',gap:4,
    fontFamily:'var(--mantis-font-mono)',position:'relative',minHeight:62,
    boxShadow: isActive ? `0 0 8px ${sc}26` : 'none',
  }}>
    {isActive && <PulseDot color={sc} size={5}/>}
    <div style={{display:'flex',alignItems:'center',gap:5,marginTop:isActive?-12:0,marginLeft:isActive?12:0}}>
      <span style={{display:'inline-block',width:6,height:6,borderRadius:'50%',background:a.color}}/>
      <span style={{fontSize:10,fontWeight:700,color:'#fff'}}>{a.epic}</span>
    </div>
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginTop:1}}>
      <span style={{padding:'1px 4px',borderRadius:2,fontSize:8,fontWeight:700,letterSpacing:'0.08em',background:`${dc}1a`,color:dc,border:`1px solid ${dc}33`}}>{last.dir}</span>
      <span style={{fontSize:9,color: last.conf>=50?'#39FF14':last.conf>=30?'#FFB020':'rgba(255,255,255,0.4)',fontWeight:700,fontFeatureSettings:'"tnum" 1'}}>{last.conf}%</span>
    </div>
    <div style={{height:2,background:'rgba(255,255,255,0.06)',borderRadius:1,overflow:'hidden',marginTop:2}}>
      <div style={{width:`${last.conf}%`,height:'100%',background:last.conf>=50?'#39FF14':last.conf>=30?'#FFB020':'#8B949E'}}/>
    </div>
  </div>;
}

function Legend() {
  return <div style={{display:'flex',gap:8,fontFamily:'var(--mantis-font-mono)'}}>
    {[
      {c:'#39FF14',l:'EXEC'},
      {c:'#FF3D57',l:'REJ'},
      {c:'#00E5FF',l:'CLOSED'},
      {c:'#8B949E',l:'HOLD'},
    ].map(x => <span key={x.l} style={{display:'inline-flex',alignItems:'center',gap:4,fontSize:8,color:'rgba(255,255,255,0.5)'}}>
      <span style={{width:5,height:5,borderRadius:'50%',background:x.c}}/>{x.l}
    </span>)}
  </div>;
}

// ─────────────────────────────────────────────────────────────
// RIGHT — Live feed timeline
// ─────────────────────────────────────────────────────────────

function LiveFeedTimeline() {
  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)', borderRadius:6,
    padding:'12px', display:'flex', flexDirection:'column', gap:10, height:'fit-content',
    position:'sticky', top:14,
  }}>
    <div style={{display:'flex',alignItems:'center',gap:8}}>
      <PulseDot color="#39FF14" size={6}/>
      <span style={{fontSize:10,fontWeight:700,letterSpacing:'0.18em',textTransform:'uppercase',color:'#39FF14',fontFamily:'var(--mantis-font-mono)'}}>LIVE FEED</span>
      <div style={{flex:1}}/>
      <span style={{fontSize:9,color:'rgba(255,255,255,0.4)',fontFamily:'var(--mantis-font-mono)'}}>{FEED.length} eventi · 24h</span>
    </div>

    {/* Counts strip */}
    <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:5,fontFamily:'var(--mantis-font-mono)'}}>
      <CountTile label="EXEC" value={2} color="#39FF14"/>
      <CountTile label="REJ" value={5} color="#FF3D57"/>
      <CountTile label="HOLD" value={57} color="#8B949E"/>
    </div>

    {/* Timeline */}
    <div style={{display:'flex',flexDirection:'column',gap:0,position:'relative'}}>
      <div style={{position:'absolute',left:9,top:6,bottom:6,width:1,background:'linear-gradient(180deg, transparent, rgba(57,255,20,0.2), transparent)'}}/>
      {FEED.slice(0,11).map((s,i) => <TimelineEvent key={i} s={s}/>)}
    </div>
  </div>;
}

function CountTile({ label, value, color }) {
  return <div style={{
    background:`${color}0d`,border:`1px solid ${color}26`,borderRadius:3,
    padding:'5px 8px',display:'flex',flexDirection:'column',gap:1,
  }}>
    <span style={{fontSize:8,letterSpacing:'0.14em',color:color,fontWeight:700}}>{label}</span>
    <span style={{fontSize:14,fontWeight:700,color:'#fff',fontFeatureSettings:'"tnum" 1',lineHeight:1}}>{value}</span>
  </div>;
}

function TimelineEvent({ s }) {
  const sc = stateColor(s.state);
  const dc = dirColor(s.dir);
  const isImportant = s.state==='executed' || s.state==='rejected';
  return <div style={{
    display:'grid',gridTemplateColumns:'20px 1fr',gap:8,padding:'7px 0',
    fontFamily:'var(--mantis-font-mono)',
    borderBottom:'1px solid rgba(255,255,255,0.04)',
  }}>
    <div style={{display:'flex',justifyContent:'center',position:'relative',zIndex:1,paddingTop:4}}>
      <div style={{
        width:9,height:9,borderRadius:'50%',background:'#0d1117',
        border:`2px solid ${sc}`,boxShadow:isImportant?`0 0 8px ${sc}99`:'none',
      }}/>
    </div>
    <div style={{display:'flex',flexDirection:'column',gap:3}}>
      <div style={{display:'flex',alignItems:'center',gap:6,justifyContent:'space-between'}}>
        <div style={{display:'flex',alignItems:'center',gap:5}}>
          <AssetGlyph epic={s.epic} size={14}/>
          <span style={{fontSize:10,fontWeight:700,color:'#fff'}}>{s.epic}</span>
          <span style={{padding:'1px 4px',borderRadius:2,fontSize:8,fontWeight:700,letterSpacing:'0.08em',background:`${dc}1a`,color:dc,border:`1px solid ${dc}33`}}>{s.dir}</span>
        </div>
        <span style={{fontSize:9,color:'rgba(255,255,255,0.4)',fontFeatureSettings:'"tnum" 1'}}>{s.time}</span>
      </div>
      <div style={{display:'flex',alignItems:'center',gap:6}}>
        <span style={{fontSize:9,color:s.conf>=50?'#39FF14':'rgba(255,255,255,0.4)',fontWeight:700}}>{s.conf}%</span>
        <span style={{fontSize:9,color:'rgba(255,255,255,0.5)',fontFeatureSettings:'"tnum" 1'}}>{typeof s.price === 'number' ? s.price : '—'}</span>
        <span style={{fontSize:9,color:'rgba(255,255,255,0.35)',padding:'0 4px',background:'rgba(255,255,255,0.025)',border:'1px solid rgba(255,255,255,0.04)',borderRadius:2}}>{s.strategy}</span>
      </div>
      {isImportant && <div style={{fontSize:9,color:sc,padding:'3px 6px',background:`${sc}0d`,border:`1px solid ${sc}26`,borderRadius:2,marginTop:2}}>
        {s.detail}
      </div>}
    </div>
  </div>;
}

// ─────────────────────────────────────────────────────────────

function Footer() {
  return <div style={{
    display:'flex',alignItems:'center',gap:14,padding:'10px 16px',
    borderTop:'1px solid rgba(255,255,255,0.06)',
    fontFamily:'var(--mantis-font-mono)',fontSize:9,color:'rgba(255,255,255,0.4)',
  }}>
    <span style={{color:'#39FF14',fontWeight:700,letterSpacing:'0.12em'}}>MANTIS AI</span>
    <span>v1.0</span>
    <div style={{flex:1}}/>
    <span style={{color:'#FFB020'}}>Demo Mode</span>
  </div>;
}

window.PaperVariantB = PaperVariantB;
