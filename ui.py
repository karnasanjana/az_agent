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
  .azin { width:100%; margin:3px 0; background:var(--panel2); color:var(--ink);
          border:1px solid var(--line); border-radius:8px; padding:8px; }
  .warn { color:var(--warn); white-space:pre-wrap; }
</style>
</head>
<body>
<header>
  <h1>BRD &rarr; ADF Agent</h1>
  <span id="modeTag" class="tag">checking&hellip;</span>
  <span id="healTag" class="tag" style="display:none">self-heal ON</span>
  <span id="runTag" class="pill"></span>
</header>
<main>
  <section class="left">
    <h2>0. Azure connection</h2>
    <details id="azBox" class="card" style="padding:0">
      <summary>Deploy target <span id="azSummary" class="pill"></span></summary>
      <div style="padding:10px">
        <div class="muted" style="margin-bottom:8px">Where pipelines get deployed. Saved for this
          server session only — never written into the code.</div>
        <input id="az_subscription_id" class="azin" placeholder="Subscription ID"/>
        <input id="az_resource_group" class="azin" placeholder="Resource group"/>
        <input id="az_factory_name" class="azin" placeholder="Data Factory name"/>
        <input id="az_storage_account" class="azin" placeholder="Storage account name"/>
        <div class="row">
          <select id="az_storage_kind" class="azin" style="flex:1">
            <option value="">storage kind (auto)</option>
            <option value="adls">ADLS Gen2 (hierarchical namespace)</option>
            <option value="blob">Plain Blob storage</option>
          </select>
          <input id="az_location" class="azin" placeholder="Region (e.g. eastus)" style="flex:1"/>
        </div>
        <div class="row">
          <button id="azSaveBtn" class="sec">Save</button>
          <button id="azTestBtn" class="sec">Test connection</button>
        </div>
        <div id="azState" class="pill"></div>
        <div id="azChecks"></div>
      </div>
    </details>

    <h2>1. What do you want to build?</h2>
    <textarea id="brd" placeholder="Describe it in plain English or paste a full BRD &mdash; e.g. &quot;copy the daily sales CSVs from https://... into the lake and aggregate revenue by region&quot;. Or upload a .txt/.md/.pdf."></textarea>
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
    <h2>2. Pipeline graph (click a step)</h2>
    <div id="graph" class="muted">Generate a plan to see the pipeline steps.</div>

    <h2>Node detail</h2>
    <div id="detail" class="card muted">Select a node above.</div>

    <h2>Plan &mdash; what I'll build</h2>
    <div id="planReadable" class="card muted">Generate a plan to see it in plain English.</div>
    <div id="planNotes"></div>

    <h2>3. Governance plan (raw)</h2>
    <details><summary>Show plain-text plan (with JSON)</summary><pre id="planText" class="muted">&mdash;</pre></details>

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
  else{t.textContent='LIVE Azure';t.className='tag live';}
  if(h.self_heal){ $('#healTag').style.display=''; }
}catch(e){} })();

// --- Azure connection panel: read/set the deploy target from the UI ---------
const AZ_FIELDS = ['subscription_id','resource_group','factory_name','storage_account','storage_kind','location'];
function azSummary(cfg){
  const ok = cfg.subscription_id && cfg.resource_group && cfg.factory_name && cfg.storage_account;
  $('#azSummary').textContent = ok ? (cfg.factory_name+' / '+cfg.storage_account) : 'not set — click to configure';
  if(!ok) $('#azBox').open = true;
}
(async()=>{ try{
  const cfg = await jget('/azure-config');
  AZ_FIELDS.forEach(f=>{ const el=$('#az_'+f); if(el && cfg[f]) el.value=cfg[f]; });
  azSummary(cfg);
}catch(e){} })();

$('#azSaveBtn').onclick = async ()=>{
  const body={}; AZ_FIELDS.forEach(f=>{ body[f]=$('#az_'+f).value.trim(); });
  try{
    const cfg = await jpost('/azure-config', body);
    $('#azState').textContent='Saved for this session.'; azSummary(cfg); $('#azChecks').innerHTML='';
  }catch(e){ $('#azState').textContent='Save failed: '+e.message; }
};

$('#azTestBtn').onclick = async ()=>{
  $('#azState').textContent='Testing…'; $('#azChecks').innerHTML='';
  try{
    const r = await jpost('/azure-config/test', {});
    $('#azState').textContent = r.ok ? 'Connection OK.' : 'Connection has problems:';
    $('#azChecks').innerHTML = '<div class="card">'+r.checks.map(c=>
      '<div class="check"><span class="dot '+(c.passed?'ok':'bad')+'"></span><div><b>'+
      esc(c.name)+'</b><div class="muted">'+esc(c.detail||'')+'</div></div></div>').join('')+'</div>';
  }catch(e){ $('#azState').textContent='Test failed: '+e.message; }
};

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
    renderPlan(data);  // show any assumptions the agent already made
    $('#approveBox').style.display='none';
    REVIEW=GRAPH=null; $('#graph').textContent=''; $('#objects').innerHTML='';
    $('#preflight').innerHTML=''; $('#planText').textContent='—';
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
  REVIEW = data.review; GRAPH = data.graph;
  renderPreflight(data.preflight);
  renderGraph(GRAPH); renderObjects(REVIEW);
  $('#planText').textContent=data.plan_text; $('#planText').className='';
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
    return line.trim()===''? '<div style="height:.4em"></div>' : '<div>'+t+'</div>';
  }).join('');
}
function renderPlan(data){
  if(data.plan_markdown){
    $('#planReadable').innerHTML = mdToHtml(data.plan_markdown);
    $('#planReadable').className = 'card';
  }
  const A = data.assumptions||[], S = data.suggestions||[];
  let html='';
  if(A.length) html += '<h2>Assumptions I made (change any via chat)</h2><div class="card">'+
    A.map(a=>'<div class="check"><span class="dot ok"></span><div>'+esc(a)+'</div></div>').join('')+'</div>';
  if(S.length) html += '<h2>Optional suggestions</h2><div class="card">'+
    S.map(s=>'<div class="check"><span class="dot"></span><div>'+esc(s)+'</div></div>').join('')+'</div>';
  $('#planNotes').innerHTML = html;
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
  ['preflight','clar','graph','objects','chatLog','planNotes'].forEach(id=>$('#'+id).innerHTML='');
  $('#detail').innerHTML='Select a node above.'; $('#detail').className='card muted';
  $('#planReadable').innerHTML='Generate a plan to see it in plain English.'; $('#planReadable').className='card muted';
  $('#planText').textContent='—'; $('#approveBox').style.display='none'; $('#liveBox').style.display='none';
  $('#chatBox').style.display='none'; $('#graph').textContent=''; $('#runErr').textContent='';
}

function renderClar(items){
  $('#clar').innerHTML = '<h2>One thing before I can build</h2><div class="card">'+
    'Answer in the chat below (or edit the description and regenerate):'+
    '<ul>'+items.map(i=>'<li>'+esc(i)+'</li>').join('')+'</ul></div>';
}

function renderPreflight(pf){
  const rows = pf.checks.map(c=>'<div class="check"><span class="dot '+(c.passed?'ok':'bad')+'"></span>'+
     '<div><b>'+esc(c.name)+'</b><div class="muted">'+esc(c.detail||'')+'</div></div></div>').join('');
  $('#preflight').innerHTML='<h2>Pre-flight ('+(pf.passed?'PASS':'FAIL')+')</h2><div class="card">'+rows+'</div>';
}

function orderedNodes(g){
  // Topological order from the edges (works for any pipeline shape);
  // falls back to the server's node order for anything unreachable.
  const indeg = {}, next = {};
  g.nodes.forEach(n=>{ indeg[n.id]=0; });
  g.edges.forEach(e=>{ if(e.to in indeg){ indeg[e.to]++; (next[e.from]=next[e.from]||[]).push(e.to); } });
  const queue = g.nodes.filter(n=>indeg[n.id]===0).map(n=>n.id), out=[], seen=new Set();
  while(queue.length){
    const id=queue.shift(); if(seen.has(id)) continue; seen.add(id); out.push(id);
    (next[id]||[]).forEach(t=>{ if(--indeg[t]===0) queue.push(t); });
  }
  g.nodes.forEach(n=>{ if(!seen.has(n.id)) out.push(n.id); });
  return out.map(id=>g.nodes.find(n=>n.id===id));
}

function renderGraph(g){
  if(!g.nodes.length){ $('#graph').textContent='No executable steps found.'; return; }
  const nodes = orderedNodes(g);
  let html='<div class="graph">';
  nodes.forEach((n,i)=>{
    const idx = g.nodes.indexOf(n);
    html += '<div class="node '+(n.layer||'')+'" data-idx="'+idx+'" onclick="selNode('+idx+')">'+
            '<div class="l">'+esc(n.label)+'</div><div class="k">'+esc(n.kind)+'</div>'+
            '<div class="k">'+esc(n.note||'')+'</div></div>';
    if(i<nodes.length-1) html+='<div class="arrow">&rarr;<small>Succeeded</small></div>';
  });
  html+='</div>';
  $('#graph').innerHTML=html;
}

function selNode(idx){
  document.querySelectorAll('.node').forEach(n=>n.classList.toggle('sel', n.dataset.idx==idx));
  const n = GRAPH.nodes[idx];
  if(!n) return;
  let h = '<div><b>'+esc(n.label)+'</b> &mdash; '+esc(n.kind)+'</div>'+
          '<div class="muted">object: '+esc(n.object||'')+' &nbsp; source: '+esc(n.source_dataset||'-')+
          ' &rarr; sink: '+esc(n.sink_dataset||'-')+'</div>';
  if(n.layer==='bronze'){ h+='<div class="pill">raw landing, no transformation &mdash; no script (correct)</div>'; }
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
