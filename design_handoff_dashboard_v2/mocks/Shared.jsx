// Shared.jsx — primitives + mock data used by both variants
const TIMEFRAMES = ['1D','7D','30D','90D','YTD','ALL','Custom'];

// deterministic pseudo-random
const rand = (seed) => { let s = seed; return () => { s = (s*9301+49297)%233280; return s/233280; }; };

const genHeatmap = (days) => {
  const r = rand(42);
  const out = [];
  const today = new Date('2026-04-22');
  for (let i = days-1; i >= 0; i--) {
    const d = new Date(today); d.setDate(today.getDate() - i);
    const dow = d.getDay();
    const weekend = dow === 0 || dow === 6;
    if (weekend && r() > 0.3) { out.push({date:d, pnl:0, trades:0, wins:0, losses:0, weekend:true, empty:true}); continue; }
    const trades = Math.floor(r()*8) + (r()>0.15?1:0);
    if (trades === 0) { out.push({date:d, pnl:0, trades:0, wins:0, losses:0, empty:true}); continue; }
    const wins = Math.floor(r()*trades*0.75) + (trades>0?1:0);
    const losses = Math.max(0, trades - wins);
    const base = (wins - losses*0.7) * (80 + r()*180);
    const pnl = Math.round(base + (r()-0.5)*120);
    out.push({date:d, pnl, trades, wins, losses, weekend});
  }
  return out;
};

const HEATMAP_90 = genHeatmap(90);
const HEATMAP_YTD = genHeatmap(112);

// equity curve
const genEquity = () => {
  const r = rand(17);
  const pts = []; let v = 50000; let peak = v;
  for (let i = 0; i < 120; i++) {
    v += (r() - 0.42) * 480;
    peak = Math.max(peak, v);
    pts.push({ i, v, peak, dd: (v - peak) / peak });
  }
  return pts;
};
const EQUITY = genEquity();

// cell color ramp (heatmap)
const heatColor = (pnl, max) => {
  if (pnl === 0) return { bg:'rgba(255,255,255,0.03)', fg:'rgba(255,255,255,0.25)' };
  const n = Math.min(1, Math.abs(pnl)/max);
  if (pnl > 0) {
    // green ramp
    const a = 0.12 + n*0.75;
    return { bg:`rgba(57,255,20,${a})`, fg: n>0.5?'#000':'#39FF14', glow: n>0.7?`0 0 12px rgba(57,255,20,${n*0.5})`:'none' };
  } else {
    const a = 0.12 + n*0.75;
    return { bg:`rgba(255,61,87,${a})`, fg: n>0.5?'#fff':'#FF3D57' };
  }
};

// tabular num formatting
const fmtEur = (n, sign=true) => (sign && n>0?'+':'') + (n<0?'−':'') + '€' + Math.abs(n).toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2});
const fmtNum = (n, d=2, sign=false) => (sign && n>0?'+':'') + n.toFixed(d);
const fmtPct = (n, sign=true) => (sign && n>0?'+':'') + n.toFixed(2) + '%';

// shared small components
const Segment = ({ options, active, onChange, size='sm' }) => (
  <div style={{display:'inline-flex',background:'rgba(255,255,255,0.04)',border:'1px solid rgba(255,255,255,0.08)',borderRadius:6,padding:2,fontSize:size==='sm'?11:12}}>
    {options.map(o => (
      <button key={o} onClick={()=>onChange(o)} style={{
        background: active===o ? 'rgba(57,255,20,0.12)' : 'transparent',
        color: active===o ? '#39FF14' : 'rgba(255,255,255,0.55)',
        border:'none', padding: size==='sm'?'4px 10px':'6px 14px', borderRadius:4,
        fontFamily:'var(--mantis-font-mono)', fontWeight:600, letterSpacing:'0.03em',
        cursor:'pointer', fontSize:'inherit',
        boxShadow: active===o ? 'inset 0 0 0 1px rgba(57,255,20,0.25)' : 'none',
      }}>{o}</button>
    ))}
  </div>
);

const Label = ({ children, right }) => (
  <div style={{fontSize:10,letterSpacing:'.18em',textTransform:'uppercase',color:'rgba(255,255,255,0.45)',fontWeight:700,display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
    <span>{children}</span>{right}
  </div>
);

const MiniSpark = ({ data, color='#39FF14', h=24, w=80 }) => {
  const max = Math.max(...data), min = Math.min(...data);
  const path = data.map((v,i)=>`${i===0?'M':'L'} ${(i/(data.length-1))*w} ${h - ((v-min)/((max-min)||1))*h}`).join(' ');
  return <svg width={w} height={h} style={{display:'block'}}><path d={path} stroke={color} fill="none" strokeWidth="1.2"/></svg>;
};

Object.assign(window, { TIMEFRAMES, HEATMAP_90, HEATMAP_YTD, EQUITY, heatColor, fmtEur, fmtNum, fmtPct, Segment, Label, MiniSpark, rand });
