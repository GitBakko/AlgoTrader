// OperationalStrip.jsx — compact "what's happening right now" bar shared by both variants
function OperationalStrip({ variant='a' }) {
  const positions = [
    { sym:'BTCUSD',   dir:'BUY',  pnl:+1270.00, pct:+2.12, entry:'64,210', mark:'65,480' },
    { sym:'EURUSD',   dir:'BUY',  pnl:+290.00,  pct:+0.27, entry:'1.08420', mark:'1.08710' },
    { sym:'XAUUSD',   dir:'SELL', pnl:-57.00,   pct:-0.23, entry:'2,418.40', mark:'2,424.10' },
    { sym:'NAS100',   dir:'BUY',  pnl:+3.00,    pct:+0.02, entry:'18,124', mark:'18,127' },
  ];
  const totalPnl = positions.reduce((s,p)=>s+p.pnl, 0);
  const equity = 54812.09;

  return <div style={{
    display:'grid',
    gridTemplateColumns: 'minmax(260px, 320px) minmax(0,1fr) auto',
    gap:12, alignItems:'stretch',
    background:'linear-gradient(180deg, rgba(22,27,34,0.9) 0%, rgba(13,17,23,0.6) 100%)',
    border:'1px solid rgba(0,217,126,0.18)', borderRadius:8, padding:'10px 14px',
  }}>
    {/* LIVE P&L + session */}
    <div style={{display:'flex',flexDirection:'column',gap:4,borderRight:'1px solid rgba(255,255,255,0.06)',paddingRight:14}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
        <span style={{fontSize:9,letterSpacing:'.22em',textTransform:'uppercase',color:'rgba(57,255,20,0.6)',fontWeight:700}}>SESSION · Live P&L</span>
        <span style={{display:'inline-flex',alignItems:'center',gap:5,fontSize:10,color:'#39FF14',fontFamily:'var(--mantis-font-mono)'}}>
          <span style={{width:7,height:7,borderRadius:'50%',background:'#39FF14',boxShadow:'0 0 8px rgba(57,255,20,0.8)',animation:'pulseGlow 2s infinite'}}/>LIVE · US OPEN
        </span>
      </div>
      <div style={{display:'flex',alignItems:'baseline',gap:10}}>
        <span style={{fontFamily:'var(--mantis-font-mono)',fontWeight:700,fontSize:28,letterSpacing:'.02em',color: totalPnl>=0 ? '#39FF14' : '#FF3D57', textShadow: totalPnl>=0?'0 0 16px rgba(57,255,20,0.35)':'0 0 16px rgba(255,61,87,0.35)', fontFeatureSettings:'"tnum" 1'}}>
          {totalPnl>=0?'+':''}€{Math.abs(totalPnl).toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2})}
        </span>
        <span style={{fontFamily:'var(--mantis-font-mono)',fontSize:12,color: totalPnl>=0?'#39FF14':'#FF3D57',opacity:0.8}}>
          {totalPnl>=0?'▲':'▼'} {fmtPct(totalPnl/equity*100)}
        </span>
      </div>
      <div style={{display:'flex',gap:14,fontSize:10,color:'rgba(255,255,255,0.55)',fontFamily:'var(--mantis-font-mono)'}}>
        <span>Equity <span style={{color:'rgba(255,255,255,0.85)'}}>€{equity.toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2})}</span></span>
        <span>Trades <span style={{color:'rgba(255,255,255,0.85)'}}>14</span></span>
        <span>Peak <span style={{color:'#39FF14'}}>+€1,402.10</span></span>
      </div>
    </div>

    {/* Open positions inline */}
    <div style={{display:'flex',flexDirection:'column',gap:4,minWidth:0}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
        <span style={{fontSize:9,letterSpacing:'.22em',textTransform:'uppercase',color:'rgba(255,255,255,0.45)',fontWeight:700}}>Open Positions · {positions.length}/8</span>
        <span style={{fontSize:10,color:'rgba(255,255,255,0.4)',fontFamily:'var(--mantis-font-mono)'}}>Kelly ½ · 3 slots free</span>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:6}}>
        {positions.map(p => {
          const win = p.pnl >= 0;
          return <div key={p.sym} style={{
            background: win ? 'rgba(57,255,20,0.06)' : 'rgba(255,61,87,0.06)',
            border: `1px solid ${win?'rgba(57,255,20,0.2)':'rgba(255,61,87,0.2)'}`,
            borderLeft: `3px solid ${win?'#39FF14':'#FF3D57'}`,
            borderRadius:4, padding:'6px 8px', display:'flex',flexDirection:'column',gap:2,
            fontFamily:'var(--mantis-font-mono)',
          }}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
              <span style={{fontSize:11,fontWeight:700,color:'rgba(255,255,255,0.9)',letterSpacing:'0.02em'}}>{p.sym}</span>
              <span style={{fontSize:9,fontWeight:700,letterSpacing:'0.08em',color: p.dir==='BUY'?'#39FF14':'#FF3D57'}}>{p.dir==='BUY'?'▲':'▼'}{p.dir}</span>
            </div>
            <div style={{display:'flex',justifyContent:'space-between',fontSize:12,fontWeight:700}}>
              <span style={{color: win ? '#39FF14':'#FF3D57', textShadow: win ? '0 0 8px rgba(57,255,20,0.3)':'none'}}>
                {win?'+':'−'}€{Math.abs(p.pnl).toFixed(0)}
              </span>
              <span style={{color:'rgba(255,255,255,0.5)',fontSize:10}}>{fmtPct(p.pct)}</span>
            </div>
          </div>;
        })}
      </div>
    </div>

    {/* Circuit breakers / system state */}
    <div style={{display:'flex',flexDirection:'column',gap:4,borderLeft:'1px solid rgba(255,255,255,0.06)',paddingLeft:14,minWidth:200}}>
      <span style={{fontSize:9,letterSpacing:'.22em',textTransform:'uppercase',color:'rgba(255,255,255,0.45)',fontWeight:700}}>System</span>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'2px 10px',fontSize:10,fontFamily:'var(--mantis-font-mono)'}}>
        {[
          ['Breakers','6/6 OK','#39FF14'],
          ['WS','Live','#39FF14'],
          ['Broker','Capital', 'rgba(255,255,255,0.7)'],
          ['Mode','DEMO','#FFB020'],
          ['Funding','-0.04%/8h','#FFB020'],
          ['Regime','Trend↑','#39FF14'],
        ].map(([k,v,c])=> (
          <div key={k} style={{display:'flex',justifyContent:'space-between'}}>
            <span style={{color:'rgba(255,255,255,0.45)'}}>{k}</span>
            <span style={{color:c,fontWeight:600}}>{v}</span>
          </div>
        ))}
      </div>
    </div>
  </div>;
}

Object.assign(window, { OperationalStrip });
