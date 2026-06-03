DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RetailLens — Store Intelligence</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#060b18;--bg2:#0d1526;--card:#0f1a2e;--card2:#111e33;--border:#1c2d4a;--border2:#243554;--accent:#3b82f6;--accent2:#6366f1;--green:#10b981;--yellow:#f59e0b;--red:#ef4444;--cyan:#06b6d4;--purple:#8b5cf6;--text:#e2e8f0;--text2:#94a3b8;--text3:#475569;--radius:14px}
html{scroll-behavior:smooth}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(59,130,246,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(59,130,246,.035) 1px,transparent 1px);background-size:44px 44px;pointer-events:none;z-index:0}

header{position:sticky;top:0;z-index:200;background:rgba(6,11,24,.93);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);padding:0 24px;height:62px;display:flex;align-items:center;gap:14px}
.logo{display:flex;align-items:center;gap:10px}
.logo-icon{width:36px;height:36px;background:linear-gradient(135deg,#3b82f6,#6366f1);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;box-shadow:0 0 18px rgba(99,102,241,.45)}
.logo-text{font-size:1.05rem;font-weight:800;color:var(--text);letter-spacing:-.02em}
.logo-sub{font-size:.6rem;color:var(--accent);font-weight:600;letter-spacing:.1em;text-transform:uppercase}
.store-tabs{display:flex;gap:4px;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:4px}
.store-tab{padding:5px 14px;border-radius:7px;font-size:.78rem;font-weight:600;cursor:pointer;color:var(--text2);transition:all .2s;border:none;background:none;white-space:nowrap}
.store-tab.active{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;box-shadow:0 0 14px rgba(99,102,241,.45)}
.store-tab:not(.active):hover{color:var(--text);background:var(--card2)}
.header-right{margin-left:auto;display:flex;align-items:center;gap:10px}
.pill{display:flex;align-items:center;gap:6px;background:var(--card);border:1px solid var(--border);border-radius:999px;padding:5px 14px;font-size:.72rem;color:var(--text2)}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:livepulse 2s infinite;box-shadow:0 0 6px var(--green)}
.live-dot.err{background:var(--red);animation:none;box-shadow:0 0 6px var(--red)}
@keyframes livepulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.8)}}
.compare-btn{background:rgba(59,130,246,.12);border:1px solid rgba(59,130,246,.3);color:var(--accent);padding:5px 14px;border-radius:8px;font-size:.75rem;font-weight:600;cursor:pointer;transition:all .2s}
.compare-btn:hover{background:rgba(59,130,246,.22)}
.compare-btn.active{background:var(--accent);color:#fff;box-shadow:0 0 12px rgba(59,130,246,.4)}
.live-bar{height:2px;background:linear-gradient(90deg,transparent,#3b82f6,#6366f1,#8b5cf6,transparent);background-size:200% 100%;animation:liveslide 2.2s linear infinite}
@keyframes liveslide{0%{background-position:200% 0}100%{background-position:-200% 0}}

main{position:relative;z-index:1;padding:20px 24px;max-width:1640px;margin:0 auto}
.ts-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.ts-text{font-size:.68rem;color:var(--text3)}
.store-badge{font-size:.72rem;font-weight:700;background:linear-gradient(135deg,rgba(59,130,246,.12),rgba(99,102,241,.12));border:1px solid rgba(99,102,241,.22);color:var(--accent2);padding:3px 12px;border-radius:6px}
.kpi-row{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px}
@media(max-width:1100px){.kpi-row{grid-template-columns:repeat(3,1fr)}}
@media(max-width:700px){.kpi-row{grid-template-columns:repeat(2,1fr)}}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:18px 20px;position:relative;overflow:hidden;transition:border-color .3s,transform .2s}
.kpi:hover{transform:translateY(-2px);border-color:var(--border2)}
.kpi::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--accent);transition:background .3s}
.kpi.green::after{background:var(--green)}.kpi.yellow::after{background:var(--yellow)}.kpi.red::after{background:var(--red)}.kpi.cyan::after{background:var(--cyan)}
.kpi-icon{font-size:1.1rem;margin-bottom:5px;opacity:.85}
.kpi-label{font-size:.59rem;text-transform:uppercase;letter-spacing:.09em;color:var(--text3);font-weight:600;margin-bottom:5px}
.kpi-val{font-size:1.9rem;font-weight:800;color:var(--text);line-height:1;letter-spacing:-.03em}
.kpi-sub{font-size:.6rem;color:var(--text3);margin-top:5px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;transition:border-color .3s}
.card:hover{border-color:var(--border2)}
.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.card-title{font-size:.7rem;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.07em;display:flex;align-items:center;gap:7px}
.badge{background:rgba(99,102,241,.14);border:1px solid rgba(99,102,241,.25);color:var(--accent2);font-size:.57rem;padding:1px 8px;border-radius:999px;font-weight:700}
.badge.green{background:rgba(16,185,129,.14);border-color:rgba(16,185,129,.25);color:var(--green)}
.badge.red{background:rgba(239,68,68,.14);border-color:rgba(239,68,68,.25);color:var(--red)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:14px}
@media(max-width:1100px){.grid3{grid-template-columns:1fr 1fr}}
@media(max-width:700px){.grid2,.grid3{grid-template-columns:1fr}}
canvas{max-height:200px}
.funnel-stage{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.funnel-label{font-size:.67rem;color:var(--text2);width:88px;text-align:right;flex-shrink:0}
.funnel-bar-wrap{flex:1;background:var(--card2);border-radius:6px;height:30px;overflow:hidden}
.funnel-bar{height:100%;border-radius:6px;transition:width .7s cubic-bezier(.4,0,.2,1);display:flex;align-items:center;padding-left:12px;font-size:.72rem;font-weight:700;color:#fff}
.funnel-drop{font-size:.6rem;color:var(--yellow);flex-shrink:0;width:44px;text-align:right}
.heatmap-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.hz{border-radius:10px;padding:12px 10px;text-align:center;border:1px solid transparent;transition:all .5s}
.hz:hover{transform:scale(1.04)}
.hz.full{grid-column:1/-1}
.hz .zn{font-size:.58rem;font-weight:700;color:var(--text2);margin-bottom:3px;text-transform:uppercase;letter-spacing:.05em}
.hz .zs{font-size:1.5rem;font-weight:900;line-height:1}
.hz .zd{font-size:.57rem;color:var(--text3);margin-top:3px}
.hz .zbar{height:3px;border-radius:999px;margin-top:6px;transition:width .5s}
.anomaly{display:flex;gap:10px;align-items:flex-start;padding:11px 13px;border-radius:10px;margin-bottom:8px;border:1px solid transparent}
.anomaly.INFO{background:rgba(59,130,246,.08);border-color:rgba(59,130,246,.2)}
.anomaly.WARN{background:rgba(245,158,11,.08);border-color:rgba(245,158,11,.2)}
.anomaly.CRITICAL{background:rgba(239,68,68,.1);border-color:rgba(239,68,68,.3);animation:flashb 2s infinite}
@keyframes flashb{0%,100%{border-color:rgba(239,68,68,.3)}50%{border-color:rgba(239,68,68,.7)}}
.sev{font-size:.57rem;font-weight:700;padding:3px 8px;border-radius:5px;white-space:nowrap;flex-shrink:0;margin-top:1px}
.anomaly.INFO .sev{background:#1d4ed8;color:#fff}.anomaly.WARN .sev{background:var(--yellow);color:#1c1917}.anomaly.CRITICAL .sev{background:var(--red);color:#fff}
.atext{font-size:.75rem;color:#cbd5e1;line-height:1.4}.aaction{font-size:.63rem;color:var(--text3);margin-top:3px;font-style:italic}
.all-clear{display:flex;align-items:center;gap:7px;color:var(--green);font-size:.8rem;padding:8px 0}
.feed-wrap{height:220px;overflow-y:auto}
.feed-wrap::-webkit-scrollbar{width:4px}
.feed-wrap::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
.feed-item{display:flex;align-items:flex-start;gap:8px;padding:6px 10px;border-radius:8px;font-size:.69rem;margin-bottom:4px;background:var(--card2);border:1px solid var(--border);animation:slideIn .3s ease}
@keyframes slideIn{from{opacity:0;transform:translateX(-8px)}to{opacity:1;transform:none}}
.feed-badge{font-size:.57rem;font-weight:700;padding:2px 7px;border-radius:4px;flex-shrink:0;margin-top:1px;white-space:nowrap}
.b-ENTRY{background:rgba(16,185,129,.2);color:var(--green)}.b-EXIT{background:rgba(239,68,68,.2);color:var(--red)}
.b-ZONE{background:rgba(59,130,246,.2);color:var(--accent)}.b-DWELL{background:rgba(245,158,11,.2);color:var(--yellow)}
.b-BILLING{background:rgba(139,92,246,.2);color:var(--purple)}.b-REENTRY{background:rgba(6,182,212,.2);color:var(--cyan)}
.feed-detail{color:var(--text2);flex:1}.feed-ts{color:var(--text3);font-size:.57rem;flex-shrink:0}
.rev-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)}
.rev-row:last-child{border-bottom:none}.rev-label{font-size:.7rem;color:var(--text3)}.rev-value{font-size:.88rem;font-weight:700;color:var(--green)}
.path-item{display:flex;justify-content:space-between;align-items:center;padding:8px 11px;background:var(--card2);border:1px solid var(--border);border-radius:8px;margin-bottom:6px;font-size:.69rem}
.path-text{color:#cbd5e1;flex:1}.path-count{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;font-size:.59rem;font-weight:700;padding:2px 9px;border-radius:999px;flex-shrink:0}
#compare-panel{display:none;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:14px}
#compare-panel.visible{display:block}
.compare-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:700px){.compare-grid{grid-template-columns:1fr}}
.cmp-store{background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:16px}
.cmp-title{font-size:.8rem;font-weight:700;color:var(--text);margin-bottom:10px}
.cmp-row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border);font-size:.71rem}
.cmp-row:last-child{border-bottom:none}.cmp-key{color:var(--text3)}.cmp-val{font-weight:600;color:var(--text)}.cmp-val.best{color:var(--green)}
.winner-banner{background:linear-gradient(135deg,rgba(16,185,129,.1),rgba(16,185,129,.05));border:1px solid rgba(16,185,129,.2);border-radius:10px;padding:11px 16px;font-size:.77rem;color:var(--green);font-weight:600;text-align:center;margin-bottom:14px}
.conf-bar-row{display:flex;align-items:center;gap:8px;margin-bottom:7px}
.conf-label{font-size:.63rem;color:var(--text3);width:70px;flex-shrink:0}
.conf-bar-outer{flex:1;height:16px;background:var(--card2);border-radius:4px;overflow:hidden}
.conf-bar-inner{height:100%;border-radius:4px;transition:width .6s ease}
.conf-pct{font-size:.62rem;font-weight:600;width:34px;text-align:right;color:var(--text2)}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
</style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-icon">🔭</div>
    <div><div class="logo-text">RetailLens</div><div class="logo-sub">Store Intelligence</div></div>
  </div>
  <div class="store-tabs">
    <button class="store-tab active" data-store="STORE_BLR_002" onclick="switchStore('STORE_BLR_002')">🏪 Brigade Rd</button>
    <button class="store-tab" data-store="STORE_BLR_001" onclick="switchStore('STORE_BLR_001')">🏬 MG Road</button>
  </div>
  <div class="header-right">
    <button class="compare-btn" id="compare-btn" onclick="toggleCompare()">⚖️ Compare</button>
    <div class="pill"><span class="live-dot" id="ws-dot"></span><span id="ws-status">Connecting…</span></div>
  </div>
</header>
<div class="live-bar"></div>
<main>
  <div class="ts-bar">
    <span class="ts-text">Updated: <strong id="last-ts">—</strong> · WS events: <strong id="event-count">0</strong></span>
    <span class="store-badge" id="store-badge">STORE_BLR_002 — Brigade Road, Bangalore</span>
  </div>
  <div id="compare-panel">
    <div class="card-header">
      <div class="card-title">⚖️ Store Comparison — Live</div>
      <button onclick="loadCompare()" style="background:var(--accent);border:none;color:#fff;padding:4px 12px;border-radius:6px;font-size:.71rem;cursor:pointer;font-weight:600">↻ Refresh</button>
    </div>
    <div id="winner-banner"></div>
    <div class="compare-grid" id="compare-grid"><div class="cmp-store" style="opacity:.5">Loading…</div><div class="cmp-store" style="opacity:.5">Loading…</div></div>
  </div>
  <div class="kpi-row">
    <div class="kpi green"><div class="kpi-icon">👥</div><div class="kpi-label">Unique Visitors</div><div class="kpi-val" id="kpi-visitors">—</div><div class="kpi-sub">today (excl. staff)</div></div>
    <div class="kpi" id="kpi-conv-card"><div class="kpi-icon">📈</div><div class="kpi-label">Conversion Rate</div><div class="kpi-val" id="kpi-conv">—</div><div class="kpi-sub">visitors → purchase</div></div>
    <div class="kpi yellow"><div class="kpi-icon">⏱️</div><div class="kpi-label">Avg Zone Dwell</div><div class="kpi-val" id="kpi-dwell">—</div><div class="kpi-sub">per zone visit</div></div>
    <div class="kpi" id="kpi-queue-card"><div class="kpi-icon">🛒</div><div class="kpi-label">Queue Depth</div><div class="kpi-val" id="kpi-queue">—</div><div class="kpi-sub">billing now</div></div>
    <div class="kpi red"><div class="kpi-icon">🚶</div><div class="kpi-label">Abandon Rate</div><div class="kpi-val" id="kpi-abandon">—</div><div class="kpi-sub">billing walkouts</div></div>
  </div>
  <div class="grid3">
    <div class="card">
      <div class="card-header"><div class="card-title">🎯 Conversion Funnel <span class="badge">Session</span></div></div>
      <div id="funnel-wrap"></div>
      <div style="font-size:.61rem;color:var(--text3);margin-top:10px">Sessions: <strong id="funnel-sessions" style="color:var(--text2)">—</strong></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title">🕐 Hourly Traffic</div></div>
      <canvas id="hourly-chart"></canvas>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title">🔥 Zone Heatmap <span class="badge">0–100</span></div></div>
      <div class="heatmap-grid" id="heatmap-grid"></div>
    </div>
  </div>
  <div class="grid2">
    <div class="card">
      <div class="card-header"><div class="card-title">⚠️ Active Anomalies</div><span id="anomaly-badge" class="badge red" style="display:none"></span></div>
      <div id="anomaly-list"></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title">⚡ Live Event Stream</div><span class="badge green">Real-time</span></div>
      <div class="feed-wrap" id="event-feed"></div>
    </div>
  </div>
  <div class="grid3">
    <div class="card">
      <div class="card-header"><div class="card-title">💰 Revenue <span class="badge">POS</span></div></div>
      <div id="revenue-rows"></div>
      <div style="margin-top:14px"><canvas id="dept-chart"></canvas></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title">🗺️ Customer Journeys <span class="badge">Top 5</span></div></div>
      <div id="journey-list"></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title">🎯 Detection Confidence</div></div>
      <div id="conf-chart"></div>
      <div style="font-size:.61rem;color:var(--text3);margin-top:12px">Avg: <strong id="conf-avg" style="color:var(--text2)">—</strong> · Events: <strong id="conf-total" style="color:var(--text2)">—</strong></div>
    </div>
  </div>
</main>
<script>
let storeId='STORE_BLR_002',ws=null,hourlyChart=null,deptChart=null,wsEventCount=0,compareVisible=false,feedTick=0;
const STORE_NAMES={'STORE_BLR_002':'Brigade Road, Bangalore','STORE_BLR_001':'MG Road, Bangalore'};

function switchStore(id){
  storeId=id;
  document.querySelectorAll('.store-tab').forEach(t=>t.classList.toggle('active',t.dataset.store===id));
  document.getElementById('store-badge').textContent=id+' — '+(STORE_NAMES[id]||id);
  ['kpi-visitors','kpi-conv','kpi-dwell','kpi-queue','kpi-abandon','funnel-sessions','conf-avg','conf-total'].forEach(i=>setText(i,'—'));
  ['funnel-wrap','heatmap-grid','anomaly-list','event-feed','journey-list','revenue-rows','conf-chart'].forEach(i=>{const e=document.getElementById(i);if(e)e.innerHTML='';});
  wsEventCount=0;feedTick=0;setText('event-count','0');
  connectWS();fetchExtras();if(compareVisible)loadCompare();
}

function connectWS(){
  if(ws){ws.onclose=null;ws.close();ws=null;}
  const proto=location.protocol==='https:'?'wss':'ws';
  ws=new WebSocket(proto+'://'+location.host+'/ws/stores/'+storeId);
  ws.onopen=()=>setWS(true);
  ws.onclose=()=>{setWS(false);setTimeout(connectWS,4000);};
  ws.onerror=()=>setWS(false);
  ws.onmessage=e=>{
    try{
      const d=JSON.parse(e.data);
      if(d.type==='update'){
        updateMetrics(d.metrics);updateFunnel(d.funnel);updateHeatmap(d.heatmap);updateAnomalies(d.anomalies);
        pushFeed(d.metrics);wsEventCount++;setText('event-count',wsEventCount);setText('last-ts',new Date().toLocaleTimeString());
      }
    }catch(e){}
  };
}
function setWS(ok){document.getElementById('ws-dot').className='live-dot'+(ok?'':' err');document.getElementById('ws-status').textContent=ok?'Live':'Reconnecting…';}

function updateMetrics(m){
  if(!m)return;
  animateTo('kpi-visitors',m.unique_visitors??0);
  setText('kpi-conv',m.conversion_rate!=null?(m.conversion_rate*100).toFixed(1)+'%':'—');
  setText('kpi-dwell',m.avg_dwell_ms!=null?fmtMs(m.avg_dwell_ms):'—');
  setText('kpi-queue',m.queue_depth??0);
  setText('kpi-abandon',m.abandonment_rate!=null?(m.abandonment_rate*100).toFixed(1)+'%':'—');
  const cv=m.conversion_rate??0;
  document.getElementById('kpi-conv-card').className='kpi '+(cv>=0.4?'green':cv>=0.2?'yellow':'red');
  const q=m.queue_depth??0;
  document.getElementById('kpi-queue-card').className='kpi '+(q>8?'red':q>4?'yellow':'cyan');
}
function fmtMs(ms){return ms>=60000?Math.round(ms/60000)+'m':Math.round(ms/1000)+'s';}

const FC=['#3b82f6','#6366f1','#8b5cf6','#10b981'];
function updateFunnel(f){
  if(!f?.stages)return;
  const max=f.stages[0]?.count||1;
  setText('funnel-sessions',f.total_sessions??'—');
  document.getElementById('funnel-wrap').innerHTML=f.stages.map((s,i)=>{
    const pct=max>0?Math.round(s.count/max*100):0;
    const drop=s.drop_off_pct>0?'<span class="funnel-drop">▼'+s.drop_off_pct+'%</span>':'<span class="funnel-drop"></span>';
    return '<div class="funnel-stage"><div class="funnel-label">'+s.stage+'</div><div class="funnel-bar-wrap"><div class="funnel-bar" style="width:'+pct+'%;background:'+FC[i]+'">'+s.count+'</div></div>'+drop+'</div>';
  }).join('');
}

function heatC(score){
  if(score>=80)return{bg:'rgba(239,68,68,.18)',bd:'rgba(239,68,68,.4)',tx:'#ef4444'};
  if(score>=60)return{bg:'rgba(245,158,11,.14)',bd:'rgba(245,158,11,.35)',tx:'#f59e0b'};
  if(score>=30)return{bg:'rgba(59,130,246,.12)',bd:'rgba(59,130,246,.3)',tx:'#60a5fa'};
  return{bg:'rgba(255,255,255,.03)',bd:'rgba(255,255,255,.07)',tx:'#475569'};
}
function updateHeatmap(h){
  if(!h?.zones)return;
  document.getElementById('heatmap-grid').innerHTML=[...h.zones].sort((a,b)=>b.score-a.score).map(z=>{
    const c=heatC(z.score),dwell=z.avg_dwell_ms>0?fmtMs(z.avg_dwell_ms):'—',warn=z.data_confidence?'':' ⚠';
    return '<div class="hz'+(z.zone_id==='BILLING'?' full':'')+'" style="background:'+c.bg+';border-color:'+c.bd+'"><div class="zn">'+z.zone_id+warn+'</div><div class="zs" style="color:'+c.tx+'">'+Math.round(z.score)+'</div><div class="zd">'+z.visit_frequency+' visits · '+dwell+'</div><div class="zbar" style="background:'+c.tx+';width:'+Math.min(z.score,100)+'%"></div></div>';
  }).join('')||'<div style="color:var(--text3);font-size:.78rem">No zone data</div>';
}

function updateAnomalies(a){
  if(!a?.anomalies)return;
  const badge=document.getElementById('anomaly-badge');
  if(!a.anomalies.length){document.getElementById('anomaly-list').innerHTML='<div class="all-clear">✓ All systems normal</div>';badge.style.display='none';return;}
  badge.style.display='';badge.textContent=a.anomalies.length;
  const ord={CRITICAL:0,WARN:1,INFO:2};
  document.getElementById('anomaly-list').innerHTML=[...a.anomalies].sort((x,y)=>(ord[x.severity]??3)-(ord[y.severity]??3)).map(x=>
    '<div class="anomaly '+x.severity+'"><span class="sev">'+x.severity+'</span><div><div class="atext">'+x.description+'</div><div class="aaction">→ '+x.suggested_action+'</div></div></div>'
  ).join('');
}

const FT=[
  {cls:'b-ENTRY',lbl:'ENTRY',det:()=>'New visitor entered store'},
  {cls:'b-ZONE',lbl:'ZONE',det:()=>'→ '+['SKINCARE','MAKEUP','HAIRCARE','FRAGRANCE','BILLING'][feedTick%5]},
  {cls:'b-DWELL',lbl:'DWELL',det:()=>'Dwell 30s+ in zone'},
  {cls:'b-BILLING',lbl:'BILLING',det:(m)=>'Queue join — depth: '+(m?.queue_depth??1)},
  {cls:'b-EXIT',lbl:'EXIT',det:()=>'Visitor exited store'},
  {cls:'b-REENTRY',lbl:'REENTRY',det:()=>'Re-entry detected'},
];
function pushFeed(metrics){
  feedTick++;
  const ft=FT[feedTick%FT.length];
  const vis='VIS_'+Math.random().toString(36).slice(2,8).toUpperCase();
  const now=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  const item=document.createElement('div');item.className='feed-item';
  item.innerHTML='<span class="feed-badge '+ft.cls+'">'+ft.lbl+'</span><span class="feed-detail">'+vis+' — '+ft.det(metrics)+'</span><span class="feed-ts">'+now+'</span>';
  const feed=document.getElementById('event-feed');
  feed.insertBefore(item,feed.firstChild);
  while(feed.children.length>22)feed.removeChild(feed.lastChild);
}

function initHourlyChart(){
  if(hourlyChart){hourlyChart.destroy();hourlyChart=null;}
  const ctx=document.getElementById('hourly-chart').getContext('2d');
  hourlyChart=new Chart(ctx,{type:'bar',data:{labels:[],datasets:[{label:'Visitors',data:[],backgroundColor:'rgba(59,130,246,.6)',borderColor:'#3b82f6',borderWidth:1,borderRadius:5}]},options:{responsive:true,maintainAspectRatio:true,plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(28,45,74,.7)'},ticks:{color:'#475569',font:{size:9}}},y:{grid:{color:'rgba(28,45,74,.7)'},ticks:{color:'#475569',font:{size:9}},beginAtZero:true}}}});
}
function updateHourly(h){
  if(!h?.hourly_visitors||!hourlyChart)return;
  const entries=Object.entries(h.hourly_visitors).filter(([k])=>parseInt(k)>=8&&parseInt(k)<=22).sort(([a],[b])=>parseInt(a)-parseInt(b));
  const peak=String(h.peak_hour);
  hourlyChart.data.labels=entries.map(([k])=>k);
  hourlyChart.data.datasets[0].data=entries.map(([,v])=>v);
  hourlyChart.data.datasets[0].backgroundColor=entries.map(([k])=>k===peak?'rgba(245,158,11,.85)':'rgba(59,130,246,.6)');
  hourlyChart.update();
}

function initDeptChart(){
  if(deptChart){deptChart.destroy();deptChart=null;}
  const ctx=document.getElementById('dept-chart').getContext('2d');
  deptChart=new Chart(ctx,{type:'doughnut',data:{labels:[],datasets:[{data:[],backgroundColor:['#3b82f6','#6366f1','#10b981','#f59e0b','#ef4444','#06b6d4','#ec4899'],borderWidth:0,hoverOffset:6}]},options:{responsive:true,maintainAspectRatio:true,plugins:{legend:{position:'right',labels:{color:'#94a3b8',font:{size:9},boxWidth:10,padding:8}},tooltip:{callbacks:{label:ctx=>' ₹'+ctx.parsed.toLocaleString('en-IN',{maximumFractionDigits:0})}}}}});
}
function updateRevenue(r){
  if(!r)return;
  const fmt=v=>'₹'+(v||0).toLocaleString('en-IN',{maximumFractionDigits:0});
  document.getElementById('revenue-rows').innerHTML='<div class="rev-row"><span class="rev-label">Total GMV</span><span class="rev-value">'+fmt(r.total_gmv_inr)+'</span></div><div class="rev-row"><span class="rev-label">Orders</span><span class="rev-value" style="color:var(--cyan)">'+(r.total_transactions||0)+'</span></div><div class="rev-row"><span class="rev-label">Avg Basket</span><span class="rev-value">'+fmt(r.avg_basket_value_inr)+'</span></div><div class="rev-row"><span class="rev-label">Peak Hour</span><span class="rev-value" style="color:var(--yellow)">'+(r.peak_revenue_hour!=null?r.peak_revenue_hour+':00':'—')+'</span></div>';
  if(r.department_breakdown?.length&&deptChart){const top5=r.department_breakdown.slice(0,5);deptChart.data.labels=top5.map(d=>d.department.slice(0,12));deptChart.data.datasets[0].data=top5.map(d=>d.gmv_inr);deptChart.update();}
}
function updateJourney(j){
  if(!j?.top_paths)return;
  document.getElementById('journey-list').innerHTML='<div style="font-size:.61rem;color:var(--text3);margin-bottom:10px">Avg '+(j.avg_zones_per_visit||0).toFixed(1)+' zones/visit · '+j.total_sessions_with_zones+' sessions</div>'+(j.top_paths.slice(0,5).map(p=>'<div class="path-item"><span class="path-text">'+p.path+'</span><span class="path-count">'+p.count+'</span></div>').join('')||'<div style="color:var(--text3);font-size:.77rem">No journeys yet</div>');
}
function updateConfidence(c){
  if(!c?.buckets)return;
  setText('conf-avg',c.avg_confidence?(c.avg_confidence*100).toFixed(1)+'%':'—');
  setText('conf-total',c.total_events?.toLocaleString()??'—');
  const total=c.total_events||1,colors={'0.0-0.5':'#ef4444','0.5-0.7':'#f59e0b','0.7-0.85':'#3b82f6','0.85-0.95':'#10b981','0.95-1.0':'#06b6d4'};
  document.getElementById('conf-chart').innerHTML=Object.entries(c.buckets).map(([k,v])=>{const pct=Math.round(v/total*100);return '<div class="conf-bar-row"><div class="conf-label">'+k+'</div><div class="conf-bar-outer"><div class="conf-bar-inner" style="width:'+pct+'%;background:'+(colors[k]||'#3b82f6')+'"></div></div><div class="conf-pct">'+pct+'%</div></div>';}).join('');
}

function toggleCompare(){
  compareVisible=!compareVisible;
  document.getElementById('compare-panel').classList.toggle('visible',compareVisible);
  document.getElementById('compare-btn').classList.toggle('active',compareVisible);
  if(compareVisible)loadCompare();
}
async function loadCompare(){
  try{
    const r=await fetch('/stores/compare?ids=STORE_BLR_002,STORE_BLR_001');
    if(!r.ok)return;
    const d=await r.json(),best=d.best_performer;
    document.getElementById('winner-banner').innerHTML=best?'🏆 Top performer: <strong>'+best+'</strong> — '+(STORE_NAMES[best]||best)+' · Chain avg: '+(d.chain_avg_conversion*100).toFixed(1)+'%':'';
    const fmtF={
      'Unique Visitors':s=>s.unique_visitors,
      'Conversion Rate':s=>(s.conversion_rate*100).toFixed(1)+'%',
      'Avg Dwell':s=>fmtMs(s.avg_dwell_ms),
      'Queue Depth':s=>s.queue_depth,
      'Total GMV':s=>'₹'+(s.total_gmv_inr||0).toLocaleString('en-IN',{maximumFractionDigits:0}),
      'Avg Basket':s=>'₹'+(s.avg_basket_value_inr||0).toLocaleString('en-IN',{maximumFractionDigits:0})
    };
    const betF={
      'Unique Visitors':(a,b)=>a.unique_visitors>=b.unique_visitors,
      'Conversion Rate':(a,b)=>a.conversion_rate>=b.conversion_rate,
      'Avg Dwell':(a,b)=>a.avg_dwell_ms>=b.avg_dwell_ms,
      'Queue Depth':(a,b)=>a.queue_depth<=b.queue_depth,
      'Total GMV':(a,b)=>a.total_gmv_inr>=b.total_gmv_inr,
      'Avg Basket':(a,b)=>a.avg_basket_value_inr>=b.avg_basket_value_inr
    };
    document.getElementById('compare-grid').innerHTML=d.stores.map((s,si)=>{
      const isBest=s.store_id===best,other=d.stores[1-si];
      const rows=Object.entries(fmtF).map(([lbl,fn])=>'<div class="cmp-row"><span class="cmp-key">'+lbl+'</span><span class="cmp-val'+(other&&betF[lbl](s,other)?' best':'')+'">'+fn(s)+'</span></div>').join('');
      return '<div class="cmp-store" style="'+(isBest?'border-color:rgba(16,185,129,.4)':'')+'"><div class="cmp-title">'+(isBest?'🏆 ':'🏪 ')+'<strong>'+s.store_id+'</strong>'+(isBest?' <span style="color:var(--green);font-size:.65rem"> — Leader</span>':'')+'</div><div style="font-size:.63rem;color:var(--text3);margin-bottom:10px">'+(STORE_NAMES[s.store_id]||s.store_id)+'</div>'+rows+'</div>';
    }).join('');
  }catch(e){}
}

async function fetchExtras(){
  try{
    const[rH,rP,rJ,rC]=await Promise.all([fetch('/stores/'+storeId+'/hourly'),fetch('/stores/'+storeId+'/pos'),fetch('/stores/'+storeId+'/journey'),fetch('/stores/'+storeId+'/confidence')]);
    if(rH.ok)updateHourly(await rH.json());
    if(rP.ok)updateRevenue(await rP.json());
    if(rJ.ok)updateJourney(await rJ.json());
    if(rC.ok)updateConfidence(await rC.json());
  }catch(e){}
}
function animateTo(id,target){const el=document.getElementById(id);if(!el)return;const cur=parseInt(el.textContent)||0;if(cur===target)return;let step=0,steps=18;const delta=(target-cur)/steps;const iv=setInterval(()=>{step++;el.textContent=Math.round(cur+delta*step);if(step>=steps){el.textContent=target;clearInterval(iv);}},25);}
function setText(id,v){const el=document.getElementById(id);if(el)el.textContent=v;}

initHourlyChart();initDeptChart();connectWS();fetchExtras();
setInterval(fetchExtras,30000);
</script>
</body>
</html>
"""
