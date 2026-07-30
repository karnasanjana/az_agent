"""Single self-contained UI page (inline HTML/CSS/JS, no external deps).

Served at GET /. A data engineer pastes or uploads a BRD, generates the plan,
reviews the human-readable governance plan, then approves to build + run for real
(or in the MOCK tenant), watching live Bronze->Silver->Gold status.
"""

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>BRD &rarr; ADF Medallion Agent</title>
<style>
  :root {
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2229;
    --line:#262c36; --line-strong:#333b47; --ink:#e6edf3; --mut:#8b949e;
    --accent:#4493f8; --accent-soft:rgba(68,147,248,.12);
    --bronze:#cd8a4f; --silver:#a7b4c2; --gold:#d8b13a;
    --ok:#3fb950; --bad:#f85149; --warn:#d29922;
  }
  * { box-sizing:border-box; }
  html { color-scheme:dark; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:14px/1.55 Inter,ui-sans-serif,system-ui,Segoe UI,Roboto,Arial; -webkit-font-smoothing:antialiased; }
  header { height:56px; padding:0 20px; border-bottom:1px solid var(--line);
           background:var(--panel); display:flex; align-items:center; gap:16px; }
  .brand { display:flex; align-items:center; gap:10px; margin-right:auto; }
  .brand-mark { width:30px; height:30px; border:1px solid var(--line-strong); border-radius:7px;
    display:grid; place-items:center; color:var(--accent); background:var(--accent-soft); }
  .brand-mark svg { width:18px; height:18px; }
  header h1 { font-size:14px; line-height:1.2; margin:0; font-weight:600; letter-spacing:-.01em; }
  .subtitle { color:var(--mut); font-size:11px; margin-top:1px; }
  .tag { font-size:11px; line-height:1; padding:5px 9px; border-radius:6px; border:1px solid var(--line-strong); color:var(--mut); background:var(--panel2); }
  .tag.mock { color:#1c1402; background:var(--warn); border-color:var(--warn); font-weight:700; }
  .tag.live { color:var(--ok); border-color:rgba(63,185,80,.4); background:rgba(63,185,80,.1); }
  .workspace { display:flex; height:calc(100vh - 56px); }
  main { flex:1; min-width:0; display:grid; grid-template-columns:minmax(360px, 42%) minmax(0,1fr); height:100%; }
  .left { border-right:1px solid var(--line); overflow:auto; background:var(--bg); }
  .left-inner { padding:22px; }
  .right { overflow:auto; background:var(--panel); }
  .canvas-head { padding:14px 24px; border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:space-between; background:var(--panel); position:sticky; top:0; z-index:3; }
  .canvas-title { font-weight:600; font-size:14px; } .canvas-sub { font-size:11px; color:var(--mut); margin-top:2px; }
  .right-inner { padding:22px clamp(22px,3vw,36px) 48px; }
  textarea { width:100%; height:200px; resize:vertical; background:var(--panel); color:var(--ink);
             border:1px solid var(--line-strong); border-radius:8px; padding:12px 13px; font-family:ui-monospace,Consolas,monospace;
             font-size:13px; outline:none; transition:border-color .15s,box-shadow .15s; }
  textarea:focus, input:focus { border-color:var(--accent)!important; box-shadow:0 0 0 3px var(--accent-soft); outline:none; }
  textarea::placeholder, input::placeholder { color:#586069; }
  .row { display:flex; gap:8px; align-items:center; margin:10px 0; flex-wrap:wrap; }
  button { background:var(--accent); color:#fff; border:1px solid var(--accent); border-radius:7px; padding:9px 15px;
           font-weight:600; font-size:13px; cursor:pointer; transition:filter .15s; }
  button:hover:not(:disabled) { filter:brightness(1.08); }
  button.sec { background:var(--panel2); color:var(--ink); border:1px solid var(--line-strong); }
  button.sec:hover:not(:disabled) { border-color:var(--mut); filter:none; }
  button.ok { background:var(--ok); border-color:var(--ok); color:#04140a; }
  button.bad { background:transparent; color:#ff9298; border:1px solid rgba(248,81,73,.45); }
  button:disabled { opacity:.4; cursor:not-allowed; }
  h2 { font:600 11px ui-sans-serif,system-ui; text-transform:uppercase; letter-spacing:.07em; color:var(--mut); margin:22px 0 9px; }
  h3 { color:var(--ink); font-size:15px; margin:20px 0 7px; }
  .card { background:var(--panel2); border:1px solid var(--line); border-radius:9px; padding:14px; margin-bottom:12px; }
  pre { background:#0b0e14; border:1px solid var(--line); border-radius:8px; padding:11px; overflow:auto;
        font-family:ui-monospace,Consolas,monospace; font-size:12px; margin:6px 0; }
  .check { display:flex; gap:8px; align-items:flex-start; padding:3px 0; }
  .dot { width:9px; height:9px; border-radius:50%; margin-top:6px; flex:0 0 auto; background:var(--mut); }
  .dot.ok { background:var(--ok);} .dot.bad{ background:var(--bad);} .dot.warn{ background:var(--warn);}
  .muted { color:var(--mut); }
  details { border:1px solid var(--line); border-radius:8px; margin:6px 0; background:var(--panel2); }
  summary { cursor:pointer; padding:9px 12px; font-weight:500; }
  .status-grid { display:flex; gap:10px; margin:8px 0; flex-wrap:wrap; }
  .layerbox { flex:1; min-width:150px; border:1px solid var(--line); border-radius:9px; padding:12px; background:var(--panel2); position:relative; overflow:hidden; }
  .layerbox:before { content:""; position:absolute; inset:0 auto 0 0; width:3px; background:var(--mut); }
  .layerbox:nth-child(1):before { background:var(--bronze); } .layerbox:nth-child(2):before { background:var(--silver); } .layerbox:nth-child(3):before { background:var(--gold); }
  .layerbox .s { font-weight:600; } .badge{ font-size:11px; padding:1px 7px; border-radius:6px; border:1px solid var(--line);}
  .s-Succeeded{color:var(--ok);} .s-Failed{color:var(--bad);} .s-InProgress{color:var(--accent);} .s-Pending{color:var(--mut);}
  .err { color:var(--bad); white-space:pre-wrap; }
  .pill { font-size:11px; color:var(--mut); }
  label.file { font-size:12px; color:var(--accent); cursor:pointer; border:1px dashed var(--line-strong); border-radius:7px; padding:7px 11px; transition:background .15s,border-color .15s; }
  label.file:hover { background:var(--accent-soft); border-color:var(--accent); }
  .warn { color:var(--warn); white-space:pre-wrap; }
  code { color:#79c0ff; background:rgba(68,147,248,.1); border:1px solid rgba(68,147,248,.15); border-radius:5px; padding:1px 4px; }
  a { color:var(--accent); text-underline-offset:3px; }
  ::selection { background:rgba(68,147,248,.28); }
  ::-webkit-scrollbar { width:10px; height:10px; } ::-webkit-scrollbar-track { background:transparent; }
  ::-webkit-scrollbar-thumb { background:#30363d; border:3px solid transparent; background-clip:padding-box; border-radius:10px; }
  .journey { display:flex; align-items:center; gap:8px; color:var(--mut); font-size:11px; font-weight:500; }
  .journey span { display:flex; align-items:center; gap:6px; } .journey i { width:7px; height:7px; border-radius:50%; background:#3a424e; } .journey span.is-active { color:var(--ink); } .journey span.is-active i { background:var(--accent); }
  .journey b { width:18px; height:1px; background:var(--line-strong); }
  .pipeline-canvas { margin-bottom:24px; }
  .pipeline-track { display:grid; grid-template-columns:minmax(0,1fr) 34px minmax(0,1fr) 34px minmax(0,1fr); align-items:stretch; }
  .flow-node { padding:14px; background:var(--panel2); border:1px solid var(--line); border-top:2px solid var(--mut); border-radius:9px; transition:border-color .2s,opacity .2s; }
  .flow-node.bronze { border-top-color:var(--bronze); } .flow-node.silver { border-top-color:var(--silver); } .flow-node.gold { border-top-color:var(--gold); }
  .flow-node.dim { opacity:.5; }
  .flow-node.active { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent); }
  .node-kicker { font-size:10px; color:var(--mut); text-transform:uppercase; letter-spacing:.08em; display:flex; align-items:center; gap:7px; }
  .node-dot { width:7px; height:7px; border-radius:50%; background:var(--mut); }
  .bronze .node-dot { background:var(--bronze); } .silver .node-dot { background:var(--silver); } .gold .node-dot { background:var(--gold); }
  .flow-node strong { display:block; margin:12px 0 3px; font-size:14px; } .flow-node p { margin:0; color:var(--mut); font-size:11px; }
  .node-status { margin-top:9px; font-size:11px; font-weight:600; }
  .flow-link { align-self:center; height:1px; background:var(--line-strong); position:relative; }
  .flow-link:after { content:""; position:absolute; right:-1px; top:-3px; width:6px; height:6px; border-top:1px solid var(--line-strong); border-right:1px solid var(--line-strong); transform:rotate(45deg); }
  .composer-note { color:var(--mut); font-size:12px; margin:-2px 0 12px; }
  @media (max-width:820px) {
    header { padding:10px 16px; height:auto; flex-wrap:wrap; } .brand { width:100%; }
    .workspace { height:auto; } main { display:block; height:auto; }
    .left { border-right:0; border-bottom:1px solid var(--line); } .right { min-height:55vh; }
    textarea { height:180px; } .journey { display:none; } .pipeline-track { grid-template-columns:1fr; gap:8px; } .flow-link { height:20px; width:1px; margin:auto; } .flow-link:after { right:-3px; top:auto; bottom:0; transform:rotate(135deg); }
  }
  body.embedded > header { display:none; }
  body.embedded .workspace { height:100vh; }
</style>
</head>
<body>
<script>if(new URLSearchParams(location.search).get('embedded')==='1')document.body.classList.add('embedded');</script>
<header>
  <div class="brand">
    <div class="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="5" cy="6" r="2.25"/><circle cx="19" cy="6" r="2.25"/><circle cx="12" cy="18" r="2.25"/><path d="M7.2 6h9.6M6.5 8l4.3 7.8M17.5 8l-4.3 7.8"/></svg>
    </div>
    <div><h1>ADF Pipeline Builder</h1><div class="subtitle">Business requirements to governed Azure data pipelines</div></div>
  </div>
  <div class="journey" aria-label="Build workflow"><span id="journeyDefine" class="is-active"><i></i>Define</span><b></b><span id="journeyReview"><i></i>Review</span><b></b><span id="journeyDeploy"><i></i>Deploy</span></div>
  <span id="modeTag" class="tag">checking&hellip;</span>
  <span id="healTag" class="tag" style="display:none">self-heal ON</span>
  <span id="runTag" class="pill"></span>
</header>
<div class="workspace">
<main>
  <section class="left">
    <div class="left-inner">
    <h2>Describe your pipeline</h2>
    <div class="composer-note">Paste a BRD or explain the source, transformations, and destination in plain English.</div>
    <textarea id="brd" placeholder="Describe it in plain English or paste a full BRD &mdash; e.g. &quot;copy the daily sales CSVs from https://... into the lake and aggregate revenue by region&quot;. Or upload a .txt/.md/.pdf."></textarea>
    <div class="row">
      <label class="file">Upload BRD (.txt/.md/.pdf)<input id="file" type="file" accept=".txt,.md,.text,.pdf" style="display:none"/></label>
      <span id="fileName" class="pill"></span>
    </div>
    <div class="row">
      <button id="genBtn">Generate pipelines</button>
    </div>
    <div id="genState" class="pill"></div>

    <div id="preflight"></div>
    <div id="clar"></div>

    <div id="chatBox" style="display:none">
      <h2>Chat &mdash; refine or answer questions</h2>
      <div class="card" style="padding:0">
        <div id="chatLog" style="max-height:260px;overflow:auto;padding:10px"></div>
        <div style="display:flex;gap:8px;padding:8px;border-top:1px solid var(--line)">
          <input id="chatInput" placeholder="e.g. rename the gold sink, or answer a question&hellip;"
                 style="flex:1;min-width:120px;background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:9px"/>
          <button id="chatBtn" class="sec">Send</button>
        </div>
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
      <div class="row">
        <button id="stopBtn" class="bad sec">Stop run</button>
      </div>
      <div id="deployState" class="muted"></div>
      <div class="status-grid" id="layers"></div>
      <div id="attemptLog"></div>
      <div id="heals"></div>
      <div id="runErr" class="err"></div>
    </div>
    </div>
  </section>

  <section class="right">
    <div class="canvas-head"><div><div class="canvas-title">Medallion pipeline</div><div class="canvas-sub">Bronze &rarr; Silver &rarr; Gold</div></div><span class="tag">Azure Data Factory</span></div>
    <div class="right-inner">
    <div class="pipeline-canvas" aria-label="Bronze to Silver to Gold medallion flow">
      <div class="pipeline-track">
        <div class="flow-node bronze" id="node-bronze"><div class="node-kicker"><span class="node-dot"></span>Raw ingestion</div><strong>Bronze</strong><p>Copy source data without transformation</p><div class="node-status muted" id="status-bronze">Not started</div></div>
        <div class="flow-link"></div>
        <div class="flow-node silver" id="node-silver"><div class="node-kicker"><span class="node-dot"></span>Standardize</div><strong>Silver</strong><p>Clean, validate, deduplicate and enrich</p><div class="node-status muted" id="status-silver">Not started</div></div>
        <div class="flow-link"></div>
        <div class="flow-node gold" id="node-gold"><div class="node-kicker"><span class="node-dot"></span>Serve</div><strong>Gold</strong><p>Aggregate business-ready outputs</p><div class="node-status muted" id="status-gold">Not started</div></div>
      </div>
    </div>
    <h2>Generated implementation plan</h2>
    <div id="summary"></div>
    <div id="planReadable" class="card muted">Generate a plan to see it in plain English.</div>
    <div id="planNotes"></div>
    </div>
  </section>
</main>
</div>

<script>
const $ = (s)=>document.querySelector(s);
let RUN = null, REVIEW = null, POLL = null, UPLOAD = null;

function authHeaders(){ const t = sessionStorage.getItem('api_token'); return t ? {'x-api-token': t} : {}; }
async function jget(u){ const r = await fetch(u); if(!r.ok) throw new Error((await r.json()).detail||r.status); return r.json(); }
async function jpost(u, body){
  let r = await fetch(u,{method:'POST',headers:{'content-type':'application/json',...authHeaders()},body:JSON.stringify(body)});
  if(r.status===401){
    const t = prompt('This server requires an API token (API_TOKEN):');
    if(t){ sessionStorage.setItem('api_token', t);
      r = await fetch(u,{method:'POST',headers:{'content-type':'application/json',...authHeaders()},body:JSON.stringify(body)}); }
  }
  if(!r.ok){ const d=(await r.json()).detail; throw new Error(typeof d==='string'?d:JSON.stringify(d)||r.status); }
  return r.json(); }

setCanvasState('idle');
(async()=>{ try{ const h=await jget('/health');
  const t=$('#modeTag'); if(h.mock){t.textContent='MOCK tenant (no Azure writes)';t.className='tag mock';}
  else{t.textContent='LIVE Azure';t.className='tag live';}
  if(h.self_heal){ $('#healTag').style.display=''; }
}catch(e){} })();

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
  const stop = startTimer('#genBtn','Generating');
  try{
    const fd = new FormData();
    if(UPLOAD){ fd.append('file', UPLOAD); } else { fd.append('brd', brd); }
    // Embedded in the ER app's Pipelines tab: the diagram's share token arrives
    // as ?catalog_source_id=... — pass it so grounding uses the reviewed catalog.
    const csid = new URLSearchParams(location.search).get('catalog_source_id');
    if(csid){ fd.append('catalog_source_id', csid); }
    let r = await fetch('/plan',{method:'POST',headers:authHeaders(),body:fd});
    if(r.status===401){
      const t = prompt('This server requires an API token (API_TOKEN):');
      if(t){ sessionStorage.setItem('api_token', t);
        r = await fetch('/plan',{method:'POST',headers:authHeaders(),body:fd}); }
    }
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
  setJourney('review');
  if(data.status==='NEEDS_CLARIFICATION'){
    renderClar(data.clarifications);
    renderPlan(data);  // show any assumptions the agent already made
    $('#approveBox').style.display='none';
    REVIEW=null; $('#summary').innerHTML='';
    $('#preflight').innerHTML='';
    return;
  }
  // Non-blocking questions: the plan built fine, these are optional to answer.
  if(data.clarifications && data.clarifications.length){
    $('#clar').innerHTML = '<h2>Questions (optional)</h2><div class="card">'+
      'The plan below is complete and approvable. Answer these in the chat if you want it adjusted first:'+
      '<ul>'+data.clarifications.map(i=>'<li>'+esc(i)+'</li>').join('')+'</ul></div>';
  } else { $('#clar').innerHTML=''; }
  // A refine reopens the approval gate — stop any stale live run/poll.
  if(POLL){ clearInterval(POLL); POLL=null; }
  $('#liveBox').style.display='none';
  REVIEW = data.review;
  renderPreflight(data.preflight);
  renderSummary(REVIEW);
  renderPlan(data);
  renderGate(data);
}

// --- readable plan + assumptions/suggestions (agent proposes, you approve) ---
function mdToHtml(md){
  return (md||'').split('\n').map(line=>{
    if(/^## /.test(line)) return '<h3>'+esc(line.slice(3))+'</h3>';
    if(/^# /.test(line))  return '<h2 style="border:0;margin:.3em 0">'+esc(line.slice(2))+'</h2>';
    let t = esc(line).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`(.+?)`/g,'<code>$1</code>');
    if(/^- /.test(line)) return '<div style="margin-left:1em">&bull; '+t.slice(2)+'</div>';
    const num = line.match(/^\s+(\d+)\. (.*)$/);
    if(num) return '<div style="margin-left:2.4em">'+num[1]+'. '+
      esc(num[2]).replace(/`(.+?)`/g,'<code>$1</code>')+'</div>';
    return line.trim()===''? '<div style="height:.4em"></div>' : '<div>'+t+'</div>';
  }).join('');
}
function renderPlan(data){
  if(data.plan_markdown){
    $('#planReadable').innerHTML = mdToHtml(data.plan_markdown);
    $('#planReadable').className = 'card';
  }
  const A = data.assumptions||[], S = data.suggestions||[], C = data.plan_changes||[];
  const RF = data.review_findings||[], AZ = data.azure_target||null;
  let html='';
  if(RF.length) html += '<h2>Reviewer findings (advisory — verify against your BRD)</h2>'+
    '<div class="card" style="border-left:3px solid #e5a50a">'+
    RF.map((f,i)=>'<div class="check"><span class="dot warn"></span><div><b>'+esc(f.severity||'')+
    ':</b> '+esc(f.requirement||'')+' &mdash; '+esc(f.issue||'')+
    ' <a href="#" onclick="fixViaChat('+i+');return false" style="white-space:nowrap">Fix via chat →</a></div></div>').join('')+
    '<div class="muted" style="margin-top:6px">These do not block approval. Click “Fix via chat” to have the agent repair the plan — you send the message, nothing changes without you.</div></div>';
  window._REVIEW_FINDINGS = RF;
  if(AZ) html += '<h2>Deploy target named in the BRD</h2><div class="card" id="azTargetCard">'+
    ['resource_group','factory_name','storage_account'].filter(k=>AZ[k]).map(k=>
      '<div class="check"><span class="dot"></span><div>'+esc(k)+': <code>'+esc(AZ[k])+'</code></div></div>').join('')+
    '<div class="row" style="margin-top:8px"><button class="sec" onclick="applyAzureTarget()">Use this target</button>'+
    '<span class="muted">Nothing is applied until you click — verify these are YOUR resources.</span></div>'+
    '<div id="azTargetState" class="pill"></div></div>';
  window._AZ_TARGET = AZ;
  if(C.length) html += '<h2>What changed since you last reviewed (verify before approving)</h2>'+
    '<div class="card" style="border-left:3px solid #e5a50a">'+
    C.map(c=>'<div class="check"><span class="dot warn"></span><div>'+esc(c)+'</div></div>').join('')+'</div>';
  if(A.length) html += '<details style="margin:8px 0"><summary class="muted" style="cursor:pointer">'+
    A.length+' assumption(s) made — expand to review, change any via chat</summary><div class="card">'+
    A.map(a=>'<div class="check"><span class="dot ok"></span><div>'+esc(a)+'</div></div>').join('')+'</div></details>';
  if(S.length) html += '<h2>Optional suggestions</h2><div class="card">'+
    S.map(s=>'<div class="check"><span class="dot"></span><div>'+esc(s)+'</div></div>').join('')+'</div>';
  $('#planNotes').innerHTML = html;
}

// One click drops a reviewer finding into the chat box as a repair request —
// the user reviews the wording and presses Send; the agent edits the plan in
// place. This is the interactive fix path: agent asks/flags, human decides.
function fixViaChat(i){
  const f = (window._REVIEW_FINDINGS||[])[i]; if(!f) return;
  const box = $('#chatBox'); if(box) box.style.display='';
  const inp = $('#chatInput'); if(!inp) return;
  inp.value = 'Fix this reviewer finding: '+(f.requirement||'')+' — '+(f.issue||'');
  inp.focus();
}

// Explicit user confirmation applies the BRD-named deploy target to the
// server session (POST /azure-config), then runs the read-only connectivity
// test. Never automatic — BRD text must not silently pick a deploy target.
async function applyAzureTarget(){
  const az = window._AZ_TARGET; if(!az) return;
  const st = $('#azTargetState'); st.textContent = 'applying…';
  try{
    const r = await fetch('/azure-config', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({resource_group: az.resource_group||null,
                            factory_name: az.factory_name||null,
                            storage_account: az.storage_account||null})});
    if(!r.ok) throw new Error((await r.json()).detail||r.status);
    let msg = 'applied';
    try{
      const t = await fetch('/azure-config/test', {method:'POST'});
      const tb = await t.json();
      msg += t.ok ? ' — connectivity OK' : (' — test: '+esc(JSON.stringify(tb)));
    }catch(e){ msg += ' — connectivity test unavailable'; }
    st.textContent = msg;
  }catch(e){ st.textContent = 'failed: '+e.message; }
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
  const stop = startTimer('#chatBtn','Working');
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
  setJourney('define'); setCanvasState('idle');
  REVIEW=null; if(POLL){clearInterval(POLL);POLL=null;}
  ['preflight','clar','summary','chatLog','planNotes'].forEach(id=>$('#'+id).innerHTML='');
  $('#planReadable').innerHTML='Generate a plan to see it in plain English.'; $('#planReadable').className='card muted';
  $('#approveBox').style.display='none'; $('#liveBox').style.display='none';
  $('#chatBox').style.display='none'; $('#runErr').textContent='';
}

function renderClar(items){
  $('#clar').innerHTML = '<h2>One thing before I can build</h2><div class="card">'+
    'Answer in the chat below (or edit the description and regenerate):'+
    '<ul>'+items.map(i=>'<li>'+esc(i)+'</li>').join('')+'</ul></div>';
}

function renderPreflight(pf){
  if(pf && pf.passed){
    $('#preflight').innerHTML='';
    return;
  }
  const rows = pf.checks.map(c=>'<div class="check"><span class="dot '+(c.passed?'ok':'bad')+'"></span>'+
     '<div><b>'+esc(c.name)+'</b><div class="muted">'+esc(c.detail||'')+'</div></div></div>').join('');
  $('#preflight').innerHTML='<h2>Pre-flight ('+(pf.passed?'PASS':'FAIL')+')</h2><div class="card">'+rows+'</div>';
}


// Object counts only — to the point, no JSON dumps.
function renderSummary(rev){
  const cats = [['pipelines','pipelines'],['dataflows','data flows'],
                ['datasets','datasets'],['linked_services','linked services'],['triggers','triggers']];
  const pills = cats.map(([k,label])=>{
    const n = (rev[k]||[]).length;
    return n ? '<span class="tag" style="margin-right:6px">'+n+' '+label+'</span>' : '';
  }).join('');
  $('#summary').innerHTML = pills ? '<div style="margin-bottom:8px">'+pills+'</div>' : '';
}

function renderGate(data){
  $('#approveBox').style.display='block';
  setCanvasState(data.preflight.passed ? 'ready' : 'idle');
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

async function approveRun(ack){
  const r = await fetch('/approve',{method:'POST',
    headers:{'content-type':'application/json',...authHeaders()},
    body:JSON.stringify({run_id:RUN, acknowledge_unsupported:!!ack})});
  const data = await r.json();
  if(r.status===409 && data.detail && data.detail.unsupported){
    const msg = 'These BRD requirements were NOT built:\n\n- '
      + data.detail.unsupported.join('\n- ')
      + '\n\nDeploy the pipeline WITHOUT them?';
    if(confirm(msg)) return approveRun(true);
    throw new Error('cancelled — unbuilt requirements not acknowledged');
  }
  if(!r.ok){ const d=data.detail; throw new Error(typeof d==='string'?d:JSON.stringify(d)||r.status); }
  return data;
}

$('#approveBtn').onclick = async ()=>{
  if(!RUN) return;
  $('#approveBtn').disabled=true;
  try{
    await approveRun(false);
    setJourney('deploy');
    $('#liveBox').style.display='block';
    $('#stopBtn').style.display=''; $('#stopBtn').disabled=false; $('#stopBtn').textContent='Stop run';
    POLL = setInterval(poll, 1500); poll();
  }catch(e){ alert('Approve blocked: '+e.message); $('#approveBtn').disabled=false; }
};

$('#stopBtn').onclick = async ()=>{
  if(!RUN) return;
  $('#stopBtn').disabled=true; $('#stopBtn').textContent='Stopping…';
  try{ await jpost('/stop/'+RUN,{}); }
  catch(e){ alert('Stop failed: '+e.message); $('#stopBtn').disabled=false; $('#stopBtn').textContent='Stop run'; }
};

const CAT_LABEL = {linkedServices:'linked services', datasets:'datasets',
                   dataflows:'data flows', pipelines:'pipelines', triggers:'triggers'};

function renderDeployReport(s){
  let html = 'state: '+s.status+
    (s.containers_created? '  •  containers '+JSON.stringify(s.containers_created):'');
  const dr = s.deploy_report;
  if(dr){
    // Intended (this plan) vs actual (what the factory really contains now).
    const rows = Object.keys(CAT_LABEL).map(cat=>{
      const want = (dr.intended_counts||{})[cat];
      const have = dr.factory_counts ? dr.factory_counts[cat] : null;
      if(!want && !have) return '';
      const match = (have==null || have===-1) ? '' : (have===want ? ' ✓' : ' ⚠ factory has '+have);
      return '<div class="pill">'+CAT_LABEL[cat]+': '+(want||0)+' in plan'+match+'</div>';
    }).join('');
    html += '<div style="margin-top:6px">'+rows+'</div>';
    if(dr.pruned && dr.pruned.length){
      html += '<div class="pill">removed '+dr.pruned.length+' stale object(s) from earlier runs</div>';
    }
    if(dr.stale && dr.stale.length){
      html += '<div class="pill" title="'+esc(dr.stale.join(', '))+'">'+dr.stale.length+
        ' stale object(s) from earlier runs left in the factory — the agent never deletes; '+
        'remove them yourself or set PRUNE_STALE=true</div>';
    }
    if(dr.prune_error){
      html += '<div class="warn">Cleanup of old objects failed — stale objects may remain in the factory: '+
              esc(dr.prune_error)+'</div>';
    }
  } else if(s.deployed){
    html += '  •  deployed '+s.deployed.length+' objects';
  }
  $('#deployState').innerHTML = html;
}

async function poll(){
  if(!RUN) return;
  let s; try{ s = await jget('/status/'+RUN); }catch(e){ return; }
  renderDeployReport(s);
  if(s.heals && s.heals.length){
    $('#heals').innerHTML = '<h2>Auto-fixes (self-heal)</h2><div class="card">'+
      s.heals.map(h=>'<div class="check"><span class="dot ok"></span><div><b>'+
        esc(h.category)+'/'+esc(h.name)+'</b><div class="muted">'+esc(h.fix||'')+'</div></div></div>').join('')+
      '<div class="pill">Full before/after audit: artifacts/&lt;run&gt;/heals.json</div></div>';
  }
  // Per-step live status: generic steps when present, medallion layers as fallback.
  let steps = (s.run && s.run.steps) || null;
  if(!steps){
    const layers = (s.run && s.run.layers) || {};
    steps = ['bronze','silver','gold'].map(l=>({name:l.toUpperCase(), ...(layers[l]||{status:'Pending'})}));
  }
  $('#layers').innerHTML = steps.map(d=>
    '<div class="layerbox"><div class="s">'+esc(d.name)+'</div>'+
    '<div class="badge s-'+(d.status||'Pending')+'">'+(d.status||'Pending')+'</div>'+
    (d.run_id?'<div class="pill">run '+esc(d.run_id)+'</div>':'')+
    (d.error?'<div class="err">'+esc(d.error)+'</div>':'')+'</div>').join('');
  paintCanvas(steps);
  // Past self-heal attempts stay visible while the retry runs (and at the end,
  // sourced from the final report), so errors never vanish into the loop.
  let hist = (s.run && s.run.attempt_history) || null;
  if(!hist && s.report && s.report.attempts && s.report.attempts.length > 1)
    hist = s.report.attempts.slice(0, -1);
  if(hist && hist.length){
    $('#attemptLog').innerHTML = '<h2>Previous attempts</h2><div class="card">'+
      hist.map(a=>'<div class="check"><span class="dot bad"></span><div>'+
        '<b>attempt '+esc(a.attempt)+' — '+esc(a.status||'Failed')+'</b>'+
        (a.error?'<div class="err">'+esc(a.error)+'</div>':'')+
        (a.healed?'<div class="muted">healed '+esc(a.healed.category)+'/'+esc(a.healed.name)+
          ': '+esc(a.healed.fix||'')+'</div>':'')+
        '</div></div>').join('')+'</div>';
  }
  if(s.run && s.run.status==='Healing')
    $('#deployState').innerHTML += '  •  <b>self-heal in progress&hellip;</b>';
  if(['SUCCEEDED','FAILED','ERROR','STOPPED'].includes(s.status)){
    clearInterval(POLL); POLL=null;
    $('#stopBtn').style.display='none';
    if(s.status==='STOPPED') $('#runErr').textContent = 'Run stopped by user.';
    if(s.error) $('#runErr').textContent = s.error;
    if(s.report && s.report.attempts){
      const last = s.report.attempts[s.report.attempts.length-1];
      if(last && last.error) $('#runErr').textContent = last.error;
    }
  }
}

function esc(s){ return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function setJourney(step){
  const map={define:'journeyDefine',review:'journeyReview',deploy:'journeyDeploy'};
  Object.values(map).forEach(id=>$('#'+id).classList.remove('is-active'));
  $('#'+map[step]).classList.add('is-active');
}

// Reflect real state on the medallion canvas instead of a static diagram.
// mode 'idle' (nothing built) / 'ready' (plan built, awaiting deploy); a live
// run overrides both with per-layer status from paintCanvas.
const LAYERS = ['bronze','silver','gold'];
function setCanvasState(mode){
  LAYERS.forEach(k=>{
    const node=$('#node-'+k), st=$('#status-'+k); if(!node||!st) return;
    node.classList.remove('active');
    node.classList.toggle('dim', mode==='idle');
    st.className='node-status muted';
    st.textContent = mode==='ready' ? 'Ready to deploy' : 'Not started';
  });
}
function paintCanvas(steps){
  const byLayer={};
  (steps||[]).forEach(d=>{ const n=(d.name||'').toLowerCase();
    LAYERS.forEach(k=>{ if(n.includes(k)) byLayer[k]=d.status||'Pending'; }); });
  LAYERS.forEach(k=>{
    const node=$('#node-'+k), st=$('#status-'+k); if(!node||!st) return;
    const s=byLayer[k]; node.classList.remove('dim'); node.classList.toggle('active', s==='InProgress');
    st.textContent = s || 'Pending'; st.className = 'node-status s-'+(s||'Pending');
  });
}

</script>
</body>
</html>
"""
