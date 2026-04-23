// TradeBreakdown.jsx — BUY/SELL × Going/TP/SL breakdown SPLIT BY DAY

// Generate per-day breakdown for the selected timeframe
const genBreakdownDays = (days, seed=91) => {
  const r = rand(seed);
  const today = new Date('2026-04-22');
  const out = [];
  for (let i = days-1; i >= 0; i--) {
    const d = new Date(today); d.setDate(today.getDate() - i);
    const dow = d.getDay();
    const weekend = dow === 0 || dow === 6;
    if (weekend && r() > 0.25) { out.push({date:d, buy:{tp:0,sl:0,going:0,pnl:0}, sell:{tp:0,sl:0,going:0,pnl:0}, empty:true, weekend:true}); continue; }
    const isToday = i === 0;
    const total = Math.max(1, Math.floor(r()*10) + 2);
    const buyShare = 0.4 + r()*0.3;
    const buyN = Math.round(total * buyShare);
    const sellN = total - buyN;
    const mkSide = (n, winBias=0.6) => {
      const going = isToday && r() > 0.4 ? Math.min(n, Math.floor(r()*2)+1) : 0;
      const closed = n - going;
      const tp = Math.max(0, Math.min(closed, Math.round(closed * (winBias + (r()-0.5)*0.35))));
      const sl = Math.max(0, closed - tp);
      const pnl = Math.round(tp * (70 + r()*160) - sl * (55 + r()*130));
      return { tp, sl, going, pnl };
    };
    out.push({ date:d, buy: mkSide(buyN, 0.65), sell: mkSide(sellN, 0.58), weekend });
  }
  return out;
};

const BREAKDOWN_30 = genBreakdownDays(30, 91);
const BREAKDOWN_90 = genBreakdownDays(90, 91);
// colors: TP = neon green, SL = red, Going = cyan (in-flight)
const OUTCOME_COLORS = { tp:'#39FF14', sl:'#FF3D57', going:'#00E5FF' };

// Sum helper for header metrics
const sumBreakdown = (days) => {
  const acc = { buy:{tp:0,sl:0,going:0,pnl:0,total:0}, sell:{tp:0,sl:0,going:0,pnl:0,total:0} };
  days.forEach(d => {
    if (d.empty) return;
    acc.buy.tp   += d.buy.tp;   acc.buy.sl   += d.buy.sl;   acc.buy.going   += d.buy.going;   acc.buy.pnl   += d.buy.pnl;
    acc.sell.tp  += d.sell.tp;  acc.sell.sl  += d.sell.sl;  acc.sell.going  += d.sell.going;  acc.sell.pnl  += d.sell.pnl;
  });
  acc.buy.total = acc.buy.tp + acc.buy.sl + acc.buy.going;
  acc.sell.total = acc.sell.tp + acc.sell.sl + acc.sell.going;
  return acc;
};

// Timeframe → dataset selector
const pickDays = (tf) => {
  if (tf === '1D') return BREAKDOWN_30.slice(-1);
  if (tf === '7D') return BREAKDOWN_30.slice(-7);
  if (tf === '30D') return BREAKDOWN_30;
  return BREAKDOWN_90; // 90D / YTD / ALL / Custom
};

// ─────────────────────────────────────────────────────────
// Variant A — Per-day "ladder": one row per day, mirrored bars BUY←→SELL
// ─────────────────────────────────────────────────────────

function DayLadderRow({ day, maxN, showLabels }) {
  const { buy, sell } = day;
  const empty = day.empty;
  // mirrored bar: left = BUY (fills right-to-left), right = SELL (fills left-to-right)
  const scale = n => (n / maxN) * 100;
  const buySegs  = [ {k:'sl',n:buy.sl,c:OUTCOME_COLORS.sl},  {k:'going',n:buy.going,c:OUTCOME_COLORS.going}, {k:'tp',n:buy.tp,c:OUTCOME_COLORS.tp} ];
  const sellSegs = [ {k:'tp',n:sell.tp,c:OUTCOME_COLORS.tp}, {k:'going',n:sell.going,c:OUTCOME_COLORS.going}, {k:'sl',n:sell.sl,c:OUTCOME_COLORS.sl} ];
  const buyTotal = buy.tp + buy.sl + buy.going;
  const sellTotal = sell.tp + sell.sl + sell.going;
  const dayPnl = buy.pnl + sell.pnl;
  const h = 14;
  return <div style={{display:'grid',gridTemplateColumns:'46px 42px 1fr 1fr 42px 60px',gap:6,alignItems:'center',padding:'2px 0',fontFamily:'var(--mantis-font-mono)',opacity: empty?0.35:1}}>
    {/* date */}
    <span style={{fontSize:10,color: day.weekend?'rgba(255,255,255,0.35)':'rgba(255,255,255,0.7)',letterSpacing:'0.02em'}}>{day.date.toLocaleDateString('it-IT',{day:'2-digit',month:'short'})}</span>
    {/* BUY total */}
    <span style={{fontSize:10,color: buyTotal>0?'#39FF14':'rgba(255,255,255,0.25)',textAlign:'right',fontWeight:700}}>{empty?'—':`▲${buyTotal}`}</span>
    {/* BUY mirrored bar (fills right-to-left) */}
    <div style={{display:'flex',justifyContent:'flex-end',height:h,background:'rgba(255,255,255,0.025)',borderRadius:2,overflow:'hidden'}}>
      {empty ? null : buySegs.map(s => s.n > 0 && (
        <div key={s.k} title={`BUY ${s.k.toUpperCase()} · ${s.n}`} style={{
          width:`${scale(s.n)}%`, background:s.c,
          boxShadow: s.k==='tp' ? 'inset 0 0 4px rgba(57,255,20,0.5)' : s.k==='going' ? 'inset 0 0 4px rgba(0,229,255,0.4)' : 'none',
          display:'flex',alignItems:'center',justifyContent:'center',
          fontSize:9,fontWeight:700,color: s.k==='going' ? '#002430' : '#000',
        }}>{showLabels && scale(s.n) > 8 ? s.n : ''}</div>
      ))}
    </div>
    {/* SELL bar (fills left-to-right) */}
    <div style={{display:'flex',height:h,background:'rgba(255,255,255,0.025)',borderRadius:2,overflow:'hidden'}}>
      {empty ? null : sellSegs.map(s => s.n > 0 && (
        <div key={s.k} title={`SELL ${s.k.toUpperCase()} · ${s.n}`} style={{
          width:`${scale(s.n)}%`, background:s.c,
          boxShadow: s.k==='tp' ? 'inset 0 0 4px rgba(57,255,20,0.5)' : s.k==='going' ? 'inset 0 0 4px rgba(0,229,255,0.4)' : 'none',
          display:'flex',alignItems:'center',justifyContent:'center',
          fontSize:9,fontWeight:700,color: s.k==='going' ? '#002430' : '#000',
        }}>{showLabels && scale(s.n) > 8 ? s.n : ''}</div>
      ))}
    </div>
    {/* SELL total */}
    <span style={{fontSize:10,color: sellTotal>0?'#FF3D57':'rgba(255,255,255,0.25)',fontWeight:700}}>{empty?'':`▼${sellTotal}`}</span>
    {/* day pnl */}
    <span style={{fontSize:10,fontWeight:700,color: dayPnl>0?'#39FF14':dayPnl<0?'#FF3D57':'rgba(255,255,255,0.25)',textAlign:'right',fontFeatureSettings:'"tnum" 1'}}>
      {empty?'—':`${dayPnl>0?'+':dayPnl<0?'−':''}€${Math.abs(dayPnl)>=1000?(Math.abs(dayPnl)/1000).toFixed(1)+'k':Math.abs(dayPnl).toFixed(0)}`}
    </span>
  </div>;
}

function TradeBreakdownA({ tf='30D' }) {
  const days = pickDays(tf);
  const totals = sumBreakdown(days);
  // max trades in any day — for bar scaling
  const maxN = Math.max(1, ...days.map(d => Math.max(d.buy.tp+d.buy.sl+d.buy.going, d.sell.tp+d.sell.sl+d.sell.going)));
  // scroll if > 15 rows
  const dense = days.length > 15;

  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)', borderTop:'2px solid #00d97e',
    borderRadius:6, padding:'10px 12px', display:'flex', flexDirection:'column', gap:6,
  }}>
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
      <Label>Trade Breakdown · per day</Label>
      <div style={{display:'flex',gap:10,fontSize:9,fontFamily:'var(--mantis-font-mono)',color:'rgba(255,255,255,0.55)'}}>
        <span><span style={{display:'inline-block',width:8,height:8,background:'#39FF14',borderRadius:2,marginRight:4,verticalAlign:'middle'}}/>TP</span>
        <span><span style={{display:'inline-block',width:8,height:8,background:'#00E5FF',borderRadius:2,marginRight:4,verticalAlign:'middle'}}/>Going</span>
        <span><span style={{display:'inline-block',width:8,height:8,background:'#FF3D57',borderRadius:2,marginRight:4,verticalAlign:'middle'}}/>SL</span>
        <span style={{color:'rgba(255,255,255,0.4)'}}>{tf} · {days.filter(d=>!d.empty).length} days</span>
      </div>
    </div>

    {/* column header */}
    <div style={{display:'grid',gridTemplateColumns:'46px 42px 1fr 1fr 42px 60px',gap:6,alignItems:'center',fontSize:8,color:'rgba(255,255,255,0.35)',letterSpacing:'0.12em',textTransform:'uppercase',fontFamily:'var(--mantis-font-mono)',paddingBottom:2,borderBottom:'1px solid rgba(255,255,255,0.05)'}}>
      <span>date</span>
      <span style={{textAlign:'right',color:'#39FF14'}}>▲ buy</span>
      <span style={{textAlign:'right'}}>← tp·go·sl</span>
      <span>tp·go·sl →</span>
      <span style={{color:'#FF3D57'}}>sell ▼</span>
      <span style={{textAlign:'right'}}>P&L</span>
    </div>

    {/* rows */}
    <div style={{display:'flex',flexDirection:'column',gap:0,maxHeight: dense?310:'auto',overflowY: dense?'auto':'visible'}}>
      {days.map((d,i) => <DayLadderRow key={i} day={d} maxN={maxN} showLabels={!dense}/>)}
    </div>

    {/* footer totals */}
    <div style={{display:'grid',gridTemplateColumns:'46px 42px 1fr 1fr 42px 60px',gap:6,alignItems:'center',fontFamily:'var(--mantis-font-mono)',fontSize:10,fontWeight:700,borderTop:'1px solid rgba(255,255,255,0.08)',paddingTop:4,marginTop:2}}>
      <span style={{color:'rgba(255,255,255,0.7)',letterSpacing:'0.08em',textTransform:'uppercase',fontSize:9}}>Σ {tf}</span>
      <span style={{color:'#39FF14',textAlign:'right'}}>▲{totals.buy.total}</span>
      <span style={{fontSize:9,color:'rgba(255,255,255,0.6)',textAlign:'right'}}>TP {totals.buy.tp} · Go {totals.buy.going} · SL {totals.buy.sl}</span>
      <span style={{fontSize:9,color:'rgba(255,255,255,0.6)'}}>TP {totals.sell.tp} · Go {totals.sell.going} · SL {totals.sell.sl}</span>
      <span style={{color:'#FF3D57'}}>▼{totals.sell.total}</span>
      <span style={{color:(totals.buy.pnl+totals.sell.pnl)>=0?'#39FF14':'#FF3D57',textAlign:'right'}}>+€{((totals.buy.pnl+totals.sell.pnl)/1000).toFixed(1)}k</span>
    </div>
  </div>;
}

// ─────────────────────────────────────────────────────────
// Variant B — "Mission log": column-per-day chart with stacked bars above/below zero
// BUY stacks up (+), SELL stacks down (−), each colored by outcome. A dense timeline.
// ─────────────────────────────────────────────────────────

function TradeBreakdownB({ tf='30D' }) {
  const days = pickDays(tf);
  const totals = sumBreakdown(days);
  const maxN = Math.max(1, ...days.map(d => Math.max(d.buy.tp+d.buy.sl+d.buy.going, d.sell.tp+d.sell.sl+d.sell.going)));
  const [hover, setHover] = React.useState(days.length-1);
  const H = 110; // half-height per side
  const COL_GAP = 1;
  const stackH = n => (n/maxN) * H;
  const f = days[hover];
  const fPnl = f.empty ? 0 : f.buy.pnl + f.sell.pnl;

  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)',
    borderRadius:6, padding:'10px 12px', display:'flex', flexDirection:'column', gap:8,
  }}>
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
      <Label>Trade Breakdown · per day · BUY ▲ / SELL ▼</Label>
      <div style={{display:'flex',gap:12,fontSize:9,fontFamily:'var(--mantis-font-mono)',color:'rgba(255,255,255,0.55)'}}>
        <span>{tf} · {days.filter(d=>!d.empty).length} days · Σ {totals.buy.total+totals.sell.total} trade</span>
        <span><span style={{display:'inline-block',width:8,height:8,background:'#39FF14',borderRadius:2,marginRight:4,verticalAlign:'middle'}}/>TP</span>
        <span><span style={{display:'inline-block',width:8,height:8,background:'#00E5FF',borderRadius:2,marginRight:4,verticalAlign:'middle'}}/>Going</span>
        <span><span style={{display:'inline-block',width:8,height:8,background:'#FF3D57',borderRadius:2,marginRight:4,verticalAlign:'middle'}}/>SL</span>
      </div>
    </div>

    <div style={{display:'grid',gridTemplateColumns:'1fr 200px',gap:14,alignItems:'stretch'}}>
      {/* mission log — day columns */}
      <div style={{display:'flex',flexDirection:'column',gap:2}}>
        <div style={{display:'flex',gap:COL_GAP,alignItems:'flex-end',height:H,padding:'0 2px'}}>
          {days.map((d,i) => {
            const isHover = i === hover;
            if (d.empty) return <div key={i} onMouseEnter={()=>setHover(i)} style={{flex:1,height:'100%',background:isHover?'rgba(255,255,255,0.04)':'transparent',borderRadius:2}}/>;
            const segs = [
              {k:'sl',n:d.buy.sl,c:OUTCOME_COLORS.sl},
              {k:'going',n:d.buy.going,c:OUTCOME_COLORS.going},
              {k:'tp',n:d.buy.tp,c:OUTCOME_COLORS.tp}, // on top
            ];
            return <div key={i} onMouseEnter={()=>setHover(i)} style={{flex:1,display:'flex',flexDirection:'column',justifyContent:'flex-end',gap:0,cursor:'pointer',
              background:isHover?'rgba(255,255,255,0.04)':'transparent',borderRadius:'2px 2px 0 0',
            }}>
              {segs.map(s => s.n>0 && <div key={s.k} style={{
                height: stackH(s.n), minHeight: s.n>0?2:0, background: s.c,
                boxShadow: isHover && s.k==='tp' ? 'inset 0 0 6px rgba(57,255,20,0.6), 0 0 6px rgba(57,255,20,0.4)' :
                           s.k==='tp' ? 'inset 0 0 4px rgba(57,255,20,0.35)' :
                           s.k==='going' ? 'inset 0 0 3px rgba(0,229,255,0.35)' : 'none',
              }}/>)}
            </div>;
          })}
        </div>
        {/* zero axis */}
        <div style={{height:1,background:'rgba(255,255,255,0.2)',position:'relative'}}>
          <span style={{position:'absolute',right:0,top:-14,fontSize:9,color:'rgba(255,255,255,0.35)',fontFamily:'var(--mantis-font-mono)'}}>0</span>
        </div>
        <div style={{display:'flex',gap:COL_GAP,alignItems:'flex-start',height:H,padding:'0 2px'}}>
          {days.map((d,i) => {
            const isHover = i === hover;
            if (d.empty) return <div key={i} onMouseEnter={()=>setHover(i)} style={{flex:1,height:'100%',background:isHover?'rgba(255,255,255,0.04)':'transparent',borderRadius:2}}/>;
            const segs = [
              {k:'sl',n:d.sell.sl,c:OUTCOME_COLORS.sl},
              {k:'going',n:d.sell.going,c:OUTCOME_COLORS.going},
              {k:'tp',n:d.sell.tp,c:OUTCOME_COLORS.tp}, // on bottom (closest to zero)
            ].reverse(); // so TP is at top (closest to zero axis) on the bottom half
            return <div key={i} onMouseEnter={()=>setHover(i)} style={{flex:1,display:'flex',flexDirection:'column',gap:0,cursor:'pointer',
              background:isHover?'rgba(255,255,255,0.04)':'transparent',borderRadius:'0 0 2px 2px',
            }}>
              {segs.map(s => s.n>0 && <div key={s.k} style={{
                height: stackH(s.n), minHeight: s.n>0?2:0, background: s.c,
                boxShadow: isHover && s.k==='tp' ? 'inset 0 0 6px rgba(57,255,20,0.6), 0 0 6px rgba(57,255,20,0.4)' :
                           s.k==='tp' ? 'inset 0 0 4px rgba(57,255,20,0.35)' :
                           s.k==='going' ? 'inset 0 0 3px rgba(0,229,255,0.35)' : 'none',
              }}/>)}
            </div>;
          })}
        </div>
        {/* axis labels — sparse */}
        <div style={{display:'flex',justifyContent:'space-between',fontSize:9,color:'rgba(255,255,255,0.35)',fontFamily:'var(--mantis-font-mono)',paddingTop:4}}>
          <span>{days[0].date.toLocaleDateString('it-IT',{day:'2-digit',month:'short'})}</span>
          {days.length > 14 && <span>{days[Math.floor(days.length/2)].date.toLocaleDateString('it-IT',{day:'2-digit',month:'short'})}</span>}
          <span>{days[days.length-1].date.toLocaleDateString('it-IT',{day:'2-digit',month:'short'})} · today</span>
        </div>
      </div>

      {/* focus readout */}
      <div style={{display:'flex',flexDirection:'column',gap:6,padding:'8px 10px',background:'rgba(255,255,255,0.025)',border:'1px solid rgba(0,217,126,0.18)',borderRadius:4,fontFamily:'var(--mantis-font-mono)'}}>
        <div style={{fontSize:9,letterSpacing:'.22em',textTransform:'uppercase',color:'rgba(255,255,255,0.45)',fontWeight:700}}>Focus day</div>
        <div style={{fontSize:11,color:'rgba(255,255,255,0.9)'}}>{f.date.toLocaleDateString('it-IT',{weekday:'short',day:'numeric',month:'short'})}</div>
        {f.empty ? <div style={{fontSize:10,color:'rgba(255,255,255,0.4)'}}>— no trades</div> : <>
          <div style={{display:'grid',gridTemplateColumns:'1fr auto',gap:'2px 8px',fontSize:11}}>
            <span style={{color:'#39FF14',fontWeight:700}}>▲ BUY {f.buy.tp+f.buy.sl+f.buy.going}</span>
            <span style={{color:'rgba(255,255,255,0.75)',fontSize:10}}>TP {f.buy.tp} · Go {f.buy.going} · SL {f.buy.sl}</span>
            <span style={{color:'#FF3D57',fontWeight:700}}>▼ SELL {f.sell.tp+f.sell.sl+f.sell.going}</span>
            <span style={{color:'rgba(255,255,255,0.75)',fontSize:10}}>TP {f.sell.tp} · Go {f.sell.going} · SL {f.sell.sl}</span>
          </div>
          <div style={{borderTop:'1px solid rgba(255,255,255,0.06)',paddingTop:4,marginTop:2,display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
            <span style={{fontSize:9,color:'rgba(255,255,255,0.5)',textTransform:'uppercase',letterSpacing:'.12em'}}>Day P&L</span>
            <span style={{fontSize:18,fontWeight:700,color: fPnl>=0?'#39FF14':'#FF3D57',fontFeatureSettings:'"tnum" 1',textShadow: fPnl>=0?'0 0 8px rgba(57,255,20,0.4)':'none'}}>
              {fPnl>0?'+':fPnl<0?'−':''}€{Math.abs(fPnl).toLocaleString('it-IT')}
            </span>
          </div>
          {(f.buy.going+f.sell.going)>0 && <div style={{fontSize:10,color:'#00E5FF',padding:'3px 6px',background:'rgba(0,229,255,0.08)',borderRadius:3,borderLeft:'2px solid #00E5FF'}}>
            ⏱ {f.buy.going+f.sell.going} trade ancora aperte
          </div>}
        </>}
      </div>
    </div>
  </div>;
}

Object.assign(window, { BREAKDOWN_30, BREAKDOWN_90, TradeBreakdownA, TradeBreakdownB, pickDays });
