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
.dnc{color:#b3261e;font-weight:700;font-size:10.5px}
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
function escA(s){return esc(s).replace(/"/g,'&quot;')}
'''

DIRECTOR_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CRM — Director</title><style>__CSS__
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:14px}
.stat{background:#fff;border:1px solid #e3e8ef;border-radius:12px;padding:10px 14px;text-align:center}
.stat .n{font-size:22px;font-weight:800}.stat .l{font-size:11px;color:#6b7788;text-transform:uppercase;letter-spacing:.4px}
.preset{border:1.5px solid #cbd5e1;background:#fff;border-radius:10px;padding:10px 14px;cursor:pointer;font-size:13px;text-align:left}
.preset b{display:block;font-size:13.5px}.preset span{font-size:11.5px;color:#6b7788}
.preset.on{border-color:#2563eb;background:#eef4ff;box-shadow:0 0 0 2px #2563eb22}
.presets{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:10px}
.adv{display:none;border-top:1px dashed #e3e8ef;margin-top:10px;padding-top:8px}
.adv.open{display:block}
.linky{background:none;border:none;color:#2563eb;font-size:12px;cursor:pointer;text-decoration:underline;padding:0}
.tabs{display:flex;gap:0;border-bottom:2px solid #e3e8ef;margin-bottom:12px;flex-wrap:wrap}
.tab{padding:8px 16px;cursor:pointer;font-weight:600;font-size:13px;color:#6b7788;border-bottom:2px solid transparent;margin-bottom:-2px}
.tab.on{color:#1d4ed8;border-bottom-color:#2563eb}
.bigassign{font-size:15px;padding:12px 26px}
.prevrows{font-size:12.5px;margin-top:8px}.prevrows td{padding:3px 10px 3px 0}
.stepnum{display:inline-flex;width:22px;height:22px;border-radius:50%;background:#101828;color:#fff;font-size:12px;font-weight:700;align-items:center;justify-content:center;margin-right:8px}
.piebar{display:flex;height:34px;border-radius:10px;overflow:hidden;border:1px solid #e3e8ef;cursor:pointer}
.piebar div{display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;min-width:2px;white-space:nowrap;overflow:hidden}
.pieleg{display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;font-size:12px}
.pieleg span{cursor:pointer}.pieleg b{font-size:13px}
.dotc{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;vertical-align:-1px}
.advcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin-top:10px}
.advcard{border:1px solid #e3e8ef;border-radius:10px;padding:10px 14px;background:#fafbfc}
.advcard b{font-size:14px}.advcard .row2{display:flex;gap:12px;font-size:12px;margin-top:6px;flex-wrap:wrap}
.advcard .kpi{text-align:center}.advcard .kpi b{font-size:16px;display:block}
.mtable{width:100%;font-size:12.5px}.mtable th{cursor:pointer;user-select:none;white-space:nowrap}
.mtable td{white-space:nowrap;max-width:220px;overflow:hidden;text-overflow:ellipsis}
.mrowx{cursor:pointer}.mrowx:hover{background:#f1f5f9}
.mdetail{background:#fafbfc;border:1px solid #e3e8ef;border-radius:8px;padding:10px 14px;margin:6px 0}
.pager2{display:flex;gap:10px;align-items:center;margin-top:8px}
</style></head><body>
<header><h1>🎖 Director</h1><span class="sp"></span><span class="me">__ME__</span></header>
<div class="wrap">
<div class="stats" id="stats"></div>
<div class="panel"><h3>📊 The pie <span class="muted" style="font-size:11px">whole eligible base — click a slice to see those members</span></h3>
 <div class="piebar" id="piebar"></div><div class="pieleg" id="pieleg"></div>
 <div class="advcards" id="advcards"></div></div>
<div class="panel"><h3><span class="stepnum">1</span>Who should we call?</h3>
 <div class="presets" id="presets"></div>
 <div id="filters" style="display:none">
  <div class="row"><span class="lbl">Qualified for</span><span id="quals"></span></div>
  <div class="row"><span class="lbl">Last connection</span><span class="seg" id="lcSeg"></span></div>
  <div class="row"><span class="lbl">Attempts since conn</span><span class="seg" id="asSeg"></span>
    <span class="lbl" style="min-width:auto">Total conn</span><span class="seg" id="tcSeg"></span></div>
  <div class="row"><span class="lbl">Age</span><span class="seg" id="ageSeg"></span>
    <span class="lbl" style="min-width:auto">State</span><input id="state" style="width:64px" placeholder="FL">
    <label class="chip" id="noflags" onclick="tg(this);pv()">No screening flags</label>
    <label class="chip" id="never" onclick="tg(this);pv()">Never attempted</label></div>
 </div>
 <button class="linky" id="toggleFilters">⚙ fine-tune filters</button>
 <div class="row" style="margin-top:10px"><span class="pcount" id="pcount">—</span><span class="muted">members ready (not in an open batch)</span>
  <button class="sec" id="peek">👀 preview first 10</button></div>
 <div id="prevrows" class="prevrows"></div>
</div>
<div class="panel"><h3><span class="stepnum">2</span>Assign a batch</h3>
 <div class="row">
  <input id="bname" style="width:220px">
  <select id="bsize"><option>10</option><option selected>25</option><option>50</option><option>100</option></select>
  <span class="lbl" style="min-width:auto">to</span><select id="badv"></select>
  <button class="good bigassign" onclick="createBatch()">Assign batch ➜</button></div>
 <div class="row"><input id="bscript" style="flex:1" placeholder="optional note shown on every card (the approved guides load automatically)"></div>
 <button class="linky" onclick="$('advadd').classList.toggle('open')">+ add a new advocate</button>
 <div class="adv" id="advadd"><div class="row"><input id="uemail" placeholder="advocate@parkinsons.community"><input id="udisp" placeholder="display name" style="width:130px">
  <button onclick="addUser()">Save advocate</button><span class="muted">they also need IAP access (see runbook)</span></div></div>
</div>
<div class="panel"><h3><span class="stepnum">3</span>Track</h3>
 <div class="tabs" id="tabs"></div>
 <div id="tabbody"></div>
</div>
</div><div class="toast" id="toast"></div>
<script>__JSC__
const QUALS=['Apokyn','Onapgo Qualified','Onapgo','Inbrija','Gocovri','Dyskinesia','N317 trial','IPX203 trial','OFF signals'];
const LC=[['any','Any'],['never','Never'],['6m','< 6 mo'],['1y','6–12 mo'],['2y','1–2 yr'],['old','2 yr +']];
const ASB=[['0','0'],['12','1–2'],['35','3–5'],['6p','6 +']];
const TC=[['any','Any'],['0','0'],['1','1'],['2p','2 +']];
const AGES=[['<50','< 50'],['50','50s'],['60','60s'],['70','70s'],['80','80 +'],['unk','?']];
let lcSel='any',tcSel='any',asSel=new Set(),ageSel=new Set(),qInc=new Set(),qExc=new Set();
const PRESETS=[
 {id:'fresh',name:'🎯 Fresh Onapgo prospects',desc:'Qualified (Onapgo/Apokyn), never attempted, no screening flags',
  set:()=>{qInc=new Set(['Onapgo Qualified','Apokyn']);$('never').classList.add('on');$('noflags').classList.add('on');}},
 {id:'warm',name:'📞 Follow-up: reached before',desc:'Connected in the past, quiet for 2+ years, OFF signals',
  set:()=>{qInc=new Set(['OFF signals']);tcSel='2p';lcSel='old';}},
 {id:'sweep',name:'🔁 Second-pass sweep',desc:'1–2 gentle attempts so far, never connected',
  set:()=>{asSel=new Set(['12']);tcSel='0';}},
 {id:'custom',name:'⚙ Custom',desc:'Start blank and fine-tune everything yourself',set:()=>{}}];
function clearFilters(){lcSel='any';tcSel='any';asSel=new Set();ageSel=new Set();qInc=new Set();qExc=new Set();
 $('state').value='';$('never').classList.remove('on');$('noflags').classList.remove('on');}
$('presets').innerHTML=PRESETS.map(p=>`<button class="preset" data-p="${p.id}"><b>${p.name}</b><span>${p.desc}</span></button>`).join('');
$('presets').addEventListener('click',e=>{const b=e.target.closest('[data-p]');if(!b)return;
 document.querySelectorAll('.preset').forEach(x=>x.classList.toggle('on',x===b));
 clearFilters();PRESETS.find(p=>p.id===b.dataset.p).set();drawSegs();drawQuals();
 $('filters').style.display=b.dataset.p==='custom'?'':'none';autoname();pv();});
function segHTML(id,buckets,cur,multi){$(id).innerHTML=buckets.map(b=>`<button data-b="${b[0]}" class="${(multi?cur.has(b[0]):cur===b[0])?'on':''}">${b[1]}</button>`).join('');}
function drawSegs(){segHTML('lcSeg',LC,lcSel,false);segHTML('asSeg',ASB,asSel,true);segHTML('tcSeg',TC,tcSel,false);segHTML('ageSeg',AGES,ageSel,true);}
function drawQuals(){document.querySelectorAll('#quals .chip').forEach(ch=>{const q=ch.dataset.q;
 ch.classList.toggle('inc',qInc.has(q));ch.classList.toggle('exc',qExc.has(q));});}
['lcSeg','tcSeg'].forEach(id=>$(id).addEventListener('click',e=>{const b=e.target.closest('[data-b]');if(!b)return;
 if(id==='lcSeg')lcSel=b.dataset.b;else tcSel=b.dataset.b;drawSegs();pv();}));
['asSeg','ageSeg'].forEach(id=>$(id).addEventListener('click',e=>{const b=e.target.closest('[data-b]');if(!b)return;
 const set=id==='asSeg'?asSel:ageSel;const k=b.dataset.b;set.has(k)?set.delete(k):set.add(k);drawSegs();pv();}));
$('quals').innerHTML=QUALS.map(q=>`<label class="chip" data-q="${q}">${q} <span class="n" data-qc="${q}"></span></label>`).join('');
$('quals').addEventListener('click',e=>{const ch=e.target.closest('[data-q]');if(!ch)return;const q=ch.dataset.q;
 if(qInc.has(q)){qInc.delete(q);qExc.add(q);}else if(qExc.has(q)){qExc.delete(q);}else{qInc.add(q);}drawQuals();autoname();pv();});
$('toggleFilters').addEventListener('click',()=>{const f=$('filters');f.style.display=f.style.display==='none'?'':'none';});
function tg(el){el.classList.toggle('on')}
function filters(){return{qual_inc:[...qInc],qual_exc:[...qExc],lc:lcSel,tc:tcSel,att_since:[...asSel],ages:[...ageSel],
 never_attempted:$('never').classList.contains('on'),exclude_flags:$('noflags').classList.contains('on'),state:$('state').value};}
function autoname(){const p=document.querySelector('.preset.on');const base=p&&p.dataset.p!=='custom'?p.querySelector('b').textContent.replace(/^[^ ]+ /,'').split(':')[0].replace(/\s+/g,'-'):([...qInc][0]||'Batch');
 $('bname').value=(base+'-'+new Date().toISOString().slice(5,10)).replace(/[^\w-]+/g,'');}
let pvT=null;
function pv(){clearTimeout(pvT);$('prevrows').innerHTML='';pvT=setTimeout(async()=>{const r=await api('/api/dir/preview',{method:'POST',body:JSON.stringify(filters())});$('pcount').textContent=r.count.toLocaleString();},250);}
$('state').addEventListener('input',()=>pv());
$('peek').addEventListener('click',async()=>{const r=await api('/api/dir/preview_rows',{method:'POST',body:JSON.stringify(filters())});
 $('prevrows').innerHTML='<table>'+r.rows.map(x=>`<tr><td><b>${esc(x.first)} ${esc(x.last)}</b></td><td>${x.age??''}</td><td>${esc(x.state)}</td><td>${esc((x.quals||'').split(';').slice(0,3).join(', '))}</td><td class="muted">${x.last_conn?('last conn '+x.last_conn):'never connected'} · ${x.att} att</td></tr>`).join('')+'</table>';});
async function createBatch(){const f=filters();f.name=$('bname').value;f.size=$('bsize').value;f.advocate=$('badv').value;f.script=$('bscript').value;
 if(!f.advocate){toast('Pick or add an advocate first');return;}
 const r=await api('/api/dir/batch',{method:'POST',body:JSON.stringify(f)});toast('✅ Batch #'+r.batch_id+' → '+f.advocate+' ('+r.assigned+' members)');openTab('batches');loadStats();loadPie();pv();}
async function addUser(){await api('/api/dir/user',{method:'POST',body:JSON.stringify({email:$('uemail').value,display:$('udisp').value})});toast('advocate saved');loadUsers();}
async function loadStats(){const s=await api('/api/dir/stats');
 $('stats').innerHTML=[['Ready to call',s.eligible-s.in_batch],['In open batches',s.in_batch],['Worked today',s.worked_today],['Connected today',s.connected_today],['Callbacks due now',s.callbacks_due]]
 .map(x=>`<div class="stat"><div class="n">${(+x[1]).toLocaleString()}</div><div class="l">${x[0]}</div></div>`).join('');}
async function loadUsers(){const us=await api('/api/dir/users');
 $('badv').innerHTML=us.filter(x=>x.role==='advocate'&&x.active).map(x=>`<option value="${x.email}">${esc(x.display)}</option>`).join('')||'<option value="">— no advocates yet: add one below —</option>';
 return us;}
const TABS=[['members','Members'],['batches','Batches'],['funnel','Funnel'],['answers','Answers'],['scripts','Scripts'],['flags','Integrity'],['team','Team'],['audit','Audit']];
$('tabs').innerHTML=TABS.map((t,i)=>`<div class="tab ${i==0?'on':''}" data-t="${t[0]}">${t[1]}</div>`).join('');
$('tabs').addEventListener('click',e=>{const t=e.target.closest('[data-t]');if(t)openTab(t.dataset.t);});
const PIE_COLORS={available:'#94a3b8',in_progress:'#2563eb',completed:'#16a34a',missed:'#d97706',other_done:'#7c3aed'};
const PIE_LABELS={available:'On the table',in_progress:'On plates now',completed:'Eaten — completed',missed:'Eaten — missed/unreached',other_done:'Eaten — other'};
const PIE_AVAIL={available:'available',in_progress:'assigned',completed:'worked',missed:'worked',other_done:'worked'};
async function loadPie(){const p=await api('/api/dir/pie');
 const keys=['available','in_progress','completed','missed','other_done'];
 const tot=Math.max(1,p.eligible);
 $('piebar').innerHTML=keys.map(k=>{const v=p[k]||0;const w=(v/tot*100);
  return v?`<div style="background:${PIE_COLORS[k]};width:${Math.max(w,1.5)}%" title="${PIE_LABELS[k]}: ${v.toLocaleString()}" data-k="${k}">${w>7?v.toLocaleString():''}</div>`:'';}).join('');
 $('pieleg').innerHTML=keys.map(k=>`<span data-k="${k}"><i class="dotc" style="background:${PIE_COLORS[k]}"></i>${PIE_LABELS[k]} <b>${(p[k]||0).toLocaleString()}</b></span>`).join('')+
  `<span class="muted">· eligible ${p.eligible.toLocaleString()} · refused/DQ ${p.refused_dq.toLocaleString()} · no phone ${p.no_phone.toLocaleString()}</span>`;
 const go=e=>{const el=e.target.closest('[data-k]');if(!el)return;mAvail=PIE_AVAIL[el.dataset.k]||'all';mPage=0;openTab('members');};
 $('piebar').onclick=go;$('pieleg').onclick=go;
 const ad=await api('/api/dir/advocates');
 $('advcards').innerHTML=ad.length?ad.map(a=>`<div class="advcard"><b>${esc(a.display)}</b> <span class="muted" style="font-size:11px">${esc(a.email)}</span>
  <div class="row2"><span class="kpi"><b>${a.pending+a.served}</b>on plate</span><span class="kpi"><b>${a.callbacks}</b>callbacks</span>
  <span class="kpi"><b style="color:${a.due_now?'#b3261e':'inherit'}">${a.due_now}</b>due now</span>
  <span class="kpi"><b>${a.today}</b>today</span><span class="kpi"><b>${a.worked_total}</b>eaten</span>
  <span class="kpi"><b>${a.worked_total?Math.round(a.connected_total/a.worked_total*100):0}%</b>connect</span></div>
  <div class="muted" style="font-size:11px;margin-top:4px">last activity: ${a.last_activity?a.last_activity.slice(5,16):'—'}</div></div>`).join(''):'<span class="muted">No advocates enrolled yet.</span>';}
let mAvail='all',mPage=0,mSort='name',mDir='asc',mQ='';
async function loadMembers(){const B=$('tabbody');
 const body={...filters(),avail:mAvail,q:mQ,sort:mSort,dir:mDir,page:mPage};
 const r=await api('/api/dir/members',{method:'POST',body:JSON.stringify(body)});
 const TH=[['name','Member'],['age','Age'],['state','St'],['conn','Conn'],['att','Att'],['last_conn','Last conn'],['att_since','Att since']];
 B.innerHTML=`<div class="row"><input id="mq" placeholder="search name or ID…" value="${escA(mQ)}" style="width:200px">
  <select id="mavail">${[['all','Everyone'],['available','Available to batch'],['assigned','On a plate (open batch)'],['worked','Worked (has dispositions)'],['untouched','Never touched']].map(o=>`<option value="${o[0]}" ${o[0]===mAvail?'selected':''}>${o[1]}</option>`).join('')}</select>
  <span class="muted">${r.total.toLocaleString()} members · filters from step 1 apply · page ${r.page+1} of ${Math.max(1,Math.ceil(r.total/50))}</span></div>
  <table class="mtable"><tr>${TH.map(t=>`<th data-s="${t[0]}">${t[1]}${mSort===t[0]?(mDir==='asc'?' ▲':' ▼'):''}</th>`).join('')}<th>Quals</th><th>Advocate</th><th>Stage</th><th>Last disposition</th></tr>
  ${r.rows.map(x=>`<tr class="mrowx" data-mid="${x.member_id}"><td><b>${esc(x.first)} ${esc(x.last)}</b></td><td>${x.age??''}</td><td>${esc(x.state)}</td>
   <td>${x.conn}</td><td>${x.att}</td><td>${x.last_conn||'<span class=muted>never</span>'}</td><td>${x.att_since}</td>
   <td>${(x.quals||'').split(';').filter(Boolean).slice(0,3).map(q=>`<span class="qtag">${esc(q)}</span>`).join('')}</td>
   <td>${x.advocate?esc(x.advocate.split('@')[0]):'<span class=muted>—</span>'}</td><td>${x.stage||''}</td><td>${esc(x.last_disp||'')}</td></tr><tr style="display:none" data-d="${x.member_id}"><td colspan="11"></td></tr>`).join('')}</table>
  <div class="pager2"><button class="sec" id="mprev" ${r.page==0?'disabled':''}>‹ Prev</button><button class="sec" id="mnext" ${(r.page+1)*50>=r.total?'disabled':''}>Next ›</button></div>`;
 $('mq').addEventListener('change',e=>{mQ=e.target.value;mPage=0;loadMembers();});
 $('mavail').addEventListener('change',e=>{mAvail=e.target.value;mPage=0;loadMembers();});
 $('mprev').onclick=()=>{mPage--;loadMembers();};$('mnext').onclick=()=>{mPage++;loadMembers();};
 B.querySelectorAll('th[data-s]').forEach(th=>th.addEventListener('click',()=>{const s=th.dataset.s;
  if(mSort===s)mDir=mDir==='asc'?'desc':'asc';else{mSort=s;mDir='asc';}loadMembers();}));
 B.querySelectorAll('.mrowx').forEach(tr=>tr.addEventListener('click',async()=>{const mid=tr.dataset.mid;
  const drow=B.querySelector(`tr[data-d="${mid}"]`);const cell=drow.firstElementChild;
  if(drow.style.display!=='none'){drow.style.display='none';return;}
  drow.style.display='';cell.innerHTML='<span class="muted">loading…</span>';
  const d=await api('/api/dir/member/'+mid);
  cell.innerHTML=`<div class="mdetail"><b>${esc(d.member.first)} ${esc(d.member.last)}</b> · ${d.member.age??''} · ${esc(d.member.city||'')} ${esc(d.member.state)} · phone ${esc(d.member.phone)} · Dr ${esc(d.member.doctor||'—')}
   <div style="margin:4px 0">${(d.member.quals||'').split(';').filter(Boolean).map(q=>`<span class="qtag">${esc(q)}</span>`).join('')} ${(d.member.sflags||'').split(';').filter(Boolean).map(f=>`<span class="sflag">${esc(f)}</span>`).join('')}</div>
   ${d.batches.length?'<div class="lbl">Batches</div>'+d.batches.map(b=>`<div style="font-size:12px">#${b.id} ${esc(b.name)} → ${esc(b.advocate)} · ${b.state}/${b.stage||''} ${b.callback_at?'· next: '+b.callback_at.slice(0,16):''} ${b.hcp_date?'· HCP '+b.hcp_date:''}</div>`).join(''):''}
   ${d.answers.length?'<div class="lbl" style="margin-top:6px">Guide answers</div>'+d.answers.slice(0,8).map(a=>`<div style="font-size:12px"><span class="muted">${a.ts.slice(5,16)} ${a.stage}</span> ${esc(a.prompt.slice(0,50))} → <b>${esc(a.answer)}</b></div>`).join(''):''}
   <div class="lbl" style="margin-top:6px">History</div>${d.hist.map(h=>`<div style="font-size:12px"><span class="dot ${h.cls}">${h.cls==='C'?'●':h.cls==='A'?'○':h.cls==='B'?'✖':'·'}</span> <span class="muted">${h.date||'—'}</span> ${esc(h.event_type)} — ${esc((h.detail||'').slice(0,90))}</div>`).join('')}</div>`;}));}
async function openTab(k){document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.t===k));const B=$('tabbody');B.innerHTML='<span class="muted">loading…</span>';
 if(k==='members'){await loadMembers();return;}
 if(k==='batches'){const bs=await api('/api/dir/batches');
  B.innerHTML=bs.length?'<table><tr><th>#</th><th>Name</th><th>Advocate</th><th>Done</th><th>Callbacks</th><th>Status</th><th></th></tr>'+bs.map(b=>`<tr><td>${b.id}</td><td>${esc(b.name)}</td><td>${esc(b.advocate)}</td><td>${b.done||0}/${b.total}</td><td>${b.callbacks||0}</td><td>${b.status}</td><td><button class="sec" onclick="batchDetail(${b.id})">detail</button> ${b.status==='open'?`<button class="bad" onclick="closeB(${b.id})">close</button>`:''}</td></tr>`).join('')+'</table><div id="bdetail"></div>':'<span class="muted">No batches yet — build one above. It lands here with live progress.</span>';}
 else if(k==='funnel'){const f=await api('/api/dir/funnel');const st={};f.forEach(r=>{st[r.stage]=st[r.stage]||{};st[r.stage][r.state]=r.n});
  const stages=['initial','pre_hcp','post_hcp','complete','missed_post','no_appt','dq'];
  B.innerHTML='<table><tr><th>Stage</th><th>Pending</th><th>Callback set</th><th>Done</th></tr>'+stages.map(sg=>{const x=st[sg]||{};return `<tr><td><b>${sg.replace('_',' ')}</b></td><td>${x.pending||0}</td><td>${x.callback||0}</td><td>${x.done||0}</td></tr>`}).join('')+'</table>';}
 else if(k==='answers'){const a=await api('/api/dir/answers');
  B.innerHTML=a.length?'<div style="max-height:340px;overflow-y:auto"><table>'+a.map(x=>`<tr><td class="muted">${x.ts.slice(5,16)}</td><td><b>${esc(x.first)} ${esc(x.last)}</b></td><td>${x.stage}</td><td>${esc(x.prompt.slice(0,60))}</td><td><b>${esc(x.answer)}</b></td></tr>`).join('')+'</table></div>':'<span class="muted">Discussion-guide answers appear here the moment an advocate saves a connected call.</span>';}
 else if(k==='scripts'){const S=await api('/api/dir/scripts');window._SCR=S;
  B.innerHTML='<p class="muted">These are the PRC/MLR-approved texts advocates read and record on connected calls. Edit carefully — wording is compliance-approved.</p>'+
  S.scripts.map(sc=>`<div class="row"><span class="lbl">${sc.stage}</span><input data-st="${sc.stage}" data-f="title" value="${escA(sc.title)}" style="flex:1"></div>
   <textarea data-st="${sc.stage}" data-f="body" style="width:100%;height:70px;font:12px monospace">${esc(sc.body)}</textarea>`).join('')+
  '<h4 style="margin-top:10px">Guide items (scripted lines, instructions, questions)</h4><div style="max-height:320px;overflow-y:auto">'+
  S.questions.map(q=>`<div class="row"><span class="muted" style="width:86px">${q.stage} · ${q.kind}</span>
   <input data-qid="${q.id}" data-f="prompt" value="${escA(q.prompt)}" style="flex:1">
   ${q.kind==='q'?`<select data-qid="${q.id}" data-f="qtype">${['radio','check','date','text'].map(t=>`<option ${t===q.qtype?'selected':''}>${t}</option>`).join('')}</select>
   <input data-qid="${q.id}" data-f="options" value="${escA(q.options||'')}" placeholder="options a|b|c" style="width:150px">`:''}</div>`).join('')+
  '</div><div class="row"><button class="good" onclick="saveScripts()">Save scripts & guide</button></div>';}
 else if(k==='flags'){const f=await api('/api/dir/flags');
  const sec=(t,rows,cols)=>rows.length?`<h4>${t} (${rows.length})</h4><table><tr>${cols.map(c=>'<th>'+c+'</th>').join('')}</tr>`+rows.map(r=>'<tr>'+cols.map(c=>'<td>'+esc(r[c])+'</td>').join('')+'</tr>').join('')+'</table>':'';
  B.innerHTML=(sec('Dispositions faster than 20s',f.fast_dispositions,['ts','actor','member_id','disposition','handle_secs'])+
  sec('“Connected” under 60s after dialing',f.connected_too_fast,['ts','actor','member_id','disposition','secs_after_click'])+
  sec('Disposition without any call/text click',f.disposition_without_any_click,['ts','actor','member_id','disposition']))||'<span class="muted">No integrity flags — clean so far 🎉</span>';}
 else if(k==='team'){const us=await loadUsers();
  B.innerHTML='<table>'+us.map(x=>`<tr><td>${esc(x.email)}</td><td>${x.role}</td><td>${esc(x.display)}</td><td>${x.active?'active':'disabled'}</td></tr>`).join('')+'</table><p class="muted">Add advocates in step 2. They also need IAP access on the Cloud Run service.</p>';}
 else if(k==='audit'){const a=await api('/api/dir/audit');
  B.innerHTML='<div style="max-height:340px;overflow-y:auto"><table>'+a.map(x=>`<tr><td class="muted">${x.ts.slice(5,16)}</td><td>${esc(x.actor)}</td><td>${esc(x.action)}</td><td>${esc(x.member_id||'')}</td><td class="muted">${esc((x.meta||'').slice(0,80))}</td></tr>`).join('')+'</table></div>';}}
async function saveScripts(){const S=window._SCR;if(!S)return;
 const scripts=S.scripts.map(sc=>({stage:sc.stage,
  title:document.querySelector(`input[data-st="${sc.stage}"][data-f="title"]`).value,
  body:document.querySelector(`textarea[data-st="${sc.stage}"][data-f="body"]`).value}));
 const questions=S.questions.map(q=>({id:q.id,seq:q.seq,
  prompt:document.querySelector(`input[data-qid="${q.id}"][data-f="prompt"]`).value,
  qtype:q.kind==='q'?document.querySelector(`select[data-qid="${q.id}"][data-f="qtype"]`).value:q.qtype,
  options:q.kind==='q'?document.querySelector(`input[data-qid="${q.id}"][data-f="options"]`).value:(q.options||'')}));
 await api('/api/dir/scripts',{method:'POST',body:JSON.stringify({scripts,questions})});toast('scripts & guide saved');}
async function batchDetail(id){const d=await api('/api/dir/batch/'+id);
 $('bdetail').innerHTML='<h4 style="margin-top:12px">Batch '+id+'</h4><div>'+d.summary.map(s=>`<span class="qtag">${esc(s.disposition)}: ${s.n}</span>`).join(' ')+'</div>'+
 (d.left&&d.left.length?'<div class="lbl" style="margin-top:8px">Left on the table ('+d.left.length+')</div><div style="font-size:12px;max-height:140px;overflow-y:auto">'+d.left.map(x=>`${esc(x.first)} ${esc(x.last)} (${esc(x.state)}) — ${x.bstate}${x.stage?'/'+x.stage:''}${x.callback_at?' · due '+x.callback_at.slice(0,16):''}`).join('<br>')+'</div>':'<div class="muted" style="margin-top:8px">Nothing left — plate clean.</div>')+
 '<table><tr><th>When</th><th>Who</th><th>Member</th><th>Disposition</th><th>Note</th><th>s</th></tr>'+
 d.dispositions.map(x=>`<tr><td class="muted">${x.ts.slice(5,16)}</td><td>${esc(x.actor)}</td><td>${esc(x.first)} ${esc(x.last)}</td><td>${esc(x.disposition)}</td><td>${esc((x.note||'').slice(0,60))}</td><td>${x.handle_secs?Math.round(x.handle_secs):''}</td></tr>`).join('')+'</table>';}
async function closeB(id){if(!confirm('Close this batch?'))return;await api('/api/dir/close_batch/'+id,{method:'POST'});openTab('batches');loadStats();}
api('/api/dir/qual_counts',{method:'POST',body:'{}'}).then(cs=>{for(const q in cs){const el=document.querySelector(`[data-qc="${q}"]`);if(el)el.textContent=cs[q].toLocaleString();}});
drawSegs();loadStats();loadUsers();loadPie();openTab('members');
document.querySelector('[data-p="fresh"]').click();
</script></body></html>"""
DIRECTOR_HTML = DIRECTOR_HTML.replace('__CSS__', CSS).replace('__JSC__', JS_COMMON)

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
