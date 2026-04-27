// CockpitHeader.jsx — header allineato con OperationalStrip della Dashboard

function CockpitHeader({ tweaks={} }) {
  const status = tweaks.botStatus || PAPER_STATE.status;
  const market = tweaks.market || PAPER_STATE.market;
  const openCount = tweaks.openCount ?? PAPER_STATE.openCount;
  return <div style={{
    display:'flex', alignItems:'center', gap:14, padding:'12px 16px',
    background: `linear-gradient(180deg, rgba(57,255,20,0.04) 0%, transparent 100%)`,
    borderBottom: '1px solid rgba(57,255,20,0.18)',
    fontFamily:'var(--mantis-font-mono)',
  }}>
    {/* Brand + page title */}
    <div style={{display:'flex',alignItems:'center',gap:10}}>
      <svg width="22" height="22" viewBox="0 0 64 64">
        <polygon points="32,6 52,26 46,58 18,58 12,26" fill="none" stroke="#39FF14" strokeWidth="2.5" style={{filter:'drop-shadow(0 0 4px rgba(57,255,20,0.6))'}}/>
        <ellipse cx="24" cy="32" rx="3.5" ry="5" fill="#39FF14"/>
        <ellipse cx="40" cy="32" rx="3.5" ry="5" fill="#39FF14"/>
      </svg>
      <div style={{display:'flex',flexDirection:'column',lineHeight:1}}>
        <span style={{fontSize:9,color:'rgba(255,255,255,0.4)',letterSpacing:'0.18em',fontWeight:700,textTransform:'uppercase'}}>MANTIS AI ·</span>
        <span style={{fontSize:14,fontWeight:700,color:'#fff',letterSpacing:'0.04em',marginTop:2}}>Paper Trading</span>
      </div>
    </div>

    {/* Status pills cluster */}
    <div style={{display:'flex',alignItems:'center',gap:6,marginLeft:8}}>
      <StatusPill status={status}/>
      <Chip label="MODE" value={PAPER_STATE.mode}
        color={PAPER_STATE.mode==='LIVE' ? '#FF3D57' : '#FFB020'}
        bg={PAPER_STATE.mode==='LIVE' ? 'rgba(255,61,87,0.1)' : 'rgba(255,176,32,0.08)'}
        border={PAPER_STATE.mode==='LIVE' ? 'rgba(255,61,87,0.3)' : 'rgba(255,176,32,0.25)'}/>
      <Chip label="MKT" value={market}
        color={market==='OPEN' ? '#39FF14' : '#8B949E'}
        bg={market==='OPEN' ? 'rgba(57,255,20,0.08)' : 'rgba(139,148,158,0.08)'}
        border={market==='OPEN' ? 'rgba(57,255,20,0.25)' : 'rgba(139,148,158,0.2)'}/>
    </div>

    {/* Heartbeat — compact */}
    <div style={{display:'flex',alignItems:'center',gap:8,padding:'4px 10px',background:'rgba(255,255,255,0.025)',border:'1px solid rgba(255,255,255,0.06)',borderRadius:4}}>
      <PulseDot color={status==='ERROR'?'#FF3D57':'#39FF14'} size={6}/>
      <span style={{fontSize:10,color:'rgba(255,255,255,0.6)'}}>last tick</span>
      <span style={{fontSize:10,color:'#fff',fontWeight:700}}>{PAPER_STATE.lastTickAgo.toFixed(1)}s</span>
      <span style={{width:1,height:10,background:'rgba(255,255,255,0.1)'}}/>
      <span style={{fontSize:10,color:'rgba(255,255,255,0.6)'}}>uptime</span>
      <span style={{fontSize:10,color:'#fff',fontWeight:700}}>{PAPER_STATE.uptime}</span>
      <span style={{width:1,height:10,background:'rgba(255,255,255,0.1)'}}/>
      <span style={{fontSize:10,color:'rgba(255,255,255,0.6)'}}>iter</span>
      <span style={{fontSize:10,color:'#fff',fontWeight:700}}>{PAPER_STATE.iterations}</span>
    </div>

    <div style={{flex:1}}/>

    {/* Open positions live counter */}
    <div style={{display:'flex',alignItems:'center',gap:8,padding:'4px 10px',background:'rgba(0,217,126,0.06)',border:'1px solid rgba(0,217,126,0.2)',borderRadius:4}}>
      <span style={{fontSize:9,color:'rgba(255,255,255,0.5)',letterSpacing:'0.12em',textTransform:'uppercase',fontWeight:700}}>POS</span>
      <span style={{fontSize:13,fontWeight:700,color:'#fff'}}>{openCount}</span>
      <span style={{fontSize:9,color:'rgba(255,255,255,0.4)'}}>aperte</span>
    </div>

    {/* Live unrealized P&L */}
    <div style={{display:'flex',alignItems:'baseline',gap:6,padding:'4px 12px',
      background: PAPER_STATE.pnlOpen>=0 ? 'rgba(57,255,20,0.06)' : 'rgba(255,61,87,0.06)',
      border: `1px solid ${PAPER_STATE.pnlOpen>=0?'rgba(57,255,20,0.25)':'rgba(255,61,87,0.25)'}`,
      borderRadius:4,
    }}>
      <span style={{fontSize:9,color:'rgba(255,255,255,0.5)',letterSpacing:'0.12em',textTransform:'uppercase',fontWeight:700}}>uPnL</span>
      <span style={{fontSize:14,fontWeight:700,color:PAPER_STATE.pnlOpen>=0?'#39FF14':'#FF3D57',fontFeatureSettings:'"tnum" 1'}}>{fmtEur(PAPER_STATE.pnlOpen)}</span>
    </div>

    {/* Action buttons */}
    <button style={{
      padding:'6px 14px', borderRadius:4, fontWeight:700, fontSize:11, fontFamily:'var(--mantis-font-mono)',
      letterSpacing:'0.08em', cursor:'pointer',
      background:'rgba(255,176,32,0.1)', color:'#FFB020', border:'1px solid rgba(255,176,32,0.4)',
    }}>STOP</button>
    <button style={{
      padding:'6px 14px', borderRadius:4, fontWeight:700, fontSize:11, fontFamily:'var(--mantis-font-mono)',
      letterSpacing:'0.08em', cursor:'pointer',
      background:'#FF3D57', color:'#fff', border:'1px solid #FF3D57',
      boxShadow:'0 0 12px rgba(255,61,87,0.5)',
      animation: status==='RUNNING'?'pulseEmerg 2s ease-in-out infinite':'none',
    }}>EMERGENCY STOP</button>
  </div>;
}

// ─────────────────────────────────────────────────────────────
// KPI Strip — Stato + KPI (priority #1 per l'utente)
// ─────────────────────────────────────────────────────────────

function KpiStrip({ variant='A' }) {
  const cards = [
    {
      title:'ITERAZIONI',
      value: PAPER_STATE.iterations,
      sub: `Check Pl · interv. ${PAPER_STATE.intervalSec}s`,
      accent:'#00d97e',
      detail: <Sparkline data={[5,6,6,7,7,8,8,9,9,9,9,9]} color="#00d97e" w={60} h={18}/>,
    },
    {
      title:'SEGNALI / TRADE',
      value: <span><span style={{color:'#fff'}}>{PAPER_STATE.signals.total}</span><span style={{color:'rgba(255,255,255,0.4)',fontSize:14}}> / </span><span style={{color:'#39FF14'}}>{PAPER_STATE.signals.executed}</span></span>,
      sub: `Conversione ${PAPER_STATE.signals.conversion.toFixed(1)}%`,
      accent:'#00E5FF',
      detail: <div style={{display:'flex',gap:3,alignItems:'flex-end',height:18}}>
        {[6,8,4,9,7,11,8,13,10,12,14,11].map((h,i)=><div key={i} style={{width:3,height:h,background:'#00E5FF',opacity:0.6+i*0.03,borderRadius:1}}/>)}
      </div>,
    },
    {
      title:'P&L (USD)',
      value: <span style={{color: PAPER_STATE.pnlOpen>=0?'#39FF14':'#FF3D57'}}>${PAPER_STATE.pnlOpen.toFixed(2)}</span>,
      sub: `Posizioni aperte: ${PAPER_STATE.openCount}`,
      accent: PAPER_STATE.pnlOpen>=0 ? '#39FF14' : '#FF3D57',
      detail: <Sparkline data={[2,1,3,-1,0,-2,-3,-4,-5,-7,-6,-6]} color={PAPER_STATE.pnlOpen>=0?'#39FF14':'#FF3D57'} w={60} h={18}/>,
    },
    {
      title:'ERRORI',
      value: <span style={{color: PAPER_STATE.errors>0?'#FF3D57':'#39FF14'}}>{PAPER_STATE.errors}</span>,
      sub: `${PAPER_STATE.signals.rejected} segnali rifiutati`,
      accent: PAPER_STATE.errors>0 ? '#FF3D57' : '#39FF14',
      detail: <div style={{display:'flex',alignItems:'center',gap:4,fontSize:9,color:'#39FF14',fontFamily:'var(--mantis-font-mono)'}}>
        <span style={{display:'inline-block',width:6,height:6,borderRadius:'50%',background:'#39FF14',boxShadow:'0 0 6px #39FF14'}}/>
        <span style={{fontWeight:700}}>HEALTHY</span>
      </div>,
    },
  ];
  return <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
    {cards.map((c,i) => <div key={i} style={{
      background:'#161b22', border:'1px solid rgba(0,217,126,0.15)',
      borderTop: `2px solid ${c.accent}`, borderRadius:6,
      padding:'10px 12px', display:'flex', flexDirection:'column', gap:4, position:'relative', overflow:'hidden', minHeight:88,
    }}>
      <div style={{position:'absolute',right:10,bottom:8,opacity:0.85,pointerEvents:'none'}}>{c.detail}</div>
      <Label>{c.title}</Label>
      <div style={{fontFamily:'var(--mantis-font-mono)',fontWeight:700,fontSize:24,letterSpacing:'.02em',color:'#fff',fontFeatureSettings:'"tnum" 1',lineHeight:1.05,position:'relative',zIndex:1}}>{c.value}</div>
      <div style={{fontSize:10,color:'rgba(255,255,255,0.5)',fontFamily:'var(--mantis-font-mono)',position:'relative',zIndex:1}}>{c.sub}</div>
    </div>)}
  </div>;
}

// ─────────────────────────────────────────────────────────────
// Risk Cockpit — 4 indicators in cockpit-style row
// ─────────────────────────────────────────────────────────────

function RiskCockpit() {
  const r = RISK_STATE;
  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)', borderRadius:6,
    padding:'10px 12px', display:'flex', flexDirection:'column', gap:8,
  }}>
    <Label right={<span style={{fontSize:9,fontFamily:'var(--mantis-font-mono)',color:'rgba(255,255,255,0.5)'}}>4 indicatori · refresh 10s</span>}>Risk Management</Label>
    <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
      {/* Circuit Breakers */}
      <RiskCard
        label="Circuit Breakers"
        status={r.circuitBreakers.status}
        primary={`${r.circuitBreakers.tripped}/${r.circuitBreakers.total}`}
        primarySub="tripped"
        bar={null}
        note={r.circuitBreakers.tripped===0 ? 'tutti i breaker armati' : 'attenzione'}
      />
      {/* Equity Filter */}
      <RiskCard
        label="Equity Filter"
        status={r.equityFilter.status}
        primary={`${r.equityFilter.dd.toFixed(1)}%`}
        primarySub={`DD soglia ${r.equityFilter.threshold}%`}
        bar={{ pct: (r.equityFilter.dd/r.equityFilter.threshold)*100, color: r.equityFilter.status==='WARN'?'#FFB020':'#39FF14' }}
        note="vicino al limite"
      />
      {/* Kelly Sizing */}
      <RiskCard
        label="Kelly Sizing"
        status={r.kelly.status}
        primary={<span><span style={{color:'#00E5FF'}}>{r.kelly.avg}%</span><span style={{color:'rgba(255,255,255,0.3)',fontSize:14}}>avg</span></span>}
        primarySub={`win ${r.kelly.win}% · pnl ${r.kelly.pnl}€`}
        bar={null}
        note="frazionale 14% applicato"
        accent="#00E5FF"
      />
      {/* Trading Stops */}
      <RiskCard
        label="Trading Stops"
        status={r.tradingStops.status}
        primary={r.tradingStops.count}
        primarySub="stop attivi"
        bar={null}
        note="sistema attivo"
      />
    </div>
  </div>;
}

function RiskCard({ label, status, primary, primarySub, bar, note, accent }) {
  const cfg = {
    OK:     {c:'#39FF14', text:'OK',     bg:'rgba(57,255,20,0.08)',  border:'rgba(57,255,20,0.25)'},
    WARN:   {c:'#FFB020', text:'WARN',   bg:'rgba(255,176,32,0.08)', border:'rgba(255,176,32,0.3)'},
    ATTIVO: {c:'#00E5FF', text:'ATTIVO', bg:'rgba(0,229,255,0.08)',  border:'rgba(0,229,255,0.25)'},
    ERROR:  {c:'#FF3D57', text:'ERROR',  bg:'rgba(255,61,87,0.08)',  border:'rgba(255,61,87,0.3)'},
  }[status];
  const ac = accent || cfg.c;
  return <div style={{
    background:'rgba(255,255,255,0.015)', border:`1px solid ${cfg.border}`, borderLeft:`2px solid ${ac}`,
    borderRadius:4, padding:'8px 10px', display:'flex', flexDirection:'column', gap:5,
  }}>
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
      <span style={{fontSize:9,fontWeight:700,letterSpacing:'0.14em',textTransform:'uppercase',color:'rgba(255,255,255,0.6)',fontFamily:'var(--mantis-font-mono)'}}>{label}</span>
      <span style={{fontSize:8,fontWeight:700,letterSpacing:'0.1em',color:cfg.c,padding:'2px 5px',background:cfg.bg,borderRadius:2,fontFamily:'var(--mantis-font-mono)'}}>{cfg.text}</span>
    </div>
    <div style={{display:'flex',alignItems:'baseline',gap:6,fontFamily:'var(--mantis-font-mono)'}}>
      <span style={{fontSize:18,fontWeight:700,color:'#fff',fontFeatureSettings:'"tnum" 1',lineHeight:1}}>{primary}</span>
      <span style={{fontSize:9,color:'rgba(255,255,255,0.4)'}}>{primarySub}</span>
    </div>
    {bar && <div style={{height:3,background:'rgba(255,255,255,0.06)',borderRadius:2,overflow:'hidden'}}>
      <div style={{width:`${Math.min(bar.pct,100)}%`,height:'100%',background:bar.color,boxShadow:`0 0 6px ${bar.color}`}}/>
    </div>}
    {note && <div style={{fontSize:9,color:'rgba(255,255,255,0.45)',fontFamily:'var(--mantis-font-mono)'}}>{note}</div>}
  </div>;
}

Object.assign(window, { CockpitHeader, KpiStrip, RiskCockpit });
