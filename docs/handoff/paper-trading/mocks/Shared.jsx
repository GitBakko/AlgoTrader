// Shared.jsx — building blocks condivisi tra Variant A e B per Paper Trading

// Mock data ispirato allo screenshot reale + arricchito con i campi richiesti
const PAPER_STATE = {
  status: 'RUNNING',         // RUNNING | IDLE | ERROR
  mode: 'DEMO',              // DEMO | LIVE
  market: 'OPEN',            // OPEN | CLOSED | PRE
  uptime: '4h 12m',
  lastTickAgo: 1.2,          // seconds
  iterations: 9,
  intervalSec: 900,
  signals: { total: 64, executed: 2, conversion: 3.7, rejected: 5, hold: 56 },
  errors: 0,
  pnlOpen: -6.00,            // unrealized
  pnlClosedToday: +12.40,
  openCount: 2,
  modelsLoaded: 21,
  modelsTotal: 21,
};

const RISK_STATE = {
  circuitBreakers: { status: 'OK', tripped: 0, total: 6 },
  equityFilter: { status: 'WARN', dd: 19.4, threshold: 20 },        // 19.4% DD vs 20% gate
  kelly: { status: 'ATTIVO', avg: 14, win: 60.4, pnl: -28.7 },
  tradingStops: { status: 'OK', count: 0 },
};

// 21 asset universe with last signal per asset
const ASSET_UNIVERSE = [
  { epic: 'XAUUSD', kind: 'metal',  color: '#FFD700' },
  { epic: 'BTCUSD', kind: 'crypto', color: '#F7931A' },
  { epic: 'US500',  kind: 'index',  color: '#5B7FFF' },
  { epic: 'WTIUSD', kind: 'energy', color: '#3D9970' },
  { epic: 'EURUSD', kind: 'forex',  color: '#0052B4' },
  { epic: 'TSLA',   kind: 'stock',  color: '#E31937' },
  { epic: 'DE40',   kind: 'index',  color: '#FFCE00' },
  { epic: 'NVDA',   kind: 'stock',  color: '#76B900' },
  { epic: 'SOLUSD', kind: 'crypto', color: '#9945FF' },
  { epic: 'ETHUSD', kind: 'crypto', color: '#627EEA' },
  { epic: 'BNBUSD', kind: 'crypto', color: '#F0B90B' },
  { epic: 'DOGUSD', kind: 'crypto', color: '#C2A633' },
  { epic: 'NATGAS', kind: 'energy', color: '#A0522D' },
  { epic: 'COPPER', kind: 'metal',  color: '#B87333' },
  { epic: 'PLATINUM', kind: 'metal', color: '#E5E4E2' },
  { epic: 'GBPUSD', kind: 'forex',  color: '#012169' },
  { epic: 'USDJPY', kind: 'forex',  color: '#BC002D' },
  { epic: 'XAGUSD', kind: 'metal',  color: '#C0C0C0' },
  { epic: 'NAS100', kind: 'index',  color: '#5B9BD5' },
  { epic: 'DASHUSD', kind: 'crypto', color: '#008CE7' },
  { epic: 'ICPUSD', kind: 'crypto', color: '#29ABE2' },
];

// Per-asset last signal (matches screenshot direction/state distribution)
const LAST_SIGNALS = {
  XAUUSD:  { dir:'HOLD',     conf: 0,  state:'hold',     time:'06:24' },
  BTCUSD:  { dir:'SELL',     conf:55,  state:'rejected', time:'06:24' },
  US500:   { dir:'SELL',     conf:60,  state:'rejected', time:'06:24' },
  WTIUSD:  { dir:'HOLD',     conf: 0,  state:'hold',     time:'06:24' },
  EURUSD:  { dir:'HOLD',     conf: 0,  state:'hold',     time:'06:24' },
  TSLA:    { dir:'HOLD',     conf:36,  state:'closed',   time:'10:18' },
  DE40:    { dir:'HOLD',     conf: 0,  state:'hold',     time:'06:24' },
  NVDA:    { dir:'SELL',     conf:64,  state:'executed', time:'06:24' },
  SOLUSD:  { dir:'HOLD',     conf:51,  state:'hold',     time:'06:24' },
  ETHUSD:  { dir:'HOLD',     conf:46,  state:'hold',     time:'06:24' },
  BNBUSD:  { dir:'HOLD',     conf:35,  state:'hold',     time:'06:24' },
  DOGUSD:  { dir:'HOLD',     conf:41,  state:'hold',     time:'06:24' },
  NATGAS:  { dir:'HOLD',     conf: 8,  state:'hold',     time:'06:24' },
  COPPER:  { dir:'HOLD',     conf: 8,  state:'hold',     time:'06:24' },
  PLATINUM:{ dir:'HOLD',     conf: 2,  state:'hold',     time:'06:24' },
  GBPUSD:  { dir:'HOLD',     conf: 0,  state:'hold',     time:'06:24' },
  USDJPY:  { dir:'SELL',     conf:62,  state:'executed', time:'06:24' },
  XAGUSD:  { dir:'HOLD',     conf:18,  state:'hold',     time:'06:24' },
  NAS100:  { dir:'HOLD',     conf:11,  state:'hold',     time:'06:24' },
  DASHUSD: { dir:'HOLD',     conf:24,  state:'hold',     time:'06:24' },
  ICPUSD:  { dir:'HOLD',     conf:33,  state:'hold',     time:'06:24' },
};

// Open positions enriched with all required fields
// 1. entry, 2. SL (€ + %), 3. TP (€ + %), 4. trend, 5. age, 6. trailing, 7. current (€ + %)
const OPEN_POSITIONS = [
  {
    epic: 'USDJPY', dir:'SELL', size: 100000,
    entry: 159.286, current: 159.348,
    sl: 159.85,  tp: 158.20,
    sl_eur: -353.20, sl_pct: -1.83,
    tp_eur: +685.00, tp_pct: +3.55,
    cur_eur: -6.61,  cur_pct: -0.034,
    age_min: 27,
    trailing: false,
    trend: [159.20,159.22,159.18,159.25,159.28,159.30,159.32,159.28,159.34,159.36,159.40,159.348],
    trendDir: 'down', // direction we're betting
    confidence: 62,
  },
  {
    epic: 'NVDA', dir:'SELL', size: 22.2900,
    entry: 207.08, current: 207.35,
    sl: 212.50,  tp: 195.00,
    sl_eur: -120.85, sl_pct: -2.62,
    tp_eur: +269.13, tp_pct: +5.83,
    cur_eur: -5.99,  cur_pct: -0.130,
    age_min: 142,
    trailing: true,
    trend: [206.40,206.80,207.20,207.50,207.10,206.90,207.00,207.20,207.40,207.60,207.40,207.35],
    trendDir: 'down',
    confidence: 64,
  },
];

// Recent signals feed (last 11 events)
const FEED = [
  { time:'06:24', epic:'GBPUSD',  strategy:'mean_reversion', dir:'SELL', conf:67, price:1.36460, state:'rejected', detail:'Total exposure 231.5% > limit 80%' },
  { time:'06:24', epic:'PLATINUM',strategy:'mean_reversion', dir:'HOLD', conf: 8, price:2828.60, state:'hold',    detail:'HOLD' },
  { time:'06:24', epic:'COPPER',  strategy:'mean_reversion', dir:'HOLD', conf: 8, price:6.13609, state:'hold',    detail:'HOLD' },
  { time:'06:24', epic:'NATGAS',  strategy:'mean_reversion', dir:'HOLD', conf: 8, price:2.799,   state:'hold',    detail:'HOLD' },
  { time:'06:24', epic:'ICPUSD',  strategy:'mean_reversion', dir:'HOLD', conf: 0, price:2.0071,  state:'hold',    detail:'HOLD' },
  { time:'06:24', epic:'DOGUSD',  strategy:'mean_reversion', dir:'HOLD', conf:41, price:0.106228,state:'hold',    detail:'HOLD' },
  { time:'06:24', epic:'BNBUSD',  strategy:'mean_reversion', dir:'HOLD', conf: 0, price:638.3,   state:'hold',    detail:'HOLD' },
  { time:'06:24', epic:'ETHUSD',  strategy:'mean_reversion', dir:'HOLD', conf:46, price:2393.4,  state:'hold',    detail:'HOLD' },
  { time:'06:24', epic:'SOLUSD',  strategy:'mean_reversion', dir:'HOLD', conf:51, price:87.76,   state:'hold',    detail:'HOLD' },
  { time:'06:24', epic:'DE40',    strategy:'mean_reversion', dir:'HOLD', conf: 0, price:24311.3, state:'hold',    detail:'HOLD' },
  { time:'06:24', epic:'EURUSD',  strategy:'mean_reversion', dir:'HOLD', conf: 0, price:1.17293, state:'hold',    detail:'HOLD' },
];

// Color helpers ─────────────────────────────────────────────
const stateColor = (s) => ({
  executed:  '#39FF14',
  hold:      '#8B949E',
  rejected:  '#FF3D57',
  closed:    '#00E5FF',
  exec_failed:'#FF3D57',
}[s] || '#8B949E');

const dirColor = (d) => d === 'BUY' ? '#39FF14' : d === 'SELL' ? '#FF3D57' : '#8B949E';

const fmtEur = (n, dp=2) => `${n>0?'+':n<0?'−':''}€${Math.abs(n).toLocaleString('it-IT',{minimumFractionDigits:dp,maximumFractionDigits:dp})}`;
const fmtPct = (n, dp=2) => `${n>0?'+':n<0?'−':''}${Math.abs(n).toFixed(dp)}%`;
const fmtAge = (m) => m < 60 ? `${m}m` : `${Math.floor(m/60)}h ${m%60}m`;

// ─────────────────────────────────────────────────────────────
// Generic primitives
// ─────────────────────────────────────────────────────────────

function Label({ children, right }) {
  return <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',gap:8}}>
    <span style={{fontSize:9,fontWeight:700,letterSpacing:'0.18em',textTransform:'uppercase',color:'rgba(255,255,255,0.4)',fontFamily:'var(--mantis-font-mono)'}}>{children}</span>
    {right}
  </div>;
}

function PulseDot({ color='#39FF14', size=7 }) {
  return <span style={{
    display:'inline-block', width:size, height:size, borderRadius:'50%',
    background: color, boxShadow:`0 0 0 0 ${color}`,
    animation:'pulseGlow 2s ease-out infinite',
  }}/>;
}

function StatusPill({ status }) {
  const cfg = {
    RUNNING: {c:'#39FF14', bg:'rgba(57,255,20,0.12)', glow:true,  pulse:true},
    IDLE:    {c:'#8B949E', bg:'rgba(139,148,158,0.12)', glow:false, pulse:false},
    ERROR:   {c:'#FF3D57', bg:'rgba(255,61,87,0.12)', glow:true, pulse:true},
  }[status];
  return <span style={{
    display:'inline-flex',alignItems:'center',gap:6,padding:'4px 10px 4px 8px',
    borderRadius:100, background:cfg.bg, border:`1px solid ${cfg.c}33`,
    color:cfg.c, fontFamily:'var(--mantis-font-mono)', fontSize:10, fontWeight:700,
    letterSpacing:'0.08em', boxShadow: cfg.glow?`0 0 12px ${cfg.c}55`:'none',
  }}>
    {cfg.pulse && <PulseDot color={cfg.c} size={6}/>}
    {status}
  </span>;
}

function Chip({ label, value, color='rgba(255,255,255,0.7)', bg='rgba(255,255,255,0.04)', border='rgba(255,255,255,0.08)' }) {
  return <span style={{
    display:'inline-flex',alignItems:'center',gap:6,padding:'3px 8px',borderRadius:4,
    background:bg, border:`1px solid ${border}`,
    fontFamily:'var(--mantis-font-mono)', fontSize:10, color,
  }}>
    {label && <span style={{opacity:0.55,letterSpacing:'0.08em',textTransform:'uppercase',fontSize:9,fontWeight:700}}>{label}</span>}
    <span style={{fontWeight:700}}>{value}</span>
  </span>;
}

function Sparkline({ data, w=80, h=24, color='#39FF14', fill=true }) {
  if (!data || data.length<2) return <svg width={w} height={h}/>;
  const min = Math.min(...data), max = Math.max(...data);
  const span = max-min || 1;
  const pts = data.map((v,i) => `${(i/(data.length-1))*w},${h - ((v-min)/span)*(h-2) - 1}`).join(' ');
  const areaPts = `0,${h} ${pts} ${w},${h}`;
  return <svg width={w} height={h} style={{display:'block'}}>
    {fill && <polyline points={areaPts} fill={color} fillOpacity="0.12" stroke="none"/>}
    <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4" strokeLinejoin="round"/>
    <circle cx={w} cy={h - ((data[data.length-1]-min)/span)*(h-2) - 1} r="2" fill={color}/>
  </svg>;
}

// Mini bar showing position progress between SL ←→ Entry ←→ TP, with current marker
function PositionRange({ entry, current, sl, tp, dir, w=180 }) {
  // For SELL: tp < entry < sl (price goes down for profit)
  // For BUY:  sl < entry < tp
  const lo = Math.min(sl, tp, entry, current);
  const hi = Math.max(sl, tp, entry, current);
  const span = hi - lo || 1;
  const x = (v) => ((v - lo) / span) * w;
  const inProfit = dir === 'SELL' ? current < entry : current > entry;
  const slX = x(sl), tpX = x(tp), entryX = x(entry), curX = x(current);
  const fillStart = Math.min(entryX, curX), fillEnd = Math.max(entryX, curX);
  return <svg width={w} height={20} style={{display:'block'}}>
    {/* base line */}
    <line x1="0" y1="10" x2={w} y2="10" stroke="rgba(255,255,255,0.12)" strokeWidth="2"/>
    {/* SL→TP gradient hint */}
    <line x1={Math.min(slX,tpX)} y1="10" x2={Math.max(slX,tpX)} y2="10" stroke="rgba(255,255,255,0.06)" strokeWidth="2"/>
    {/* travelled distance entry→current */}
    <line x1={fillStart} y1="10" x2={fillEnd} y2="10" stroke={inProfit?'#39FF14':'#FF3D57'} strokeWidth="3"
      style={{filter:`drop-shadow(0 0 4px ${inProfit?'rgba(57,255,20,0.6)':'rgba(255,61,87,0.6)'})`}}/>
    {/* SL marker */}
    <line x1={slX} y1="2" x2={slX} y2="18" stroke="#FF3D57" strokeWidth="1.5"/>
    <text x={slX} y="2" fill="#FF3D57" fontSize="7" fontFamily="var(--mantis-font-mono)" textAnchor="middle" dy="-1">SL</text>
    {/* TP marker */}
    <line x1={tpX} y1="2" x2={tpX} y2="18" stroke="#39FF14" strokeWidth="1.5"/>
    <text x={tpX} y="2" fill="#39FF14" fontSize="7" fontFamily="var(--mantis-font-mono)" textAnchor="middle" dy="-1">TP</text>
    {/* Entry marker */}
    <circle cx={entryX} cy="10" r="3" fill="#fff" stroke="rgba(0,0,0,0.4)" strokeWidth="1"/>
    {/* Current marker */}
    <circle cx={curX} cy="10" r="4" fill={inProfit?'#39FF14':'#FF3D57'} stroke="#0d1117" strokeWidth="1.5"
      style={{filter:`drop-shadow(0 0 6px ${inProfit?'rgba(57,255,20,0.8)':'rgba(255,61,87,0.8)'})`}}/>
  </svg>;
}

// Asset glyph circle
function AssetGlyph({ epic, size=22 }) {
  const a = ASSET_UNIVERSE.find(x=>x.epic===epic) || {color:'#8B949E'};
  const initials = epic.slice(0,2);
  return <span style={{
    display:'inline-flex',alignItems:'center',justifyContent:'center',
    width:size, height:size, borderRadius:'50%',
    background:`linear-gradient(135deg, ${a.color}33, ${a.color}11)`,
    border:`1px solid ${a.color}66`,
    fontSize: size*0.4, fontWeight:700, color: a.color,
    fontFamily:'var(--mantis-font-mono)', letterSpacing:'-0.04em',
    flexShrink:0,
  }}>{initials}</span>;
}

Object.assign(window, {
  PAPER_STATE, RISK_STATE, ASSET_UNIVERSE, LAST_SIGNALS, OPEN_POSITIONS, FEED,
  stateColor, dirColor, fmtEur, fmtPct, fmtAge,
  Label, PulseDot, StatusPill, Chip, Sparkline, PositionRange, AssetGlyph,
});
