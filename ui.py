CSS = '''
*{box-sizing:border-box}body{margin:0;font:14px/1.5 'Segoe UI',system-ui,sans-serif;background:#f4f6f9;color:#1e2733}
header{background:#101828;color:#fff;padding:10px 20px;display:flex;gap:12px;align-items:center}
header h1{font-size:15px;margin:0}.sp{flex:1}.me{font-size:12px;color:#94a3b8}
.wrap{max-width:880px;margin:16px auto;padding:0 14px}
.panel{background:#fff;border:1px solid #e3e8ef;border-radius:12px;padding:16px 18px;margin-bottom:14px;box-shadow:0 1px 3px #0001}
h3{margin:0 0 10px;font-size:14px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:8px 0}
.lbl{font-size:11px;font-weight:700;color:#667;text-transform:uppercase;letter-spacing:.5px;min-width:120px}
input,select{padding:6px 9px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:13px}
button{background:#101828;color:#fff;border:none;border-radius:8px;padding:8px 14px;font-size:13px;font-weight:600;cursor:pointer}
button.sec{background:#fff;color:#334155;border:1.5px solid #cbd5e1}
button.good{background:#16a34a}button.warn{background:#d97706}button.bad{background:#b3261e}
button:disabled{opacity:.45;cursor:default}
.chip{display:inline-block;font-size:11.5px;font-weight:600;padding:3px 10px;border-radius:10px;border:1.5px solid #94a3b8;background:#fff;cursor:pointer;margin:2px 3px 2px 0}
.chip.on{border-color:#2563eb;background:#eef4ff;color:#1d4ed8}
.qtag{display:inline-block;font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:8px;background:#eef4ff;color:#1d4ed8;border:1px solid #c7d8fb;margin:1px 3px 1px 0}
.sflag{display:inline-block;font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:8px;background:#fff;color:#b45309;border:1px solid #d97706;margin-right:4px}
.big{font-size:22px;font-weight:800}.muted{color:#6b7788;font-size:12px}
table{border-collapse:collapse;width:100%;font-size:12.5px}td,th{border-bottom:1px solid #e3e8ef;padding:6px 8px;text-align:left}
.dot{font-weight:800}.C{color:#0b6e4f}.A{color:#b8860b}.B{color:#b3261e}
.hist{max-height:210px;overflow-y:auto;font-size:12px;border:1px solid #e3e8ef;border-radius:8px;padding:6px 10px;background:#fafbfc}
.callbtn{font-size:16px;padding:14px 26px;border-radius:12px}
.dgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px;margin-top:10px}
.toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:#101828;color:#fff;padding:10px 16px;border-radius:8px;font-size:13px;opacity:0;transition:.3s;pointer-events:none}
.toast.on{opacity:1}
.seg{display:inline-flex;border:1.5px solid #cbd5e1;border-radius:9px;overflow:hidden;background:#fff}
.seg button{border:none;background:#fff;padding:6px 12px;font-size:12.5px;cursor:pointer;border-right:1px solid #e2e8f0;color:#334155}
.seg button:last-child{border-right:none}.seg button:hover{background:#f1f5f9}.seg button.on{background:#2563eb;color:#fff}
.chip.inc{border-color:#16a34a!important;background:#e8f7ee!important;color:#0a5c2e!important}
.chip.exc{border-color:#dc2626!important;background:#fdeceb!important;color:#b3261e!important;text-decoration:line-through}
.chip .n{color:#94a3b8;font-weight:500;font-size:10px}
.pcount{font-size:16px;font-weight:800;color:#1d4ed8;background:#eef4ff;border:1px solid #c7d8fb;border-radius:8px;padding:4px 14px}
'''
JS_COMMON = '''
const $=id=>document.getElementById(id);
const qs=new URLSearchParams(location.search); const AS=qs.get('as')?('?as='+qs.get('as')):'';
async function api(path,opts){const r=await fetch(path+AS,Object.assign({headers:{'Content-Type':'application/json'}},opts));
 if(!r.ok){const t=await r.text();toast('Error: '+t.slice(0,120));throw new Error(t);}return r.json();}
function toast(t){const el=$('toast');el.textContent=t;el.classList.add('on');setTimeout(()=>el.classList.remove('on'),2500);}
function esc(s){return String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
'''

DIRECTOR_HTML = '''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CRM — Director</title><style>'''+CSS+'''</style></head><body>
<header><h1>🎖 Director Console</h1><span class="sp"></span><span class="me">__ME__</span></header>
<div class="wrap">
<div class="panel"><h3>1 · Build a batch <span class="muted" style="font-size:11px">chips: 1× 🟢 include · 2× 🔴 exclude · 3× clear</span></h3>
 <div class="row"><span class="lbl">Qualified for</span><span id="quals"></span></div>
 <div class="row"><span class="lbl">Last connection</span><span class="seg" id="lcSeg"></span></div>
 <div class="row"><span class="lbl">Attempts since conn</span><span class="seg" id="asSeg"></span><span class="muted" style="font-size:11px">pick any</span>
   <span class="lbl" style="min-width:auto">Total conn</span><span class="seg" id="tcSeg"></span></div>
 <div class="row"><span class="lbl">Age</span><span class="seg" id="ageSeg"></span>
   <span class="lbl" style="min-width:auto">State</span><input id="state" style="width:64px" placeholder="FL">
   <label class="chip" id="noflags" onclick="tg(this);pv()">No screening flags</label>
   <label class="chip" id="never" onclick="tg(this);pv()">Never attempted</label></div>
 <div class="row"><span class="pcount" id="pcount">—</span><span class="muted">members match &amp; are not in an open batch (live)</span></div>
 <div class="row"><span class="lbl">Batch</span><input id="bname" placeholder="name e.g. Onapgo-FL-July">
   <input id="bsize" type="number" value="25" style="width:70px" title="size"><select id="badv"></select>
   <button class="good" onclick="createBatch()">Assign batch</button></div>
 <div class="row"><span class="lbl">Script hint</span><input id="bscript" style="flex:1" placeholder="extra note shown on every card of this batch (guides load automatically by stage)"></div>
</div>
<div class="panel"><h3>2 · Batches & progress</h3><div id="batches"></div><div id="bdetail"></div></div>
<div class="panel"><h3>3 · Program funnel <span class="muted">Initial → Pre-HCP → Post-HCP (open batches)</span></h3>
 <button class="sec" onclick="loadFunnel()">Refresh</button><div id="funnel"></div>
 <h3 style="margin-top:14px">Latest discussion-guide answers</h3><button class="sec" onclick="loadAnswers()">Refresh</button><div id="answers" style="max-height:280px;overflow-y:auto"></div></div>
<div class="panel"><h3>3b · Scripts & guide editor <span class="muted">what advocates read on connect</span></h3>
 <button class="sec" onclick="loadScripts()">Load</button><div id="scripts"></div></div>
<div class="panel"><h3>4 · Integrity flags</h3><button class="sec" onclick="loadFlags()">Refresh flags</button><div id="flags"></div></div>
<div class="panel"><h3>5 · Team</h3><div id="users"></div>
 <div class="row"><input id="uemail" placeholder="advocate@yourorg.com"><input id="udisp" placeholder="display name" style="width:130px">
 <button onclick="addUser()">Add / update advocate</button></div></div>
<div class="panel"><h3>6 · Audit trail (latest 300)</h3><button class="sec" onclick="loadAudit()">Load</button><div id="audit" style="max-height:300px;overflow-y:auto"></div></div>
</div><div class="toast" id="toast"></div>
<script>'''+JS_COMMON+'''
const QUALS=['Apokyn','Onapgo Qualified','Onapgo','Inbrija','Gocovri','Dyskinesia','N317 trial','IPX203 trial','OFF signals'];
const LC=[['any','Any'],['never','Never'],['6m','< 6 mo'],['1y','6–12 mo'],['2y','1–2 yr'],['old','2 yr +']];
const ASB=[['0','0'],['12','1–2'],['35','3–5'],['6p','6 +']];
const TC=[['any','Any'],['0','0'],['1','1'],['2p','2 +']];
const AGES=[['<50','< 50'],['50','50s'],['60','60s'],['70','70s'],['80','80 +'],['unk','?']];
let lcSel='any',tcSel='any',asSel=new Set(),ageSel=new Set(),qInc=new Set(),qExc=new Set();
function seg(id,buckets,single){$(id).innerHTML=buckets.map(b=>`<button data-b="${b[0]}" class="${(single&&b[0]==='any')?'on':''}">${b[1]}</button>`).join('');
 $(id).addEventListener('click',e=>{const b=e.target.closest('[data-b]');if(!b)return;const k=b.dataset.b;
  if(single){if(id==='lcSeg')lcSel=k;else tcSel=k;$(id).querySelectorAll('button').forEach(x=>x.classList.toggle('on',x.dataset.b===k));}
  else{const set=id==='asSeg'?asSel:ageSel;if(set.has(k)){set.delete(k);b.classList.remove('on');}else{set.add(k);b.classList.add('on');}}
  pv();});}
seg('lcSeg',LC,true);seg('asSeg',ASB,false);seg('tcSeg',TC,true);seg('ageSeg',AGES,false);
$('quals').innerHTML=QUALS.map(q=>`<label class="chip" data-q="${q}">${q} <span class="n" data-qc="${q}"></span></label>`).join('');
$('quals').addEventListener('click',e=>{const ch=e.target.closest('[data-q]');if(!ch)return;const q=ch.dataset.q;
 if(qInc.has(q)){qInc.delete(q);qExc.add(q);ch.classList.remove('inc');ch.classList.add('exc');}
 else if(qExc.has(q)){qExc.delete(q);ch.classList.remove('exc');}
 else{qInc.add(q);ch.classList.add('inc');}pv();});
api('/api/dir/qual_counts',{method:'POST',body:'{}'}).then(cs=>{for(const q in cs){const el=document.querySelector(`[data-qc="${q}"]`);if(el)el.textContent=cs[q].toLocaleString();}});
function tg(el){el.classList.toggle('on')}
function filters(){return{qual_inc:[...qInc],qual_exc:[...qExc],lc:lcSel,tc:tcSel,att_since:[...asSel],ages:[...ageSel],
 never_attempted:$('never').classList.contains('on'),exclude_flags:$('noflags').classList.contains('on'),
 state:$('state').value};}
let pvT=null;
function pv(){clearTimeout(pvT);pvT=setTimeout(async()=>{const r=await api('/api/dir/preview',{method:'POST',body:JSON.stringify(filters())});$('pcount').textContent=r.count.toLocaleString();},250);}
$('state').addEventListener('input',pv);pv();
async function createBatch(){const f=filters();f.name=$('bname').value;f.size=$('bsize').value;f.advocate=$('badv').value;f.script=$('bscript').value;
 const r=await api('/api/dir/batch',{method:'POST',body:JSON.stringify(f)});toast('Batch #'+r.batch_id+' assigned ('+r.assigned+' members)');loadBatches();pv();}
async function loadBatches(){const bs=await api('/api/dir/batches');
 $('batches').innerHTML='<table><tr><th>#</th><th>Name</th><th>Advocate</th><th>Progress</th><th>Callbacks</th><th>Status</th><th></th></tr>'+
 bs.map(b=>`<tr><td>${b.id}</td><td>${esc(b.name)}</td><td>${esc(b.advocate)}</td><td>${b.done||0}/${b.total}</td><td>${b.callbacks||0}</td><td>${b.status}</td>
 <td><button class="sec" onclick="detail(${b.id})">detail</button> ${b.status==='open'?`<button class="bad" onclick="closeB(${b.id})">close</button>`:''}</td></tr>`).join('')+'</table>';}
async function detail(id){const d=await api('/api/dir/batch/'+id);
 $('bdetail').innerHTML='<h3 style="margin-top:12px">Batch '+id+'</h3><div>'+d.summary.map(s=>`<span class="qtag">${esc(s.disposition)}: ${s.n}</span>`).join(' ')+'</div>'+
 '<table><tr><th>When</th><th>Who</th><th>Member</th><th>Disposition</th><th>Note</th><th>Handle s</th></tr>'+
 d.dispositions.map(x=>`<tr><td>${x.ts}</td><td>${esc(x.actor)}</td><td>${esc(x.first)} ${esc(x.last)}</td><td>${esc(x.disposition)}</td><td>${esc(x.note)}</td><td>${x.handle_secs?Math.round(x.handle_secs):''}</td></tr>`).join('')+'</table>';}
async function closeB(id){await api('/api/dir/close_batch/'+id,{method:'POST'});loadBatches();}
async function loadFlags(){const f=await api('/api/dir/flags');
 const sec=(t,rows,cols)=>rows.length?`<h3 style="margin-top:10px">${t} (${rows.length})</h3><table><tr>${cols.map(c=>'<th>'+c+'</th>').join('')}</tr>`+rows.map(r=>'<tr>'+cols.map(c=>'<td>'+esc(r[c])+'</td>').join('')+'</tr>').join('')+'</table>':'';
 $('flags').innerHTML=(sec('Dispositions faster than 20s',f.fast_dispositions,['ts','actor','member_id','disposition','handle_secs'])+
 sec('“Connected” under 60s after dialing',f.connected_too_fast,['ts','actor','member_id','disposition','secs_after_click'])+
 sec('Disposition without any call/text click',f.disposition_without_any_click,['ts','actor','member_id','disposition']))||'<span class="muted">no flags 🎉</span>';}
async function addUser(){await api('/api/dir/user',{method:'POST',body:JSON.stringify({email:$('uemail').value,display:$('udisp').value})});toast('saved');loadUsers();}
async function loadFunnel(){const f=await api('/api/dir/funnel');
 const st={};f.forEach(r=>{st[r.stage]=st[r.stage]||{};st[r.stage][r.state]=r.n});
 const stages=['initial','pre_hcp','post_hcp','complete','missed_post','no_appt','dq'];
 $('funnel').innerHTML='<table><tr><th>Stage</th><th>Pending</th><th>Callback set</th><th>Done</th></tr>'+stages.map(sg=>{const x=st[sg]||{};
  return `<tr><td><b>${sg.replace('_',' ')}</b></td><td>${x.pending||0}</td><td>${x.callback||0}</td><td>${x.done||0}</td></tr>`}).join('')+'</table>';}
async function loadAnswers(){const a=await api('/api/dir/answers');
 $('answers').innerHTML='<table>'+a.map(x=>`<tr><td>${x.ts}</td><td>${esc(x.first)} ${esc(x.last)}</td><td>${x.stage}</td><td>${esc(x.prompt)}</td><td><b>${esc(x.answer)}</b></td></tr>`).join('')+'</table>'||'none yet';}
let SCR=null;
async function loadScripts(){SCR=await api('/api/dir/scripts');
 $('scripts').innerHTML=SCR.scripts.map(sc=>`<div class="row"><span class="lbl">${sc.stage}</span></div>
  <input data-st="${sc.stage}" data-f="title" value="${esc(sc.title)}" style="width:220px">
  <textarea data-st="${sc.stage}" data-f="body" style="width:100%;height:90px;font:12.5px monospace">${esc(sc.body)}</textarea>`).join('')+
 '<h3 style="margin-top:10px">Guide prompts</h3>'+SCR.questions.map(q=>`<div class="row"><span class="muted" style="width:60px">${q.stage}</span>
  <input data-qid="${q.id}" data-f="prompt" value="${esc(q.prompt)}" style="flex:1">
  <select data-qid="${q.id}" data-f="qtype">${['text','yesno','choice','hcp_date'].map(t=>`<option ${t===q.qtype?'selected':''}>${t}</option>`).join('')}</select>
  <input data-qid="${q.id}" data-f="options" value="${esc(q.options||'')}" placeholder="choice options a|b|c" style="width:170px"></div>`).join('')+
 '<div class="row"><button class="good" onclick="saveScripts()">Save scripts & prompts</button></div>';}
async function saveScripts(){
 const scripts=SCR.scripts.map(sc=>({stage:sc.stage,
  title:document.querySelector(`input[data-st="${sc.stage}"][data-f="title"]`).value,
  body:document.querySelector(`textarea[data-st="${sc.stage}"][data-f="body"]`).value}));
 const questions=SCR.questions.map(q=>({id:q.id,seq:q.seq,
  prompt:document.querySelector(`input[data-qid="${q.id}"][data-f="prompt"]`).value,
  qtype:document.querySelector(`select[data-qid="${q.id}"][data-f="qtype"]`).value,
  options:document.querySelector(`input[data-qid="${q.id}"][data-f="options"]`).value}));
 await api('/api/dir/scripts',{method:'POST',body:JSON.stringify({scripts,questions})});toast('scripts saved');}
async function loadUsers(){const us=await api('/api/dir/users');
 $('users').innerHTML='<table>'+us.map(x=>`<tr><td>${esc(x.email)}</td><td>${x.role}</td><td>${esc(x.display)}</td><td>${x.active?'active':'disabled'}</td></tr>`).join('')+'</table>';
 $('badv').innerHTML=us.filter(x=>x.role==='advocate'&&x.active).map(x=>`<option value="${x.email}">${esc(x.display)}</option>`).join('')||'<option value="">— add an advocate below —</option>';}
async function loadAudit(){const a=await api('/api/dir/audit');
 $('audit').innerHTML='<table>'+a.map(x=>`<tr><td>${x.ts}</td><td>${esc(x.actor)}</td><td>${esc(x.action)}</td><td>${esc(x.member_id||'')}</td><td>${esc(x.meta)}</td></tr>`).join('')+'</table>';}
loadUsers();loadBatches();
</script></body></html>'''

ADVOCATE_HTML = '''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CRM — My Queue</title><style>'''+CSS+'''</style></head><body>
<header><h1>📞 My Queue</h1><span class="sp"></span><span class="me" id="tally"></span><span class="me">__ME__</span></header>
<div class="wrap"><div id="card" class="panel">Loading…</div></div>
<div class="toast" id="toast"></div>
<script>'''+JS_COMMON+'''
let M=null;
const DISP=['Connected — Educated','Connected — Callback Scheduled','Connected — Not Interested','Left Voicemail','No Answer','Bad Number','Refused / Remove','DQ — Clinical','Deceased','Skipped'];
async function tally(){const s=await api('/api/adv/summary');$('tally').textContent=`today: ${s.today} worked · ${s.connected} connected`;}
async function next(){M=await api('/api/adv/next');
 if(M.empty){$('card').innerHTML='<div class="big">Queue empty 🎉</div><div class="muted">No pending members or due callbacks. Check back later.</div>';return;}
 M.call_click_at=null;M.text_click_at=null;
 $('card').innerHTML=`
 <div class="muted">${esc(M.batch)} · ${M.remaining} left after this one · <b style="color:#2563eb">${esc(M.stage_title)}</b>${(M.stage==='pre_hcp'||M.stage==='post_hcp')?` — attempt <b>${M.stage_attempt} of ${M.max_attempts}</b>`:''}${M.hcp_date?` · HCP appt: <b>${M.hcp_date}</b>`:''}</div>
 <div class="big">${esc(M.first)} ${esc(M.last)} <span class="muted" style="font-size:13px">${M.age??''} ${M.city?'· '+esc(M.city):''} ${esc(M.state)}</span></div>
 <div style="margin:6px 0">${(M.quals||'').split(';').filter(Boolean).map(q=>`<span class="qtag">${esc(q)}</span>`).join('')}
   ${(M.sflags||'').split(';').filter(Boolean).map(f=>`<span class="sflag">${esc(f)} — verify</span>`).join('')}</div>
 <div class="muted">Doctor: ${esc(M.doctor)||'—'}${M.clinic?' · '+esc(M.clinic):''} · Last connection: <b>${M.last_conn||'never'}</b> · Attempts since: <b>${M.att_since}</b> (${M.conn}/${M.att} lifetime)</div>
 <div class="panel" style="background:#fffbe6;border-color:#fde68a;margin:10px 0;padding:10px 14px;white-space:pre-wrap">📋 <b>${esc(M.stage_title)} script</b><br>${esc(M.stage_script)}${M.script?'<br><i>'+esc(M.script)+'</i>':''}</div>
 <div class="row" style="margin:14px 0">
  <button class="good callbtn" onclick="go('call')">📞 Call ····${esc(M.phone_last4)}</button>
  <button class="callbtn" style="background:#2563eb" onclick="go('text')">💬 Text</button></div>
 <div class="lbl">History</div>
 <div class="hist">${(M.hist||[]).map(h=>`<div><span class="dot ${h.cls}">${h.cls==='C'?'●':h.cls==='A'?'○':h.cls==='B'?'✖':'·'}</span> <span class="muted">${h.date||'—'}</span> ${esc(h.event_type)} — ${esc(h.detail)}</div>`).join('')||'<span class="muted">fresh — no prior events</span>'}</div>
 <div class="row" style="margin-top:12px"><button class="good" style="font-size:15px;padding:10px 20px" onclick="openGuide()">🟢 Connected — open discussion guide</button></div>
 <div id="guide" style="display:none"></div>
 <div class="lbl" style="margin-top:12px">No-connect disposition</div>
 <div class="dgrid">${DISP.filter(d=>!d.startsWith('Connected — Educated')).map(d=>`<button class="sec" onclick="disp('${d}')">${d}</button>`).join('')}</div>
 <div class="row"><input id="note" placeholder="note (required for Skipped)" style="flex:1">
   <input id="cbat" type="datetime-local" title="callback time"></div>`;
}
function openGuide(){const g=$('guide');g.style.display='';
 const byseq={};M.guide.forEach(it=>byseq[it.seq]=it);
 g.innerHTML=`<div class="panel" style="border-color:#16a34a;background:#f7fdf9;margin-top:10px"><div class="lbl">${esc(M.stage_title)} — read scripted lines verbatim, record answers</div>`+
 M.guide.map(it=>{
  let inner='';
  if(it.kind==='say')inner=`<div style="white-space:pre-wrap;margin:9px 0;padding:8px 12px;background:#fff;border-left:3px solid #2563eb;border-radius:4px">${esc(it.text)}</div>`;
  else if(it.kind==='instr')inner=`<div style="margin:7px 0;font-size:12px;color:#7c3aed">⚙ ${esc(it.text)}</div>`;
  else{let inp='';
   if(it.qtype==='radio')inp=`<select data-qid="${it.id}" data-seq="${it.seq}" onchange="reeval()"><option value=""></option>${it.options.split('|').map(o=>`<option>${esc(o)}</option>`).join('')}</select>`;
   else if(it.qtype==='check')inp=it.options.split('|').map(o=>`<label style="display:block;font-size:12.5px"><input type="checkbox" data-qid="${it.id}" data-seq="${it.seq}" value="${escA(o)}" onchange="reeval()"> ${esc(o)}</label>`).join('');
   else if(it.qtype==='date')inp=`<input type="date" data-qid="${it.id}" data-seq="${it.seq}" onchange="reeval()">`;
   else inp=`<textarea data-qid="${it.id}" data-seq="${it.seq}" style="width:100%;height:44px"></textarea>`;
   inner=`<div style="margin:9px 0"><div style="font-weight:600">${esc(it.text)}${it.sched==='hcp'?' <span class="muted">(drives call scheduling)</span>':''}${it.dq_vals?' <span class="dnc">contraindication check</span>':''}</div>${inp}</div>`;}
  return `<div class="gitem" data-gseq="${it.seq}" data-show="${escA(it.show_qid||'')}" data-showvals="${escA(it.show_vals||'')}">${inner}</div>`;
 }).join('')+`<div class="row"><button class="good" onclick="submitGuide()">Save answers & schedule next call</button>
 <button class="sec" onclick="$('guide').style.display='none'">cancel</button></div></div>`;
 reeval();g.scrollIntoView({behavior:'smooth'});}
function answerOf(seq){
 const els=[...document.querySelectorAll(`#guide [data-seq="${seq}"]`)];if(!els.length)return '';
 if(els[0].type==='checkbox')return els.filter(e=>e.checked).map(e=>e.value).join('; ');
 return els[0].value||'';}
function reeval(){document.querySelectorAll('#guide .gitem').forEach(el=>{
 const ctrl=el.dataset.show;if(!ctrl)return;
 const want=el.dataset.showvals.split('|');const got=answerOf(ctrl);
 el.style.display=(got&&want.some(w=>got.includes(w)))?'':'none';});}
async function submitGuide(){
 const seen=new Set();const answers=[];
 document.querySelectorAll('#guide .gitem').forEach(el=>{if(el.style.display==='none')return;
  const q=el.querySelector('[data-qid]');if(!q)return;const qid=+q.dataset.qid;if(seen.has(qid))return;seen.add(qid);
  const v=answerOf(q.dataset.seq);if(v)answers.push({qid,answer:v});});
 if(!answers.length){toast('Record at least one answer');return;}
 const r=await api('/api/adv/guide_submit',{method:'POST',body:JSON.stringify({member_id:M.member_id,answers,served_at:M.served_at,call_click_at:M.call_click_at,text_click_at:M.text_click_at})});
 toast('Saved — '+r.outcome);tally();next();}
async function go(kind){const r=await api('/api/adv/click',{method:'POST',body:JSON.stringify({member_id:M.member_id,kind})});
 if(kind==='call')M.call_click_at=r.ts;else M.text_click_at=r.ts;
 window.open(kind==='call'?M.call_url:M.text_url,'gv');}
async function disp(d){const body={member_id:M.member_id,disposition:d,note:$('note').value,served_at:M.served_at,
 call_click_at:M.call_click_at,text_click_at:M.text_click_at,callback_at:$('cbat').value||null};
 await api('/api/adv/disposition',{method:'POST',body:JSON.stringify(body)});toast(d+' logged');tally();next();}
tally();next();
</script></body></html>'''
