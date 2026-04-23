// VariantA_Conservative.jsx — Bloomberg-dense classical grid layout
function KpiCardA({ title, value, valueColor='#fff', sub, spark, sparkColor='#39FF14', note, noteColor, accent='#00d97e' }) {
  return <div style={{
    background:'#161b22', border:'1px solid rgba(0,217,126,0.15)', borderTop:`2px solid ${accent}`,
    borderRadius:6, padding:'10px 12px', display:'flex', flexDirection:'column', gap:4,
    position:'relative', overflow:'hidden', minHeight:110,
  }}>
    {/* sparkline sits as absolute background in bottom-right corner — never collides with text */}
    {spark && <div style={{position:'absolute',right:8,bottom:8,opacity:0.7,pointerEvents:'none'}}>
      <MiniSpark data={spark} color={sparkColor} w={56} h={18}/>
    </div>}
    <Label>{title}</Label>
    <div style={{fontFamily:'var(--mantis-font-mono)',fontWeight:700,fontSize:22,letterSpacing:'.02em',color:valueColor,fontFeatureSettings:'"tnum" 1',lineHeight:1.05,position:'relative',zIndex:1}}>{value}</div>
    {sub && <div style={{fontSize:10,color:'rgba(255,255,255,0.5)',fontFamily:'var(--mantis-font-mono)',position:'relative',zIndex:1}}>{sub}</div>}
    {note && <div style={{fontSize:10,color:noteColor||'rgba(255,255,255,0.6)',fontFamily:'var(--mantis-font-mono)',fontWeight:600,position:'relative',zIndex:1}}>{note}</div>}
  </div>;
}

function UnderwaterChart() {
  const pts = EQUITY;
  const w = 320, h = 80;
  const ddPath = pts.map((p,i)=>`${i===0?'M':'L'} ${(i/(pts.length-1))*w} ${-p.dd*100 * 2.2}`).join(' ') + ` L ${w} 0 L 0 0 Z`;
  const linePath = pts.map((p,i)=>`${i===0?'M':'L'} ${(i/(pts.length-1))*w} ${-p.dd*100 * 2.2}`).join(' ');
  return <svg viewBox={`0 -${h} ${w} ${h}`} preserveAspectRatio="none" style={{width:'100%',height:h,display:'block'}}>
    <defs><linearGradient id="ddGrad" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#FF3D57" stopOpacity="0"/><stop offset="100%" stopColor="#FF3D57" stopOpacity=".4"/></linearGradient></defs>
    <line x1="0" x2={w} y1="0" y2="0" stroke="rgba(255,255,255,.12)" strokeDasharray="2 2"/>
    <path d={ddPath} fill="url(#ddGrad)"/>
    <path d={linePath} stroke="#FF3D57" fill="none" strokeWidth="1.2"/>
  </svg>;
}

function EquityChartA() {
  const pts = EQUITY;
  const w = 600, h = 140;
  const vs = pts.map(p=>p.v); const mn = Math.min(...vs), mx = Math.max(...vs);
  const path = pts.map((p,i)=>`${i===0?'M':'L'} ${(i/(pts.length-1))*w} ${h - ((p.v-mn)/(mx-mn))*h}`).join(' ');
  const area = path + ` L ${w} ${h} L 0 ${h} Z`;
  return <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{width:'100%',height:h,display:'block'}}>
    <defs><linearGradient id="eqA" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#39FF14" stopOpacity=".35"/><stop offset="100%" stopColor="#39FF14" stopOpacity="0"/></linearGradient></defs>
    {[0.25, 0.5, 0.75].map(y => <line key={y} x1="0" x2={w} y1={h*y} y2={h*y} stroke="rgba(255,255,255,0.05)"/>)}
    <path d={area} fill="url(#eqA)"/>
    <path d={path} stroke="#39FF14" fill="none" strokeWidth="1.4" style={{filter:'drop-shadow(0 0 3px rgba(57,255,20,0.5))'}}/>
  </svg>;
}

function HeatmapA() {
  const cells = HEATMAP_90;
  const max = Math.max(...cells.map(c=>Math.abs(c.pnl)));
  // group by week (sunday start)
  const weeks = [];
  let curWeek = new Array(7).fill(null);
  let weekStart = cells[0].date.getDay();
  cells.forEach((c, i) => {
    const dow = c.date.getDay();
    curWeek[dow] = c;
    if (dow === 6 || i === cells.length-1) { weeks.push(curWeek); curWeek = new Array(7).fill(null); }
  });
  return <div style={{display:'flex',flexDirection:'column',gap:4}}>
    <div style={{display:'flex',gap:3}}>
      <div style={{display:'flex',flexDirection:'column',gap:3,fontSize:9,color:'rgba(255,255,255,0.35)',fontFamily:'var(--mantis-font-mono)',width:18,paddingTop:2}}>
        {['M','T','W','T','F','S','S'].map((d,i)=><div key={i} style={{height:24}}>{d}</div>)}
      </div>
      <div style={{display:'flex',gap:3,flex:1}}>
        {weeks.map((w,wi) => <div key={wi} style={{display:'flex',flexDirection:'column',gap:3,flex:1,minWidth:0}}>
          {[1,2,3,4,5,6,0].map((dow,di) => {
            const c = w[dow];
            if (!c) return <div key={di} style={{height:24,background:'rgba(255,255,255,0.015)',borderRadius:3}}/>;
            const color = heatColor(c.pnl, max);
            return <div key={di} title={`${c.date.toLocaleDateString()} · ${fmtEur(c.pnl)} · ${c.wins}W/${c.losses}L`} style={{
              height:24, background: color.bg, borderRadius:3, padding:'2px 4px',
              display:'flex',flexDirection:'column',justifyContent:'space-between',overflow:'hidden',
              fontFamily:'var(--mantis-font-mono)',cursor:'pointer',
              boxShadow: color.glow || 'none',
              border: c.empty ? '1px dashed rgba(255,255,255,0.05)' : 'none',
            }}>
              <div style={{display:'flex',justifyContent:'space-between',fontSize:8,color: color.fg, opacity:0.7, lineHeight:1}}>
                <span>{c.date.getDate()}</span>
                {c.trades>0 && <span>{c.wins}/{c.losses}</span>}
              </div>
              {c.trades>0 && <div style={{fontSize:9,fontWeight:700,color: color.fg, lineHeight:1,textAlign:'right'}}>
                {c.pnl>0?'+':'−'}{Math.abs(c.pnl)>=1000?(Math.abs(c.pnl)/1000).toFixed(1)+'k':Math.abs(c.pnl).toFixed(0)}
              </div>}
            </div>;
          })}
        </div>)}
      </div>
    </div>
    <div style={{display:'flex',justifyContent:'space-between',fontSize:9,fontFamily:'var(--mantis-font-mono)',color:'rgba(255,255,255,0.4)',paddingLeft:22}}>
      <span>90 giorni · {cells.filter(c=>c.pnl>0).length}W · {cells.filter(c=>c.pnl<0).length}L · {cells.filter(c=>c.empty).length} flat</span>
      <div style={{display:'flex',alignItems:'center',gap:4}}>
        <span>less</span>
        {[0.15,0.3,0.5,0.7,0.9].map(a=><span key={a} style={{width:10,height:10,background:`rgba(57,255,20,${a})`,borderRadius:2}}/>)}
        <span>more</span>
      </div>
    </div>
  </div>;
}

function VariantA() {
  const [tf, setTf] = React.useState('30D');
  return <div style={{background:'#0d1117',color:'rgba(255,255,255,0.92)',fontFamily:'var(--mantis-font-ui)',padding:16,display:'flex',flexDirection:'column',gap:12,minHeight:'100%'}}>
    <OperationalStrip/>

    {/* TF picker */}
    <div style={{display:'flex',alignItems:'center',gap:12,justifyContent:'space-between'}}>
      <div style={{display:'flex',alignItems:'center',gap:12}}>
        <h2 style={{fontSize:14,fontWeight:600,color:'rgba(255,255,255,0.85)',margin:0,letterSpacing:'0.02em'}}>Performance</h2>
        <span style={{fontSize:10,color:'rgba(255,255,255,0.4)',fontFamily:'var(--mantis-font-mono)'}}>since 2026-01-22 · 412 closed trades</span>
      </div>
      <Segment options={TIMEFRAMES} active={tf} onChange={setTf}/>
    </div>

    {/* 7 KPI grid — 4 cols top row, 3 cols + chart bottom */}
    <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
      <KpiCardA title="Win Rate" value="62.4%"
        valueColor="#fff"
        spark={[58,61,59,63,62,65,62,64,63,62.4].map(n=>n)} sparkColor="#39FF14"
        note="▲ +1.8pp vs prev"
        noteColor="#39FF14"
        sub="258W · 154L · 412 tot"/>

      <KpiCardA title="Profit Factor" value="1.87"
        valueColor="#39FF14"
        spark={[1.4,1.5,1.6,1.55,1.7,1.75,1.8,1.82,1.85,1.87]}
        note="› 1.3 soglia · ottimo"
        noteColor="#39FF14"
        sub="gross +€24.8k / −€13.3k"/>

      <KpiCardA title="Calmar Ratio" value="2.41"
        valueColor="#39FF14"
        spark={[1.8,2.0,1.9,2.1,2.2,2.15,2.3,2.35,2.4,2.41]}
        accent="#00E5FF"
        note="Sharpe 1.62 · Sortino 2.18"
        sub="ret/maxDD · 30d ann."/>

      <KpiCardA title="Max Drawdown" value="−8.42%"
        valueColor="#FF3D57"
        accent="#FF3D57"
        spark={[0,-1.2,-2.4,-3.8,-5.1,-6.2,-7.4,-8.4,-5.2,-2.1]}
        sparkColor="#FF3D57"
        note="peak €57,340 · 12d ago"
        noteColor="#FFB020"
        sub="current DD −2.1% · recovering"/>
    </div>

    <div style={{display:'grid',gridTemplateColumns:'1.2fr 1fr 1fr',gap:10}}>
      {/* Avg duration + PnL/hr */}
      <div style={{background:'#161b22',border:'1px solid rgba(0,217,126,0.15)',borderTop:'2px solid #00d97e',borderRadius:6,padding:'10px 12px',display:'flex',flexDirection:'column',gap:8}}>
        <Label right={<span style={{fontFamily:'var(--mantis-font-mono)',color:'rgba(255,255,255,0.5)',fontWeight:600,textTransform:'none',letterSpacing:0}}>trade timing</span>}>Duration & €/h</Label>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10,fontFamily:'var(--mantis-font-mono)'}}>
          <div style={{padding:'6px 8px',background:'rgba(57,255,20,0.06)',borderLeft:'2px solid #39FF14',borderRadius:3}}>
            <div style={{fontSize:9,color:'rgba(255,255,255,0.5)',textTransform:'uppercase',letterSpacing:'.12em'}}>WIN</div>
            <div style={{fontSize:16,fontWeight:700,color:'#39FF14'}}>47m <span style={{fontSize:10,opacity:0.6}}>avg</span></div>
            <div style={{fontSize:10,color:'rgba(255,255,255,0.65)'}}>€38.20/h · 258 trades</div>
          </div>
          <div style={{padding:'6px 8px',background:'rgba(255,61,87,0.06)',borderLeft:'2px solid #FF3D57',borderRadius:3}}>
            <div style={{fontSize:9,color:'rgba(255,255,255,0.5)',textTransform:'uppercase',letterSpacing:'.12em'}}>LOSS</div>
            <div style={{fontSize:16,fontWeight:700,color:'#FF3D57'}}>1h 08m</div>
            <div style={{fontSize:10,color:'rgba(255,255,255,0.65)'}}>−€28.70/h · 154 trades</div>
          </div>
        </div>
        <div style={{fontSize:10,color:'#FFB020',fontFamily:'var(--mantis-font-mono)',padding:'4px 8px',background:'rgba(255,176,32,0.08)',borderRadius:3,borderLeft:'2px solid #FFB020'}}>
          ⚠ loss avg dura 45% più del win · potenziale late-exit bias
        </div>
      </div>

      {/* Funding */}
      <div style={{background:'#161b22',border:'1px solid rgba(0,217,126,0.15)',borderTop:'2px solid #FFB020',borderRadius:6,padding:'10px 12px',display:'flex',flexDirection:'column',gap:6}}>
        <Label right={<span style={{fontSize:9,fontFamily:'var(--mantis-font-mono)',color:'rgba(255,176,32,0.9)',fontWeight:700,letterSpacing:'0.08em'}}>BYBIT PERP</span>}>Funding Exposure</Label>
        <div style={{display:'flex',alignItems:'baseline',gap:8}}>
          <span style={{fontFamily:'var(--mantis-font-mono)',fontWeight:700,fontSize:22,color:'#FF3D57',fontFeatureSettings:'"tnum" 1'}}>−€127.40</span>
          <span style={{fontSize:10,color:'rgba(255,255,255,0.5)',fontFamily:'var(--mantis-font-mono)'}}>7d accum</span>
        </div>
        <div style={{display:'flex',justifyContent:'space-between',fontSize:10,fontFamily:'var(--mantis-font-mono)',color:'rgba(255,255,255,0.7)'}}>
          <span>rate <span style={{color:'#FFB020'}}>−0.0412%/8h</span></span>
          <span>next <span style={{color:'rgba(255,255,255,0.85)'}}>04:38</span></span>
        </div>
        <div style={{fontSize:10,color:'rgba(255,255,255,0.55)',fontFamily:'var(--mantis-font-mono)'}}>BTC long · 0.12 BTC · €7,858 notional</div>
      </div>

      {/* Underwater DD */}
      <div style={{background:'#161b22',border:'1px solid rgba(255,61,87,0.2)',borderTop:'2px solid #FF3D57',borderRadius:6,padding:'10px 12px',display:'flex',flexDirection:'column',gap:6}}>
        <Label right={<span style={{fontFamily:'var(--mantis-font-mono)',fontSize:9,color:'#FF3D57'}}>peak-to-valley</span>}>Underwater</Label>
        <UnderwaterChart/>
        <div style={{display:'flex',justifyContent:'space-between',fontSize:10,fontFamily:'var(--mantis-font-mono)'}}>
          <span style={{color:'rgba(255,255,255,0.6)'}}>curr <span style={{color:'#FF3D57'}}>−2.1%</span></span>
          <span style={{color:'rgba(255,255,255,0.6)'}}>max <span style={{color:'#FF3D57'}}>−8.4%</span></span>
          <span style={{color:'rgba(255,255,255,0.6)'}}>days from peak <span style={{color:'#FFB020'}}>12</span></span>
        </div>
      </div>
    </div>

    {/* Trade Breakdown — BUY/SELL × Going/TP/SL */}
    <TradeBreakdownA tf={tf}/>

    {/* Equity + Heatmap row */}
    <div style={{display:'grid',gridTemplateColumns:'1.2fr 1.8fr',gap:10}}>
      <div style={{background:'#161b22',border:'1px solid rgba(0,217,126,0.15)',borderRadius:6,padding:'12px 14px',display:'flex',flexDirection:'column',gap:8}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
          <Label>Equity Curve</Label>
          <span style={{fontFamily:'var(--mantis-font-mono)',fontSize:18,fontWeight:700,color:'#fff'}}>€54,812.09</span>
        </div>
        <EquityChartA/>
        <div style={{display:'flex',gap:12,fontSize:10,fontFamily:'var(--mantis-font-mono)',color:'rgba(255,255,255,0.6)',flexWrap:'wrap'}}>
          <span>start <span style={{color:'rgba(255,255,255,0.85)'}}>€50,000</span></span>
          <span>ROI <span style={{color:'#39FF14'}}>+9.62%</span></span>
          <span>ann. <span style={{color:'#39FF14'}}>+34.7%</span></span>
          <span>volatility <span style={{color:'rgba(255,255,255,0.85)'}}>14.2%</span></span>
          <span>expectancy <span style={{color:'#39FF14'}}>€27.60/trade</span></span>
        </div>
      </div>

      <div style={{background:'#161b22',border:'1px solid rgba(0,217,126,0.15)',borderRadius:6,padding:'12px 14px',display:'flex',flexDirection:'column',gap:8}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
          <Label>Daily P&L Heatmap</Label>
          <div style={{display:'flex',gap:6,fontSize:10,fontFamily:'var(--mantis-font-mono)',color:'rgba(255,255,255,0.6)'}}>
            <span>best <span style={{color:'#39FF14'}}>+€1,408</span></span>
            <span>·</span>
            <span>worst <span style={{color:'#FF3D57'}}>−€612</span></span>
          </div>
        </div>
        <HeatmapA/>
      </div>
    </div>
  </div>;
}

Object.assign(window, { VariantA });
