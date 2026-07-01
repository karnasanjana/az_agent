"""Single self-contained UI page (inline HTML/CSS/JS, no external deps).

Served at GET /. A data engineer pastes or uploads a BRD, generates the plan,
reviews all three layers (visual graph + JSON + Silver/Gold scripts + the
human-readable governance plan), then approves to build + run for real (or in the
MOCK tenant), watching live Bronze->Silver->Gold status.
"""

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>BRD &rarr; ADF Medallion Agent</title>
<style>
  :root {
    --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --line:#2a2f3a;
    --ink:#e6e8ec; --mut:#9aa3b2; --accent:#4f9cff;
    --bronze:#c8803c; --silver:#9aa7b4; --gold:#d8b13a;
    --ok:#3fb950; --bad:#f85149; --warn:#d29922;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,Arial; }
  header { padding:14px 20px; border-bottom:1px solid var(--line);
           display:flex; align-items:center; gap:12px; }
  header h1 { font-size:16px; margin:0; font-weight:650; }
  .tag { font-size:11px; padding:2px 8px; border-radius:10px; border:1px solid var(--line); color:var(--mut); }
  .tag.mock { color:#000; background:var(--warn); border-color:var(--warn); font-weight:700; }
  .tag.live { color:var(--ok); border-color:var(--ok); }
  main { display:grid; grid-template-columns:380px 1fr; gap:0; height:calc(100vh - 51px); }
  .left { border-right:1px solid var(--line); padding:16px; overflow:auto; }
  .right { padding:16px; overflow:auto; }
  textarea { width:100%; height:230px; resize:vertical; background:var(--panel); color:var(--ink);
             border:1px solid var(--line); border-radius:8px; padding:10px; font-family:ui-monospace,Consolas,monospace; }
  .row { display:flex; gap:8px; align-items:center; margin:10px 0; flex-wrap:wrap; }
  button { background:var(--accent); color:#fff; border:0; border-radius:8px; padding:9px 14px;
           font-weight:600; cursor:pointer; }
  button.sec { background:var(--panel2); color:var(--ink); border:1px solid var(--line); }
  button.ok { background:var(--ok); }
  button.bad { background:var(--bad); }
  button:disabled { opacity:.45; cursor:not-allowed; }
  h2 { font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:var(--mut); margin:18px 0 8px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; margin-bottom:12px; }
  pre { background:#0b0d12; border:1px solid var(--line); border-radius:8px; padding:10px; overflow:auto;
        font-family:ui-monospace,Consolas,monospace; font-size:12px; margin:6px 0; }
  .check { display:flex; gap:8px; align-items:flex-start; padding:3px 0; }
  .dot { width:9px; height:9px; border-radius:50%; margin-top:6px; flex:0 0 auto; }
  .dot.ok { background:var(--ok);} .dot.bad{ background:var(--bad);}
  .muted { color:var(--mut); }
  /* graph */
  .graph { display:flex; align-items:center; gap:0; flex-wrap:wrap; }
  .node { width:190px; border:2px solid var(--line); border-radius:12px; padding:12px; cursor:pointer;
          background:var(--panel2); transition:.12s; }
  .node:hover { transform:translateY(-2px); }
  .node.sel { outline:2px solid var(--accent); }
  .node .l { font-weight:700; letter-spacing:.05em; }
  .node .k { font-size:11px; color:var(--mut); }
  .node.bronze { border-color:var(--bronze);} .node.silver{ border-color:var(--silver);} .node.gold{ border-color:var(--gold);}
  .arrow { padding:0 10px; color:var(--mut); font-size:22px; }
  .arrow small { display:block; font-size:9px; text-align:center; color:var(--mut); }
  details { border:1px solid var(--line); border-radius:8px; margin:6px 0; background:var(--panel); }
  summary { cursor:pointer; padding:8px 10px; font-weight:600; }
  .status-grid { display:flex; gap:10px; margin:8px 0; flex-wrap:wrap; }
  .layerbox { flex:1; min-width:150px; border:1px solid var(--line); border-radius:8px; padding:10px; background:var(--panel2); }
  .layerbox .s { font-weight:700; } .badge{ font-size:11px; padding:1px 7px; border-radius:9px; border:1px solid var(--line);}
  .s-Succeeded{color:var(--ok);} .s-Failed{color:var(--bad);} .s-InProgress{color:var(--accent);} .s-Pending{color:var(--mut);}
  .err { color:var(--bad); white-space:pre-wrap; }
  .pill { font-size:11px; color:var(--mut); }
  label.file { font-size:12px; color:var(--mut); cursor:pointer; }
</style>
</head>
<body>
<header>
  <h1>BRD &rarr; ADF Medallion Agent</h1>
  <span id="modeTag" class="tag">checking&hellip;</span>
  <span class="tag">Bronze=Copy &nbsp;Silver/Gold=Data&nbsp;Flow</span>
  <span id="runTag" class="pill"></span>
</header>
<main>
  <section class="left">
    <h2>1. Business Requirements</h2>
    <textarea id="brd" placeholder="Paste the BRD here, or upload a .txt/.md/.pdf file&hellip;"></textarea>
    <div class="row">
      <label class="file">Upload BRD (.txt/.md/.pdf)<input id="file" type="file" accept=".txt,.md,.text,.pdf" style="display:none"/></label>
      <span id="fileName" class="pill"></span>
    </div>
    <div class="row">
      <button id="genBtn">Generate pipelines</button>
      <button id="sampleBtn" class="sec">Load COVID example</button>
    </div>
    <div id="genState" class="pill"></div>

    <div id="preflight"></div>
    <div id="clar"></div>

    <div id="chatBox" style="display:none">
      <h2>Chat &mdash; refine or answer questions</h2>
      <div id="chatLog" class="card" style="max-height:240px;overflow:auto"></div>
      <div class="row">
        <input id="chatInput" placeholder="e.g. rename the gold sink, or answer a question&hellip;"
               style="flex:1;min-width:160px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:9px"/>
        <button id="chatBtn" class="sec">Send</button>
      </div>
    </div>

    <div id="approveBox" style="display:none">
      <h2>4. Approval gate</h2>
      <div class="muted" id="gateNote"></div>
      <div class="row">
        <button id="approveBtn" class="ok">Approve &mdash; build &amp; run</button>
        <button id="rejectBtn" class="bad sec">Reject</button>
      </div>
    </div>

    <div id="liveBox" style="display:none">
      <h2>5. Live run</h2>
      <div id="deployState" class="muted"></div>
      <div class="status-grid" id="layers"></div>
      <div id="heals"></div>
      <div id="runErr" class="err"></div>
    </div>
  </section>

  <section class="right">
    <h2>2. Pipeline graph (click a layer)</h2>
    <div id="graph" class="muted">Generate a plan to see the Bronze&rarr;Silver&rarr;Gold graph.</div>

    <h2>Node detail</h2>
    <div id="detail" class="card muted">Select a node above.</div>

    <h2>3. Governance plan (human-readable)</h2>
    <details><summary>Show plain-text plan</summary><pre id="planText" class="muted">&mdash;</pre></details>

    <h2>All objects</h2>
    <div id="objects" class="muted">&mdash;</div>
  </section>
</main>

<script>
const $ = (s)=>document.querySelector(s);
let RUN = null, REVIEW = null, GRAPH = null, POLL = null, UPLOAD = null;

async function jget(u){ const r = await fetch(u); if(!r.ok) throw new Error((await r.json()).detail||r.status); return r.json(); }
async function jpost(u, body){ const r = await fetch(u,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok) throw new Error((await r.json()).detail||r.status); return r.json(); }

(async()=>{ try{ const h=await jget('/health');
  const t=$('#modeTag'); if(h.mock){t.textContent='MOCK tenant (no Azure writes)';t.className='tag mock';}
  else{t.textContent='LIVE Azure';t.className='tag live';} }catch(e){} })();

$('#file').addEventListener('change', async (e)=>{
  const f=e.target.files[0]; if(!f) return; $('#fileName').textContent=f.name;
  const isPdf = /\.pdf$/i.test(f.name) || f.type==='application/pdf';
  if(isPdf){
    // PDFs can't be read as text in the browser — send the file to the server.
    UPLOAD = f; $('#brd').value=''; $('#brd').placeholder='PDF ready: '+f.name+' — click Generate.';
  }else{
    UPLOAD = null; $('#brd').value = await f.text();
  }
});

$('#sampleBtn').onclick = async ()=>{
  $('#brd').value = SAMPLE_BRD; $('#fileName').textContent=''; UPLOAD=null;
};

// Live "elapsed seconds" timer on a button so long LLM calls don't look frozen.
function startTimer(sel, label){
  const el=$(sel), t0=Date.now();
  el.disabled=true;
  const id=setInterval(()=>{ el.textContent=label+' '+Math.round((Date.now()-t0)/1000)+'s'; }, 1000);
  el.textContent=label+' 0s';
  return ()=>{ clearInterval(id); el.disabled=false; };
}

$('#genBtn').onclick = async ()=>{
  const brd = $('#brd').value.trim();
  if(!brd && !UPLOAD){ alert('Paste or upload a BRD first.'); return; }
  reset();
  $('#genState').textContent='Large BRDs can take 1–2 minutes to generate — please wait.';
  const stop = startTimer('#genBtn','Generating&hellip;');
  try{
    const fd = new FormData();
    if(UPLOAD){ fd.append('file', UPLOAD); } else { fd.append('brd', brd); }
    const r = await fetch('/plan',{method:'POST',body:fd});
    const data = await r.json();
    if(!r.ok){ throw new Error(data.detail||'plan failed'); }
    RUN = data.run_id; $('#runTag').textContent = 'run '+RUN;
    $('#chatBox').style.display='block';
    applyPlan(data);
    $('#genState').textContent='';
  }catch(e){ alert('Generate failed: '+e.message); $('#genState').textContent=''; }
  finally{ stop(); $('#genBtn').textContent='Generate pipelines'; }
};

// Render a /plan or /chat response into the page.
function applyPlan(data){
  if(data.status==='NEEDS_CLARIFICATION'){
    renderClar(data.clarifications);
    $('#approveBox').style.display='none';
    REVIEW=GRAPH=null; $('#graph').textContent=''; $('#objects').innerHTML='';
    $('#preflight').innerHTML=''; $('#planText').textContent='—';
    return;
  }
  $('#clar').innerHTML='';
  // A refine reopens the approval gate — stop any stale live run/poll.
  if(POLL){ clearInterval(POLL); POLL=null; }
  $('#liveBox').style.display='none';
  REVIEW = data.review; GRAPH = data.graph;
  renderPreflight(data.preflight);
  renderGraph(GRAPH); renderObjects(REVIEW);
  $('#planText').textContent=data.plan_text; $('#planText').className='';
  renderGate(data);
}

// --- chat: refine the spec or answer the agent's questions ---
function chatAppend(who, text){
  const log=$('#chatLog');
  log.innerHTML += '<div style="margin:4px 0"><b class="'+(who==='you'?'':'muted')+'">'+
    (who==='you'?'You':'Agent')+':</b> '+esc(text)+'</div>';
  log.scrollTop = log.scrollHeight;
}

async function sendChat(){
  const msg = $('#chatInput').value.trim();
  if(!msg || !RUN) return;
  chatAppend('you', msg); $('#chatInput').value='';
  const stop = startTimer('#chatBtn','Working&hellip;');
  try{
    const data = await jpost('/chat',{run_id:RUN, message:msg});
    if(data.status==='NEEDS_CLARIFICATION'){
      chatAppend('agent', 'I need a bit more: '+(data.clarifications||[]).join(' • '));
    }else{
      chatAppend('agent', 'Updated — pre-flight '+(data.preflight.passed?'PASS':'FAIL')+'. '+
        (data.preflight.passed?'Re-approve when ready.':'See the failing checks.'));
    }
    applyPlan(data);
  }catch(e){ chatAppend('agent', 'Sorry — '+e.message); }
  finally{ stop(); $('#chatBtn').textContent='Send'; }
}
$('#chatBtn').onclick = sendChat;
$('#chatInput').addEventListener('keydown', e=>{ if(e.key==='Enter') sendChat(); });

function reset(){
  REVIEW=GRAPH=null; if(POLL){clearInterval(POLL);POLL=null;}
  ['preflight','clar','graph','objects','chatLog'].forEach(id=>$('#'+id).innerHTML='');
  $('#detail').innerHTML='Select a node above.'; $('#detail').className='card muted';
  $('#planText').textContent='—'; $('#approveBox').style.display='none'; $('#liveBox').style.display='none';
  $('#chatBox').style.display='none'; $('#graph').textContent=''; $('#runErr').textContent='';
}

function renderClar(items){
  $('#clar').innerHTML = '<h2>Needs clarification</h2><div class="card">'+
    'The agent will not invent components. Answer these in the chat below (or edit the BRD and regenerate):'+
    '<ul>'+items.map(i=>'<li>'+esc(i)+'</li>').join('')+'</ul></div>';
}

function renderPreflight(pf){
  const rows = pf.checks.map(c=>'<div class="check"><span class="dot '+(c.passed?'ok':'bad')+'"></span>'+
     '<div><b>'+esc(c.name)+'</b><div class="muted">'+esc(c.detail||'')+'</div></div></div>').join('');
  $('#preflight').innerHTML='<h2>Pre-flight ('+(pf.passed?'PASS':'FAIL')+')</h2><div class="card">'+rows+'</div>';
}

function renderGraph(g){
  const order = ['bronze','silver','gold'];
  const nodes = order.map(l=>g.nodes.find(n=>n.id===l)).filter(Boolean);
  let html='<div class="graph">';
  nodes.forEach((n,i)=>{
    html += '<div class="node '+n.id+'" data-id="'+n.id+'" onclick="selNode(\''+n.id+'\')">'+
            '<div class="l">'+esc(n.label)+'</div><div class="k">'+esc(n.kind)+'</div>'+
            '<div class="k">'+esc(n.note||'')+'</div></div>';
    if(i<nodes.length-1) html+='<div class="arrow">&rarr;<small>Succeeded</small></div>';
  });
  html+='</div>';
  $('#graph').innerHTML=html;
}

function selNode(id){
  document.querySelectorAll('.node').forEach(n=>n.classList.toggle('sel', n.dataset.id===id));
  const n = GRAPH.nodes.find(x=>x.id===id);
  let h = '<div><b>'+esc(n.label)+'</b> &mdash; '+esc(n.kind)+'</div>'+
          '<div class="muted">object: '+esc(n.object||'')+' &nbsp; source: '+esc(n.source_dataset||'-')+
          ' &rarr; sink: '+esc(n.sink_dataset||'-')+'</div>';
  if(n.id==='bronze'){ h+='<div class="pill">raw landing, no transformation &mdash; no script (correct)</div>'; }
  h += '<h2>JSON</h2><pre>'+esc(JSON.stringify(n.json,null,2))+'</pre>';
  if(n.script){ h+='<h2>Data Flow script</h2><pre>'+esc(n.script)+'</pre>'; }
  $('#detail').className='card'; $('#detail').innerHTML=h;
}
window.selNode = selNode;

function renderObjects(rev){
  const cats = [['linked_services','Linked services'],['datasets','Datasets'],
                ['dataflows','Data flows'],['pipelines','Pipelines'],['triggers','Triggers']];
  let html='';
  cats.forEach(([k,label])=>{
    (rev[k]||[]).forEach(o=>{
      html += '<details><summary>'+esc(label.slice(0,-1))+': '+esc(o.name)+'</summary>'+
              '<pre>'+esc(JSON.stringify(o.json,null,2))+'</pre></details>';
    });
  });
  $('#objects').innerHTML = html || '<span class="muted">—</span>';
}

function renderGate(data){
  $('#approveBox').style.display='block';
  const ok = data.preflight.passed;
  $('#approveBtn').disabled = !ok;
  $('#gateNote').innerHTML = ok
    ? 'Pre-flight passed and the plan is previewed. Approving will '+
      (data.mock?'write to the MOCK tenant and simulate the run.':'connect to Azure and BUILD + RUN for real.')
    : '<span class="err">Pre-flight failed.</span> Tell the agent what to fix in the '+
      '<b>chat below</b> (e.g. &ldquo;add the silver and gold data flows and a master '+
      'pipeline chaining bronze&rarr;silver&rarr;gold&rdquo;) — it will edit the plan in place, no need to retype the BRD.';
}

$('#rejectBtn').onclick = ()=>{ reset(); $('#runTag').textContent=''; RUN=null; };

$('#approveBtn').onclick = async ()=>{
  if(!RUN) return;
  $('#approveBtn').disabled=true;
  try{
    await jpost('/approve',{run_id:RUN});
    $('#liveBox').style.display='block';
    POLL = setInterval(poll, 1500); poll();
  }catch(e){ alert('Approve blocked: '+e.message); $('#approveBtn').disabled=false; }
};

async function poll(){
  if(!RUN) return;
  let s; try{ s = await jget('/status/'+RUN); }catch(e){ return; }
  $('#deployState').textContent = 'state: '+s.status+
    (s.deployed? '  •  deployed '+s.deployed.length+' objects':'')+
    (s.containers_created? '  •  containers '+JSON.stringify(s.containers_created):'');
  if(s.heals && s.heals.length){
    $('#heals').innerHTML = '<h2>Auto-fixes</h2><div class="card">'+
      s.heals.map(h=>'<div class="check"><span class="dot ok"></span><div><b>'+
        esc(h.category)+'/'+esc(h.name)+'</b><div class="muted">'+esc(h.fix||'')+'</div></div></div>').join('')+
      '</div>';
  }
  const layers = (s.run && s.run.layers) || {};
  $('#layers').innerHTML = ['bronze','silver','gold'].map(l=>{
    const d = layers[l] || {status:'Pending'};
    return '<div class="layerbox"><div class="s">'+l.toUpperCase()+'</div>'+
      '<div class="badge s-'+(d.status||'Pending')+'">'+(d.status||'Pending')+'</div>'+
      (d.run_id?'<div class="pill">run '+esc(d.run_id)+'</div>':'')+
      (d.error?'<div class="err">'+esc(d.error)+'</div>':'')+'</div>';
  }).join('');
  if(['SUCCEEDED','FAILED','ERROR'].includes(s.status)){
    clearInterval(POLL); POLL=null;
    if(s.error) $('#runErr').textContent = s.error;
    if(s.report && s.report.attempts){
      const last = s.report.attempts[s.report.attempts.length-1];
      if(last && last.error) $('#runErr').textContent = last.error;
    }
  }
}

function esc(s){ return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

const SAMPLE_BRD = `Build a COVID-19 medallion pipeline in Azure Data Factory ONLY (no Databricks, Synapse, or Fabric).

SOURCE: Johns Hopkins CSSE daily reports, anonymous HTTPS files at
https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_daily_reports/
with file pattern MM-DD-YYYY.csv, parameterised by report date.

STORAGE: ADLS Gen2 account 'covidlake' with bronze, silver, gold containers, Managed Identity (no keys).

BRONZE: copy the raw daily CSV byte-for-byte into the bronze container. No transformation.

SILVER: cast Confirmed/Deaths/Recovered/Active to integer (null -> 0), cast Last_Update to timestamp,
add an ingestion_date audit column, drop rows with a null/empty Country_Region, and dedup on
(Country_Region, Province_State, Last_Update). Write Parquet to silver.

GOLD: sum Confirmed/Deaths/Recovered by Country_Region, compute case_fatality_rate =
total_deaths / total_confirmed * 100 (0.0 when total_confirmed is 0), sort by total_confirmed desc.
Write CSV to gold.

ORCHESTRATION: chain Bronze -> Silver -> Gold so a failed Bronze halts downstream work.
Provide a manual trigger and a daily schedule trigger.`;
</script>
</body>
</html>
"""
