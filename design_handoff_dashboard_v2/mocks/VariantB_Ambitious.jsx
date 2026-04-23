// VariantB_Ambitious.jsx — single-spine "cockpit" layout
// Central equity spine with underwater DD overlay; KPIs as readout rails around it;
// heatmap as calendar mosaic with a focus cell; duration as scatter diagnostic.

function EquitySpine({ height=190 }) {
  const pts = EQUITY;
  const w = 900, h = height;
  const vs = pts.map(p=>p.v); const mn = Math.min(...vs), mx = Math.max(...vs);
  const eqY = v => h*0.55 - ((v-mn)/(mx-mn))*h*0.5;
  const path = pts.map((p,i)=>`${i===0?'M':'L'} ${(i/(pts.length-1))*w} ${eqY(p.v)}`).join(' ');
  const area = path + ` L ${w} ${h*0.55} L 0 ${h*0.55} Z`;
  const peakPath = pts.map((p,i)=>`${i===0?'M':'L'} ${(i/(pts.length-1))*w} ${eqY(p.peak)}`).join(' ');
  // DD band below zero line
  const ddY = p => h*0.55 + (-p.dd * h * 3.2);
  const ddArea = pts.map((p,i)=>`${i===0?'M':'L'} ${(i/(pts.length-1))*w} ${ddY(p)}`).join(' ') + ` L ${w} ${h*0.55} L 0 ${h*0.55} Z`;
  // markers
  const maxDDIdx = pts.reduce((mi,p,i)=> p.dd<pts[mi].dd?i:mi, 0);
  const peakIdx = pts.reduce((mi,p,i)=> p.v>pts[mi].v?i:mi, 0);

  return <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{width:'100%',height:h,display:'block'}}>
    <defs>
      <linearGradient id="eqSpine" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#39FF14" stopOpacity=".5"/><stop offset="100%" stopColor="#39FF14" stopOpacity="0"/></linearGradient>
      <linearGradient id="ddSpine" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#FF3D57" stopOpacity="0"/><stop offset="100%" stopColor="#FF3D57" stopOpacity=".45"/></linearGradient>
      <pattern id="spineGrid" width="45" height="20" patternUnits="userSpaceOnUse"><path d="M 45 0 L 0 0 0 20" stroke="rgba(255,255,255,0.03)" fill="none"/></pattern>
    </defs>
    <rect x="0" y="0" width={w} height={h} fill="url(#spineGrid)"/>
    <line x1="0" x2={w} y1={h*0.55} y2={h*0.55} stroke="rgba(255,255,255,0.12)" strokeDasharray="3 3"/>
    {/* equity area + line */}
    <path d={area} fill="url(#eqSpine)"/>
    <path d={peakPath} stroke="rgba(255,255,255,0.25)" fill="none" strokeWidth="1" strokeDasharray="2 3"/>
    <path d={path} stroke="#39FF14" fill="none" strokeWidth="1.6" style={{filter:'drop-shadow(0 0 4px rgba(57,255,20,0.6))'}}/>
    {/* dd band */}
    <path d={ddArea} fill="url(#ddSpine)"/>
    <path d={pts.map((p,i)=>`${i===0?'M':'L'} ${(i/(pts.length-1))*w} ${ddY(p)}`).join(' ')} stroke="#FF3D57" fill="none" strokeWidth="1" opacity="0.9"/>
    {/* peak marker */}
    <g transform={`translate(${(peakIdx/(pts.length-1))*w}, ${eqY(pts[peakIdx].v)})`}>
      <circle r="4" fill="#39FF14" style={{filter:'drop-shadow(0 0 6px rgba(57,255,20,0.9))'}}/>
      <text x="8" y="-6" fill="#39FF14" fontSize="10" fontFamily="var(--mantis-font-mono)" fontWeight="700">PEAK €{Math.round(pts[peakIdx].v).toLocaleString()}</text>
    </g>
    {/* max DD marker */}
    <g transform={`translate(${(maxDDIdx/(pts.length-1))*w}, ${ddY(pts[maxDDIdx])})`}>
      <circle r="4" fill="#FF3D57" style={{filter:'drop-shadow(0 0 6px rgba(255,61,87,0.9))'}}/>
      <text x="8" y="14" fill="#FF3D57" fontSize="10" fontFamily="var(--mantis-font-mono)" fontWeight="700">MAX DD {(pts[maxDDIdx].dd*100).toFixed(1)}%</text>
    </g>
    {/* zero label */}
    <text x="6" y={h*0.55 - 4} fill="rgba(255,255,255,0.35)" fontSize="9" fontFamily="var(--mantis-font-mono)">BREAKEVEN</text>
  </svg>;
}

function RailKPI({ label, value, sub, color='#fff', accent='#39FF14', right=false }) {
  return <div style={{
    display:'flex',flexDirection:'column',gap:2,
    padding:'8px 12px',
    background:'rgba(255,255,255,0.015)',
    border:'1px solid rgba(255,255,255,0.05)',
    borderLeft: right?'none':`2px solid ${accent}`,
    borderRight: right?`2px solid ${accent}`:'none',
    borderRadius:4,
    textAlign: right?'right':'left',
    fontFamily:'var(--mantis-font-mono)',
  }}>
    <div style={{fontSize:9,letterSpacing:'.22em',textTransform:'uppercase',color:'rgba(255,255,255,0.4)',fontWeight:700}}>{label}</div>
    <div style={{fontSize:18,fontWeight:700,color,lineHeight:1.05,fontFeatureSettings:'"tnum" 1'}}>{value}</div>
    {sub && <div style={{fontSize:10,color:'rgba(255,255,255,0.5)'}}>{sub}</div>}
  </div>;
}

function DurationScatter() {
  const r = rand(7);
  // x = duration minutes (0-180), y = PnL (-400..600)
  const points = [];
  for (let i = 0; i < 180; i++) {
    const win = r() > 0.38;
    const dur = win ? 20 + r()*80 : 45 + r()*110;
    const pnl = win ? 30 + r()*400 : -(20 + r()*380);
    points.push({ dur, pnl, win });
  }
  const W = 280, H = 140;
  const xS = x => (x/180)*W;
  const yS = y => H/2 - (y/600)*(H/2 - 6);
  return <svg viewBox={`0 0 ${W} ${H}`} style={{width:'100%',height:H,display:'block'}}>
    <defs><pattern id="scatG" width="40" height="20" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 20" stroke="rgba(255,255,255,0.03)" fill="none"/></pattern></defs>
    <rect x="0" y="0" width={W} height={H} fill="url(#scatG)"/>
    <line x1="0" x2={W} y1={H/2} y2={H/2} stroke="rgba(255,255,255,0.15)" strokeDasharray="2 3"/>
    {/* median markers */}
    <line x1={xS(47)} x2={xS(47)} y1={H/2} y2={yS(200)} stroke="#39FF14" strokeDasharray="2 2" opacity="0.4"/>
    <line x1={xS(68)} x2={xS(68)} y1={H/2} y2={yS(-180)} stroke="#FF3D57" strokeDasharray="2 2" opacity="0.4"/>
    {points.map((p,i)=> <circle key={i} cx={xS(p.dur)} cy={yS(p.pnl)} r="2.2"
      fill={p.win?'#39FF14':'#FF3D57'} opacity="0.65"
      style={{filter: Math.abs(p.pnl)>300 ? `drop-shadow(0 0 4px ${p.win?'rgba(57,255,20,0.8)':'rgba(255,61,87,0.8)'})` : 'none'}}/>)}
    <text x="4" y="12" fill="rgba(57,255,20,0.7)" fontSize="9" fontFamily="var(--mantis-font-mono)">+€</text>
    <text x="4" y={H-4} fill="rgba(255,61,87,0.7)" fontSize="9" fontFamily="var(--mantis-font-mono)">−€</text>
    <text x={W-38} y={H-4} fill="rgba(255,255,255,0.35)" fontSize="9" fontFamily="var(--mantis-font-mono)">dur →</text>
  </svg>;
}

function CalendarMosaic() {
  const cells = HEATMAP_90;
  const max = Math.max(...cells.map(c=>Math.abs(c.pnl)));
  const [focus, setFocus] = React.useState(cells.length-1);
  // flexible square grid
  const side = Math.ceil(Math.sqrt(cells.length));
  // group by week for better reading
  const weeks = [];
  let curWeek = new Array(7).fill(null);
  cells.forEach((c, i) => {
    const dow = c.date.getDay();
    curWeek[dow] = c;
    if (dow === 6 || i === cells.length-1) { weeks.push(curWeek); curWeek = new Array(7).fill(null); }
  });
  const f = cells[focus];
  return <div style={{display:'grid',gridTemplateColumns:'1fr auto',gap:14,alignItems:'stretch'}}>
    <div style={{display:'flex',flexDirection:'column',gap:4}}>
      <div style={{display:'flex',gap:3}}>
        <div style={{display:'flex',flexDirection:'column',gap:3,fontSize:8,color:'rgba(255,255,255,0.3)',fontFamily:'var(--mantis-font-mono)',width:14,paddingTop:2}}>
          {['M','T','W','T','F','S','S'].map((d,i)=><div key={i} style={{height:26}}>{d}</div>)}
        </div>
        <div style={{display:'flex',gap:3,flex:1}}>
          {weeks.map((w,wi) => <div key={wi} style={{display:'flex',flexDirection:'column',gap:3,flex:1,minWidth:0}}>
            {[1,2,3,4,5,6,0].map((dow,di) => {
              const c = w[dow];
              if (!c) return <div key={di} style={{height:26,background:'rgba(255,255,255,0.01)',borderRadius:2}}/>;
              const color = heatColor(c.pnl, max);
              const isFocus = cells.indexOf(c) === focus;
              return <div key={di} onMouseEnter={()=>setFocus(cells.indexOf(c))} style={{
                height:26, background: color.bg, borderRadius:2,
                display:'flex',alignItems:'center',justifyContent:'center',
                fontFamily:'var(--mantis-font-mono)',cursor:'pointer',
                boxShadow: color.glow || 'none',
                border: isFocus ? '1px solid #fff' : (c.empty?'1px dashed rgba(255,255,255,0.05)':'1px solid transparent'),
                outline: isFocus ? '1px solid rgba(255,255,255,0.4)' : 'none',
                fontSize:8,color:color.fg,fontWeight:700,transition:'transform 120ms',
                transform: isFocus?'scale(1.15)':'scale(1)',zIndex: isFocus?2:1,position:'relative',
              }}>
                {c.trades>0 && (Math.abs(c.pnl)>=1000?((c.pnl>0?'+':'−')+(Math.abs(c.pnl)/1000).toFixed(1)+'k'):(c.pnl>0?'+':c.pnl<0?'−':'')+Math.abs(c.pnl).toFixed(0))}
              </div>;
            })}
          </div>)}
        </div>
      </div>
    </div>
    {/* focus card */}
    <div style={{
      minWidth:170,background:'rgba(255,255,255,0.03)',border:'1px solid rgba(0,217,126,0.2)',
      borderRadius:6,padding:'10px 12px',display:'flex',flexDirection:'column',gap:4,
      fontFamily:'var(--mantis-font-mono)',
    }}>
      <div style={{fontSize:9,letterSpacing:'.2em',textTransform:'uppercase',color:'rgba(255,255,255,0.5)'}}>Focus</div>
      <div style={{fontSize:11,color:'rgba(255,255,255,0.85)'}}>{f.date.toLocaleDateString('it-IT',{weekday:'short',day:'numeric',month:'short'})}</div>
      <div style={{fontSize:20,fontWeight:700,color: f.pnl>0?'#39FF14':f.pnl<0?'#FF3D57':'rgba(255,255,255,0.4)',textShadow: f.pnl>0?'0 0 10px rgba(57,255,20,0.4)':'none'}}>
        {f.pnl===0?'— flat':((f.pnl>0?'+':'−')+'€'+Math.abs(f.pnl).toLocaleString('it-IT'))}
      </div>
      <div style={{fontSize:10,color:'rgba(255,255,255,0.6)'}}>{f.pnl===0?'no trades':`${f.trades} trade · ${f.wins}W ${f.losses}L`}</div>
      {f.pnl!==0 && <div style={{fontSize:10,color:'rgba(255,255,255,0.5)'}}>{fmtPct(f.pnl/54000*100)} equity · {f.trades>0?((f.wins/f.trades)*100).toFixed(0):0}% hit</div>}
    </div>
  </div>;
}

function VariantB() {
  const [tf, setTf] = React.useState('30D');
  return <div style={{background:'#0d1117',color:'rgba(255,255,255,0.92)',fontFamily:'var(--mantis-font-ui)',padding:16,display:'flex',flexDirection:'column',gap:12,minHeight:'100%'}}>
    <OperationalStrip/>

    {/* TF + title */}
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:12}}>
      <div style={{display:'flex',alignItems:'center',gap:12}}>
        <h2 style={{fontSize:14,fontWeight:600,color:'rgba(255,255,255,0.85)',margin:0,letterSpacing:'.02em'}}>Performance Cockpit</h2>
        <span style={{fontSize:10,color:'rgba(255,255,255,0.4)',fontFamily:'var(--mantis-font-mono)'}}>since 2026-01-22 · 412 closed trades · regime-gated</span>
      </div>
      <Segment options={TIMEFRAMES} active={tf} onChange={setTf}/>
    </div>

    {/* The spine — central cockpit */}
    <div style={{
      background:'linear-gradient(180deg, #0d1117 0%, #10161e 100%)',
      border:'1px solid rgba(0,217,126,0.22)',borderRadius:8,padding:'14px 16px',
      position:'relative',overflow:'hidden',
    }}>
      <div style={{position:'absolute',inset:0,background:'radial-gradient(circle at 50% 40%, rgba(57,255,20,0.04) 0%, transparent 60%)',pointerEvents:'none'}}/>
      <div style={{display:'grid',gridTemplateColumns:'auto 1fr auto',gap:14,alignItems:'stretch',position:'relative'}}>
        {/* Left rail */}
        <div style={{display:'flex',flexDirection:'column',gap:6,minWidth:165}}>
          <RailKPI label="Profit Factor" value="1.87" color="#39FF14" sub="gross +24.8k / −13.3k · soglia 1.3 ✓" accent="#39FF14"/>
          <RailKPI label="Calmar" value="2.41" color="#39FF14" sub="Sharpe 1.62 · Sortino 2.18" accent="#00E5FF"/>
          <RailKPI label="Expectancy" value="+€27.60" color="#fff" sub="per trade · 412 closed" accent="#00d97e"/>
        </div>

        {/* Spine chart */}
        <div style={{display:'flex',flexDirection:'column',gap:6}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',fontFamily:'var(--mantis-font-mono)'}}>
            <div>
              <span style={{fontSize:9,letterSpacing:'.22em',textTransform:'uppercase',color:'rgba(255,255,255,0.4)',fontWeight:700}}>Equity Spine</span>
              <span style={{fontSize:9,color:'rgba(255,255,255,0.35)',marginLeft:10}}>▬ equity  ┄ peak  ▬ drawdown</span>
            </div>
            <div style={{display:'flex',gap:14,fontSize:10}}>
              <span style={{color:'rgba(255,255,255,0.55)'}}>curr <span style={{color:'#fff',fontWeight:700}}>€54,812.09</span></span>
              <span style={{color:'#39FF14'}}>ROI +9.62%</span>
              <span style={{color:'#39FF14'}}>ann. +34.7%</span>
            </div>
          </div>
          <EquitySpine/>
          <div style={{display:'flex',justifyContent:'space-between',fontSize:9,fontFamily:'var(--mantis-font-mono)',color:'rgba(255,255,255,0.4)'}}>
            <span>Jan 22</span><span>Feb 14</span><span>Mar 8</span><span>Mar 30</span><span>Apr 22 · today</span>
          </div>
        </div>

        {/* Right rail — critical / psychological */}
        <div style={{display:'flex',flexDirection:'column',gap:6,minWidth:175}}>
          <RailKPI label="Max Drawdown" value="−8.42%" color="#FF3D57" sub="12d dal peak · rec. in corso" accent="#FF3D57" right/>
          <RailKPI label="Current DD" value="−2.1%" color="#FFB020" sub="€54,812 vs peak €57,340" accent="#FFB020" right/>
          <RailKPI label="Win Rate" value="62.4%" color="#39FF14" sub="258W · 154L · ▲ +1.8pp" accent="#39FF14" right/>
        </div>
      </div>
    </div>

    {/* Trade breakdown row — KPI secondario, in fondo */}

    {/* Bottom 3 rows: duration scatter, funding ring, calendar */}
    <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1.7fr',gap:10}}>
      {/* Duration scatter */}
      <div style={{background:'#161b22',border:'1px solid rgba(0,217,126,0.15)',borderRadius:6,padding:'10px 12px',display:'flex',flexDirection:'column',gap:6}}>
        <Label right={<span style={{fontFamily:'var(--mantis-font-mono)',fontSize:9,color:'rgba(255,255,255,0.5)',letterSpacing:'0.04em',textTransform:'none'}}>180 trade · €/h axis</span>}>
          Duration ✕ PnL
        </Label>
        <DurationScatter/>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,fontFamily:'var(--mantis-font-mono)',fontSize:10}}>
          <div style={{color:'#39FF14'}}>● win <span style={{color:'rgba(255,255,255,0.7)'}}>47m · +€38.20/h</span></div>
          <div style={{color:'#FF3D57',textAlign:'right'}}>● loss <span style={{color:'rgba(255,255,255,0.7)'}}>1h08m · −€28.70/h</span></div>
        </div>
        <div style={{fontSize:10,color:'#FFB020',fontFamily:'var(--mantis-font-mono)',padding:'3px 6px',background:'rgba(255,176,32,0.08)',borderRadius:3,borderLeft:'2px solid #FFB020'}}>
          ⚠ loss dura 45% più del win · late-exit bias
        </div>
      </div>

      {/* Funding ring */}
      <div style={{background:'#161b22',border:'1px solid rgba(255,176,32,0.25)',borderRadius:6,padding:'10px 12px',display:'flex',flexDirection:'column',gap:6}}>
        <Label right={<span style={{fontFamily:'var(--mantis-font-mono)',fontSize:9,color:'#FFB020',fontWeight:700,letterSpacing:'0.08em'}}>BYBIT · BTC</span>}>Funding Exposure</Label>
        <div style={{display:'flex',alignItems:'center',gap:10,flex:1}}>
          <svg width="96" height="96" viewBox="0 0 96 96">
            <circle cx="48" cy="48" r="38" stroke="rgba(255,255,255,0.06)" strokeWidth="8" fill="none"/>
            <circle cx="48" cy="48" r="38" stroke="#FFB020" strokeWidth="8" fill="none"
              strokeDasharray="239" strokeDashoffset="95" strokeLinecap="round"
              transform="rotate(-90 48 48)" style={{filter:'drop-shadow(0 0 6px rgba(255,176,32,0.6))'}}/>
            <text x="48" y="46" textAnchor="middle" fill="#fff" fontSize="11" fontFamily="var(--mantis-font-mono)" fontWeight="700">−0.04%</text>
            <text x="48" y="60" textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="8" fontFamily="var(--mantis-font-mono)">per 8h</text>
          </svg>
          <div style={{display:'flex',flexDirection:'column',gap:3,fontFamily:'var(--mantis-font-mono)',flex:1}}>
            <div style={{fontSize:20,fontWeight:700,color:'#FF3D57',lineHeight:1}}>−€127.40</div>
            <div style={{fontSize:10,color:'rgba(255,255,255,0.5)'}}>7d accum</div>
            <div style={{fontSize:10,color:'rgba(255,255,255,0.7)',marginTop:4}}>BTC long 0.12</div>
            <div style={{fontSize:10,color:'rgba(255,255,255,0.7)'}}>€7,858 notional</div>
            <div style={{fontSize:10,color:'#FFB020',marginTop:4}}>next 04:38</div>
          </div>
        </div>
      </div>

      {/* Calendar mosaic */}
      <div style={{background:'#161b22',border:'1px solid rgba(0,217,126,0.15)',borderRadius:6,padding:'10px 12px',display:'flex',flexDirection:'column',gap:6}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
          <Label>Daily Heatmap · 90d</Label>
          <div style={{display:'flex',gap:10,fontSize:10,fontFamily:'var(--mantis-font-mono)',color:'rgba(255,255,255,0.55)'}}>
            <span>best <span style={{color:'#39FF14'}}>+€1,408</span></span>
            <span>worst <span style={{color:'#FF3D57'}}>−€612</span></span>
          </div>
        </div>
        <CalendarMosaic/>
      </div>
    </div>

    {/* Trade Breakdown per day — KPI secondario, in fondo */}
    <TradeBreakdownB tf={tf}/>
  </div>;
}

Object.assign(window, { VariantB });
