CSS = r'''
:root{
 /* type */
 --font:'Segoe UI',system-ui,-apple-system,Roboto,sans-serif;
 --fs-2xs:10.5px;--fs-xs:11.5px;--fs-sm:12.5px;--fs-base:14px;--fs-md:15px;--fs-lg:16px;--fs-2xl:22px;
 --lh:1.5;--lh-tight:1.25;--fw:400;--fw-med:600;--fw-bold:700;--fw-heavy:800;--tracking:.5px;
 /* neutrals — single (cool slate) temperature */
 --ink:#1e293b;--ink-2:#334155;--muted:#64748b;--faint:#94a3b8;
 --line:#e2e8f0;--line-2:#cbd5e1;
 --bg:#f4f6f9;--surface:#ffffff;--surface-2:#f8fafc;--header:#0f172a;
 /* brand (accent = blue, program CTAs) */
 --brand:#2563eb;--brand-ink:#1d4ed8;--brand-weak:#eef4ff;--brand-border:#c7d8fb;
 /* semantic — fixed set */
 --good:#16a34a;--good-ink:#0a5c2e;--good-weak:#e8f7ee;
 --warn:#b45309;--warn-weak:#fffbeb;--warn-border:#fde68a;
 --bad:#dc2626;--bad-ink:#b91c1c;--bad-weak:#fdeceb;
 /* spacing rhythm (4/8) */
 --s1:4px;--s2:8px;--s3:12px;--s4:16px;--s5:24px;--s6:32px;
 /* radii */
 --r-sm:6px;--r:8px;--r-md:10px;--r-lg:12px;--r-pill:999px;
 /* elevation + focus */
 --sh-1:0 1px 3px rgba(15,23,42,.08);--sh-2:0 4px 12px rgba(15,23,42,.10);
 --ring:0 0 0 3px rgba(37,99,235,.40);
 --tap:40px;--tap-lg:44px;
}
*{box-sizing:border-box}
body{margin:0;font:var(--fw) var(--fs-base)/var(--lh) var(--font);background:var(--bg);color:var(--ink)}
:focus-visible{outline:2px solid var(--brand);outline-offset:2px;border-radius:var(--r-sm)}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important;scroll-behavior:auto!important}}
header{background:var(--header);color:#fff;padding:var(--s3) var(--s5);display:flex;gap:var(--s3);align-items:center}
header h1{font-size:var(--fs-md);font-weight:var(--fw-bold);margin:0}
header a:focus-visible{outline-color:#fff}
.sp{flex:1}.me{font-size:var(--fs-sm);color:var(--faint)}
.wrap{max-width:880px;margin:var(--s4) auto;padding:0 var(--s4)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:var(--s4);margin-bottom:var(--s4);box-shadow:var(--sh-1)}
h3{margin:0 0 var(--s3);font-size:var(--fs-base);font-weight:var(--fw-bold)}
h4{margin:var(--s3) 0 var(--s2);font-size:var(--fs-sm);font-weight:var(--fw-bold)}
.row{display:flex;gap:var(--s3);flex-wrap:wrap;align-items:center;margin:var(--s2) 0}
.lbl{font-size:var(--fs-xs);font-weight:var(--fw-bold);color:var(--muted);text-transform:uppercase;letter-spacing:var(--tracking);min-width:120px}
.big{font-size:var(--fs-2xl);font-weight:var(--fw-heavy)}
.muted{color:var(--muted);font-size:var(--fs-sm)}
/* fields — one height/radius/border/placeholder */
input,select,textarea{font:var(--fw) var(--fs-sm)/1.3 var(--font);color:var(--ink);padding:0 10px;height:36px;border:1.5px solid var(--line-2);border-radius:var(--r);background:var(--surface)}
textarea{height:auto;padding:8px 10px;resize:vertical}
input::placeholder,textarea::placeholder{color:var(--faint)}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--brand);box-shadow:var(--ring)}
/* buttons — primary/secondary/tertiary + all states */
button{min-height:var(--tap);background:var(--header);color:#fff;border:1.5px solid var(--header);border-radius:var(--r);padding:0 var(--s4);font:var(--fw-med) var(--fs-sm)/1 var(--font);cursor:pointer;transition:filter .12s,background .12s,box-shadow .12s}
button:hover{filter:brightness(1.12)}button:active{filter:brightness(.94)}
button:disabled{opacity:.45;cursor:not-allowed;filter:none}
button.sec{background:var(--surface);color:var(--ink-2);border-color:var(--line-2)}
button.sec:hover{background:var(--surface-2);filter:none}
button.good{background:var(--good);border-color:var(--good)}
button.warn{background:var(--warn);border-color:var(--warn)}
button.bad{background:var(--bad);border-color:var(--bad)}
button.link,.linky{min-height:0;background:none;border:none;color:var(--brand);font:var(--fw-med) var(--fs-sm) var(--font);cursor:pointer;text-decoration:underline;padding:0}
.callbtn,.bigassign{min-height:var(--tap-lg);font-size:var(--fs-md);padding:0 var(--s5);border-radius:var(--r-lg)}
/* chips */
.chip{display:inline-flex;align-items:center;min-height:28px;font-size:var(--fs-xs);font-weight:var(--fw-med);padding:3px 10px;border-radius:var(--r-pill);border:1.5px solid var(--faint);background:var(--surface);color:var(--ink-2);cursor:pointer;margin:2px 3px 2px 0}
.chip.on{border-color:var(--brand);background:var(--brand-weak);color:var(--brand-ink)}
.chip.inc{border-color:var(--good);background:var(--good-weak);color:var(--good-ink)}
.chip.exc{border-color:var(--bad);background:var(--bad-weak);color:var(--bad-ink);text-decoration:line-through}
.chip .n{color:var(--muted);font-weight:var(--fw);font-size:var(--fs-2xs);margin-left:4px}
.qtag{display:inline-block;font-size:var(--fs-2xs);font-weight:var(--fw-med);padding:1px 7px;border-radius:var(--r);background:var(--brand-weak);color:var(--brand-ink);border:1px solid var(--brand-border);margin:1px 3px 1px 0}
.sflag{display:inline-block;font-size:var(--fs-2xs);font-weight:var(--fw-med);padding:1px 7px;border-radius:var(--r);background:var(--warn-weak);color:var(--warn);border:1px solid var(--warn-border);margin-right:4px}
.dnc,.due{color:var(--bad);font-weight:var(--fw-bold);font-size:var(--fs-2xs)}
.due{font-size:var(--fs-sm)}
.pcount{font-size:var(--fs-lg);font-weight:var(--fw-heavy);color:var(--brand-ink);background:var(--brand-weak);border:1px solid var(--brand-border);border-radius:var(--r);padding:var(--s1) var(--s4)}
/* tables */
table,.sheet,.mtable{border-collapse:collapse;width:100%;font-size:var(--fs-sm)}
td,th,.sheet td,.sheet th{border-bottom:1px solid var(--line);padding:6px var(--s2);text-align:left}
th,.sheet th,.mtable th{font-weight:var(--fw-bold);color:var(--ink-2);white-space:nowrap}
.mtable th{cursor:pointer;user-select:none}.mtable td{white-space:nowrap;max-width:220px;overflow:hidden;text-overflow:ellipsis}
.sheet td{white-space:nowrap;max-width:200px;overflow:hidden;text-overflow:ellipsis}
.mrowx,.sheet tr.rowx{cursor:pointer}.mrowx:hover,.sheet tr.rowx:hover{background:var(--surface-2)}
.dot{font-weight:var(--fw-heavy)}.C{color:var(--good)}.A{color:var(--warn)}.B{color:var(--bad)}
.hist{max-height:210px;overflow-y:auto;font-size:var(--fs-sm);border:1px solid var(--line);border-radius:var(--r);padding:var(--s2) var(--s3);background:var(--surface-2)}
.dgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:var(--s2);margin-top:var(--s2)}
.mdetail,.drawer{background:var(--surface-2);border:1px solid var(--line);border-radius:var(--r-md);padding:var(--s3) var(--s4);margin:6px 0}
/* toast */
.toast{position:fixed;bottom:var(--s5);left:50%;transform:translateX(-50%);background:var(--header);color:#fff;padding:var(--s3) var(--s4);border-radius:var(--r);font-size:var(--fs-sm);opacity:0;transition:opacity .3s;pointer-events:none;max-width:80%;box-shadow:var(--sh-2);z-index:20}
.toast.on{opacity:1}
/* segmented control */
.seg{display:inline-flex;border:1.5px solid var(--line-2);border-radius:var(--r-md);overflow:hidden;background:var(--surface)}
.seg button{min-height:34px;border:none;border-right:1px solid var(--line);border-radius:0;background:var(--surface);padding:0 var(--s3);font-size:var(--fs-sm);color:var(--ink-2)}
.seg button:last-child{border-right:none}.seg button:hover{background:var(--surface-2);filter:none}.seg button.on{background:var(--brand);color:#fff}
/* tabs (shared) */
.tabs{display:flex;gap:0;border-bottom:2px solid var(--line);margin-bottom:var(--s3);flex-wrap:wrap}
.tab{padding:var(--s2) var(--s4);cursor:pointer;font-weight:var(--fw-med);font-size:var(--fs-sm);color:var(--muted);border-bottom:2px solid transparent;margin-bottom:-2px}
.tab.on{color:var(--brand-ink);border-bottom-color:var(--brand)}.tab .n{font-size:var(--fs-xs);color:var(--faint)}
.pager2{display:flex;gap:var(--s3);align-items:center;margin-top:var(--s2)}
/* director: stat cards */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:var(--s3);margin-bottom:var(--s4)}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:var(--s3) var(--s4);text-align:center}
.stat .n{font-size:var(--fs-2xl);font-weight:var(--fw-heavy)}.stat .l{font-size:var(--fs-xs);color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
/* director: presets */
.presets{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:var(--s3);margin-bottom:var(--s3)}
.preset{border:1.5px solid var(--line-2);background:var(--surface);border-radius:var(--r-md);padding:var(--s3) var(--s4);cursor:pointer;font-size:var(--fs-sm);text-align:left;min-height:var(--tap)}
.preset b{display:block;font-size:var(--fs-sm);font-weight:var(--fw-bold)}.preset span{font-size:var(--fs-xs);color:var(--muted)}
.preset.on{border-color:var(--brand);background:var(--brand-weak);box-shadow:0 0 0 2px rgba(37,99,235,.13)}
.adv{display:none;border-top:1px dashed var(--line);margin-top:var(--s3);padding-top:var(--s2)}.adv.open{display:block}
.stepnum{display:inline-flex;width:22px;height:22px;border-radius:var(--r-pill);background:var(--header);color:#fff;font-size:var(--fs-sm);font-weight:var(--fw-bold);align-items:center;justify-content:center;margin-right:var(--s2)}
.prevrows{font-size:var(--fs-sm);margin-top:var(--s2)}.prevrows td{padding:3px var(--s3) 3px 0}
/* director: pie + advocate cards */
.piebar{display:flex;height:34px;border-radius:var(--r-md);overflow:hidden;border:1px solid var(--line);cursor:pointer}
.piebar div{display:flex;align-items:center;justify-content:center;font-size:var(--fs-xs);font-weight:var(--fw-bold);color:#fff;min-width:2px;white-space:nowrap;overflow:hidden}
.pieleg{display:flex;gap:var(--s3);flex-wrap:wrap;margin-top:var(--s2);font-size:var(--fs-sm)}
.pieleg span{cursor:pointer}.pieleg b{font-size:var(--fs-sm)}
.dotc{display:inline-block;width:10px;height:10px;border-radius:var(--r-sm);margin-right:var(--s1);vertical-align:-1px}
.advcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:var(--s3);margin-top:var(--s3)}
.advcard{border:1px solid var(--line);border-radius:var(--r-md);padding:var(--s3) var(--s4);background:var(--surface-2)}
.advcard b{font-size:var(--fs-base);font-weight:var(--fw-bold)}.advcard .row2{display:flex;gap:var(--s3);font-size:var(--fs-sm);margin-top:6px;flex-wrap:wrap}
.advcard .kpi{text-align:center}.advcard .kpi b{font-size:var(--fs-lg);display:block}
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
<title>CRM — Director</title><style>__CSS__</style></head><body>
<header><h1>🎖 Director</h1><a href="/dashboard" target="_blank" style="margin-left:14px;color:#93c5fd;font-size:13px;font-weight:600;text-decoration:none">🗂 Full Review Dashboard ↗</a><span class="sp"></span><span class="me">__ME__</span></header>
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
  <div class="pager2"><button class="sec" id="mprev" aria-label="Previous page" ${r.page==0?'disabled':''}>‹ Prev</button><button class="sec" id="mnext" aria-label="Next page" ${(r.page+1)*50>=r.total?'disabled':''}>Next ›</button></div>`;
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
  B.innerHTML=bs.length?'<table><tr><th>#</th><th>Name</th><th>Advocate</th><th>Done</th><th>Callbacks</th><th>Status</th><th></th></tr>'+bs.map(b=>`<tr><td>${b.id}</td><td>${esc(b.name)}</td><td>${esc(b.advocate)}</td><td>${b.done||0}/${b.total}</td><td>${b.callbacks||0}</td><td>${b.status}</td><td><button class="sec" onclick="batchDetail(${b.id})">detail</button> ${b.status==='open'?`<button class="bad" onclick="closeB(${b.id})">close</button>`:''}</td></tr>`).join('')+'</table><div id="bdetail"></div>':'<span class="muted">No batches yet — build one above, or import a batch CSV exported from your Review Dashboard.</span>';
  B.innerHTML+=`<div class="row" style="margin-top:10px;border-top:1px dashed #e3e8ef;padding-top:8px">
   <span class="lbl">Import dashboard batch CSV</span><input type="file" id="bcsv" accept=".csv">
   <select id="bcsvadv"></select><button class="sec" onclick="importCsv()">Import & assign</button></div>`;
  api('/api/dir/users').then(us=>{$('bcsvadv').innerHTML=us.filter(x=>x.role==='advocate'&&x.active).map(x=>`<option value="${x.email}">${esc(x.display)}</option>`).join('');});}
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
async function importCsv(){const f=$('bcsv').files[0];if(!f){toast('Pick the CSV first');return;}
 const txt=await f.text();const lines=txt.split(/\r?\n/).filter(Boolean);
 const hdr=lines[0].toLowerCase().split(',').map(x=>x.replace(/"/g,'').trim());
 const idi=hdr.indexOf('member_id');const nmi=hdr.indexOf('batch');
 if(idi<0){toast('CSV needs a member_id column (use the dashboard 📦 export)');return;}
 const ids=lines.slice(1).map(l=>l.split(',')[idi].replace(/"/g,'').trim()).filter(Boolean);
 const name=(nmi>=0&&lines[1])?lines[1].split(',')[nmi].replace(/"/g,'').trim():f.name.replace(/\.csv$/i,'');
 const r=await api('/api/dir/import_batch',{method:'POST',body:JSON.stringify({name,advocate:$('bcsvadv').value,member_ids:ids})});
 toast(`✅ Imported batch #${r.batch_id}: ${r.accepted} accepted, ${r.rejected} rejected (already plated/refused/no phone)`);openTab('batches');loadStats();loadPie();}
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

ADVOCATE_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CRM — My Members</title><style>__CSS__</style></head><body>
<header><h1>📞 My Members</h1><span class="sp"></span><span class="me" id="tally"></span><span class="me">__ME__</span></header>
<div class="wrap">
<div class="tabs" id="tabs"></div>
<div id="list" class="panel">Loading…</div>
</div><div class="toast" id="toast"></div>
<script>__JSC__
let VIEW='queue',PAGE=0,M=null,OPENMID=null,LASTROWS=[],RUNQ=[],RUNI=0,RUNNING=false;
const SMS_ENABLED=true; // texting ON — unbranded texts, no MLR required
const VIEWS=[['due','⏰ Due now'],['queue','📋 To call'],['callbacks','📅 Callbacks set'],['done','✅ Done today']];
const DISP=['Left Voicemail','No Answer','Bad Number','Refused / Remove','DQ — Clinical','Deceased','Skipped'];
const SIT=['Reached someone else','Health event / hospitalized','Appointment changed'];
async function tally(){const s=await api('/api/adv/summary');$('tally').textContent=`today: ${s.today} worked · ${s.connected} connected`;}
function tabs(){$('tabs').innerHTML=VIEWS.map(v=>`<div class="tab ${v[0]===VIEW?'on':''}" data-v="${v[0]}">${v[1]}</div>`).join('');
 $('tabs').querySelectorAll('[data-v]').forEach(t=>t.onclick=()=>{VIEW=t.dataset.v;PAGE=0;OPENMID=null;load();});}
async function load(){tabs();const r=await api(`/api/adv/list?view=${VIEW}&page=${PAGE}`);
 const L=$('list');
 if(!r.rows.length){L.innerHTML='<span class="muted">'+(VIEW==='due'?'Nothing due right now — check 📋 To call.':'Nothing here yet.')+'</span>';return;}
 if(VIEW==='done'){
  L.innerHTML=`<table class="sheet"><tr><th>Member</th><th>Age</th><th>St</th><th>Disposition</th><th>When</th></tr>`+
   r.rows.map(x=>`<tr><td><b>${esc(x.first)} ${esc(x.last)}</b></td><td>${x.age??''}</td><td>${esc(x.st)}</td><td>${esc(x.disposition)}</td><td class="muted">${x.ts.slice(11,16)}</td></tr>`).join('')+'</table>'+pager(r);
  wire(r);return;}
 LASTROWS=r.rows.map(x=>x.member_id);
 L.innerHTML=`<div class="row" style="margin-bottom:8px"><button class="good" onclick="startRun()">⚡ Rapid-dial next ${Math.min(5,r.rows.length)}</button><span class="muted" style="font-size:11px">text · dial · one-tap outcome · auto-advance through the queue</span></div>`+
  `<table class="sheet"><tr><th></th><th>Member</th><th>Age</th><th>St</th><th>Stage</th><th>HCP appt</th><th>Next due</th><th>Conn/Att</th><th>Last outcome</th><th>Quals</th></tr>`+
  r.rows.map(x=>{const due=x.callback_at&&x.callback_at<=new Date().toISOString();
   return `<tr class="rowx" data-mid="${x.member_id}"><td aria-hidden="true">▸</td><td><b>${esc(x.first)} ${esc(x.last)}</b></td><td>${x.age??''}</td><td>${esc(x.st)}</td>
   <td>${(x.stage||'initial').replace('_',' ')} <span class="muted">${x.stage_attempts?('att '+x.stage_attempts+'/3'):''}</span></td>
   <td>${x.hcp_date||''}</td><td class="${due?'due':''}">${x.callback_at?x.callback_at.slice(5,16):''}</td>
   <td>${x.conn}/${x.att}</td><td>${esc((x.last_disp||'').slice(0,34))}</td>
   <td>${(x.quals||'').split(';').filter(Boolean).slice(0,2).map(q=>`<span class="qtag">${esc(q)}</span>`).join('')}</td></tr>
   <tr style="display:none" data-d="${x.member_id}"><td colspan="10"></td></tr>`;}).join('')+'</table>'+pager(r);
 wire(r);}
function pager(r){return `<div class="pager2"><button class="sec" id="pv" aria-label="Previous page" ${r.page==0?'disabled':''}>‹ Prev</button>
 <span class="muted">${r.total} members · page ${r.page+1} of ${Math.max(1,Math.ceil(r.total/r.per))} · showing ${r.per}/page</span>
 <button class="sec" id="nx" aria-label="Next page" ${(r.page+1)*r.per>=r.total?'disabled':''}>Next ›</button></div>`;}
function wire(r){const L=$('list');
 const pv=$('pv'),nx=$('nx');if(pv)pv.onclick=()=>{PAGE--;load();};if(nx)nx.onclick=()=>{PAGE++;load();};
 L.querySelectorAll('tr.rowx').forEach(tr=>tr.onclick=()=>openRow(tr.dataset.mid));}
async function openRow(mid){const L=$('list');
 const drow=L.querySelector(`tr[data-d="${mid}"]`);
 if(OPENMID===mid&&drow.style.display!=='none'){drow.style.display='none';OPENMID=null;return;}
 L.querySelectorAll('tr[data-d]').forEach(x=>x.style.display='none');
 drow.style.display='';OPENMID=mid;const cell=drow.firstElementChild;cell.innerHTML='<span class="muted">loading…</span>';
 M=await api('/api/adv/open/'+mid);M.call_click_at=null;M.text_click_at=null;
 cell.innerHTML=`<div class="drawer" id="card">
  <div class="muted">${esc(M.batch)} · <b style="color:#2563eb">${esc(M.stage_title)}</b>${(M.stage==='pre_hcp'||M.stage==='post_hcp')?` — attempt <b>${M.stage_attempt} of ${M.max_attempts}</b>`:''}${M.hcp_date?` · HCP appt: <b>${M.hcp_date}</b>`:''}</div>
  <div class="big">${esc(M.first)} ${esc(M.last)} <span class="muted" style="font-size:13px">${M.age??''} ${M.city?'· '+esc(M.city):''} ${esc(M.state)}</span></div>
  <div style="margin:4px 0">${(M.quals||'').split(';').filter(Boolean).map(q=>`<span class="qtag">${esc(q)}</span>`).join('')}
   ${(M.sflags||'').split(';').filter(Boolean).map(f=>`<span class="sflag">${esc(f)} — verify</span>`).join('')}</div>
  <div class="muted">Doctor: ${esc(M.doctor)||'—'}${M.clinic?' · '+esc(M.clinic):''} · Last connection: <b>${M.last_conn||'never'}</b> · Attempts since: <b>${M.att_since}</b></div>
  ${M.script?`<div style="background:#fffbe6;border:1px solid #fde68a;border-radius:8px;padding:8px 12px;margin:8px 0">📋 ${esc(M.script)}</div>`:''}
  <div class="row" style="margin:12px 0">
   <button class="good callbtn" onclick="go('call')">📞 Call</button>
   <button class="callbtn" style="background:#2563eb" onclick="copyText()">💬 Text</button>
   <span class="muted" style="font-size:11px">📞 Call &amp; 💬 Text open Google Voice (one tab) · the message is copied so you can paste it · every click is logged</span></div>
  <div class="lbl">Call log</div>
  <div class="hist">${(M.hist||[]).map(h=>`<div><span class="dot ${h.cls}">${h.cls==='C'?'●':h.cls==='A'?'○':h.cls==='B'?'✖':'·'}</span> <span class="muted">${h.date||'—'}</span> ${esc(h.event_type)} — ${esc((h.detail||'').slice(0,100))}</div>`).join('')||'<span class="muted">fresh — no prior events</span>'}</div>
  <div class="row" style="margin-top:12px"><button class="good" style="font-size:15px;padding:10px 20px" onclick="openGuide()">🟢 Connected — open guide</button>
   <span class="seg" id="stageSeg">${['initial','pre_hcp','post_hcp'].map(s=>`<button data-st="${s}" class="${s===M.stage?'on':''}">${s==='initial'?'Initial':s==='pre_hcp'?'Pre-HCP':'Post-HCP'}</button>`).join('')}</span>
   <span class="muted" style="font-size:11px">wrong call type? switch — e.g. the appointment already happened</span></div>
  <div id="guide" style="display:none"></div>
  <div class="lbl" style="margin-top:12px">Note <span class="muted" style="text-transform:none;font-weight:400">— always saved, on any outcome</span></div>
  <textarea id="note" placeholder="What happened on this call? (e.g. spoke to husband, wife not home; wants to reschedule after 5pm; in hospital, try in 2 weeks)" style="width:100%;height:52px"></textarea>
  <div class="lbl" style="margin-top:8px">Situation</div>
  <div class="dgrid">${SIT.map(d=>`<button class="sec" onclick="disp('${d}')">${d}</button>`).join('')}</div>
  <div class="lbl" style="margin-top:8px">No-connect</div>
  <div class="dgrid">${DISP.map(d=>`<button class="sec" onclick="disp('${d}')">${d}</button>`).join('')}</div>
  <div class="row"><span class="lbl" style="min-width:auto">New appt date</span><input id="newappt" type="date" title="if the appointment changed"><span class="lbl" style="min-width:auto">Callback</span><input id="cbat" type="datetime-local" title="callback time"></div>
 </div>`;
 drow.scrollIntoView({behavior:'smooth',block:'nearest'});}
async function switchStage(s){const g=await api('/api/adv/guide/'+M.member_id+(AS?AS+'&':'?')+'stage='+s);
 M.stage=g.stage;M.stage_title=g.stage_title;M.stage_script=g.stage_script;M.guide=g.guide;
 document.querySelectorAll('#stageSeg button').forEach(b=>b.classList.toggle('on',b.dataset.st===s));
 const gd=$('guide');if(gd&&gd.style.display!=='none')openGuide();
 toast('Guide switched to '+g.stage_title.split('(')[0]);}
document.addEventListener('click',e=>{const b=e.target.closest('#stageSeg [data-st]');if(b)switchStage(b.dataset.st);});
async function copyText(){if(!SMS_ENABLED){toast('💬 Texting is off for now — use Call');return;}const r=await api('/api/adv/click',{method:'POST',body:JSON.stringify({member_id:M.member_id,kind:'text'})});M.text_click_at=r.ts;
 try{await navigator.clipboard.writeText(M.sms_text||'');}catch(e){}
 try{await navigator.clipboard.writeText(M.sms_text||'');}catch(e){} window.open(M.text_url,'gv');toast('Google Voice opened · message copied — paste to send');}
function histHtml(x){return (x.hist||[]).map(h=>`<div><span class="dot ${h.cls}">${h.cls==='C'?'●':h.cls==='A'?'○':h.cls==='B'?'✖':'·'}</span> <span class="muted">${h.date||'—'}</span> ${esc(h.event_type)} — ${esc((h.detail||'').slice(0,90))}</div>`).join('')||'<span class="muted">fresh — no prior events</span>';}
async function startRun(){if(!LASTROWS.length){toast('Nothing to dial');return;}RUNQ=LASTROWS.slice(0,5);RUNI=0;RUNNING=true;await stepRun();}
async function stepRun(){if(RUNI>=RUNQ.length){return endRun(true);}
 M=await api('/api/adv/open/'+RUNQ[RUNI]);M.call_click_at=null;M.text_click_at=null;
 $('list').innerHTML=`<div class="panel"><div class="row"><b>⚡ Rapid dial — ${RUNI+1} of ${RUNQ.length}</b><span style="flex:1"></span><button class="sec" onclick="endRun(false)">exit to list</button></div>
  <div class="big">${esc(M.first)} ${esc(M.last)} <span class="muted" style="font-size:13px">${M.age??''} ${M.city?'· '+esc(M.city):''} ${esc(M.state)}</span></div>
  <div style="margin:4px 0">${(M.quals||'').split(';').filter(Boolean).map(q=>`<span class="qtag">${esc(q)}</span>`).join('')} ${(M.sflags||'').split(';').filter(Boolean).map(f=>`<span class="sflag">${esc(f)} — verify</span>`).join('')}</div>
  <div class="muted"><b style="color:#2563eb">${esc((M.stage_title||'').split('(')[0])}</b>${(M.stage==='pre_hcp'||M.stage==='post_hcp')?` — attempt ${M.stage_attempt}/${M.max_attempts}`:''}${M.hcp_date?' · HCP appt '+M.hcp_date:''} · ${M.conn}/${M.att} lifetime · last conn ${M.last_conn||'never'}</div>
  <div class="row" style="margin:12px 0">
   <button class="good callbtn" onclick="go('call')">📞 Call</button>
   <button class="callbtn" style="background:#2563eb" onclick="copyText()">📱 Text</button>
   <span class="muted" style="font-size:11px">tap Call → talk or leave a message → tap the outcome below</span></div>
  <div class="lbl">Call log</div><div class="hist">${histHtml(M)}</div>
  <div class="lbl" style="margin-top:10px">Note <span class="muted" style="text-transform:none;font-weight:400">— always saved</span></div>
  <textarea id="note" placeholder="what happened…" style="width:100%;height:40px"></textarea>
  <div class="lbl" style="margin-top:8px">Outcome — one tap logs &amp; loads the next</div>
  <div class="dgrid">
   <button class="good" onclick="openGuide()">🟢 Connected → guide</button>
   <button class="sec" onclick="runDisp('Reached someone else')">👥 Someone else answered</button>
   <button class="sec" onclick="runDisp('Health event / hospitalized')">🏥 Health event</button>
   <button class="sec" onclick="runAppt()">📆 Appt changed…</button>
   <button class="sec" onclick="runDisp('Left Voicemail')">📮 Left voicemail</button>
   <button class="sec" onclick="runDisp('No Answer')">🔕 No answer</button>
   <button class="sec" onclick="runDisp('Bad Number')">☎️ Bad number</button>
   <button class="sec" onclick="runDisp('Deceased')">🕊 Deceased</button>
   <button class="sec" onclick="runCb()">📅 Callback…</button>
   <button class="sec" onclick="runDisp('Skipped','skipped in rapid dial')">⏭ Skip</button></div>
  <div id="guide" style="display:none"></div></div>`;
 window.scrollTo({top:0,behavior:'smooth'});}
async function runDisp(d,note){const nb=$('note');const n=note||(nb?nb.value:'');
 await api('/api/adv/disposition',{method:'POST',body:JSON.stringify({member_id:M.member_id,disposition:d,note:n,served_at:M.served_at,call_click_at:M.call_click_at,text_click_at:M.text_click_at})});toast(d+' logged — next');RUNI++;tally();stepRun();}
async function runAppt(){const t=prompt('New appointment date (YYYY-MM-DD):');if(!t)return;
 try{await api('/api/adv/disposition',{method:'POST',body:JSON.stringify({member_id:M.member_id,disposition:'Appointment changed',hcp_date:t.slice(0,10),note:($('note')?$('note').value:''),served_at:M.served_at,call_click_at:M.call_click_at})});toast('Appt updated — cadence re-timed');RUNI++;tally();stepRun();}
 catch(e){toast('Enter a valid date YYYY-MM-DD')}}
async function runCb(){const t=prompt('Callback date & time (YYYY-MM-DD HH:MM):');if(!t)return;
 try{await api('/api/adv/disposition',{method:'POST',body:JSON.stringify({member_id:M.member_id,disposition:'Connected — Callback Scheduled',callback_at:t.replace(' ','T'),served_at:M.served_at,call_click_at:M.call_click_at})});RUNI++;tally();stepRun();}
 catch(e){toast('Enter a valid future date/time');}}
function endRun(done){RUNNING=false;RUNQ=[];if(done)toast('⚡ Rapid dial complete — queue worked');load();}
async function go(kind){const r=await api('/api/adv/click',{method:'POST',body:JSON.stringify({member_id:M.member_id,kind})});
 if(kind==='call')M.call_click_at=r.ts;else M.text_click_at=r.ts;
 window.open(kind==='call'?M.call_url:M.text_url,'gv');}
function openGuide(){const g=$('guide');g.style.display='';
 g.innerHTML=`<div class="panel" style="border-color:#16a34a;background:#f7fdf9;margin-top:10px"><div class="lbl">${esc(M.stage_title)} — read scripted lines verbatim, record answers</div>`+
 M.guide.map(it=>{let inner='';
  const text=(it.text||'').replace('<Member Name>',M.first).replace('[Name]',M.first).replace('[date of upcoming appointment]',M.hcp_date||'your upcoming date').replace('<Neurologist Name>',M.doctor||'your neurologist');
  if(it.kind==='say')inner=`<div style="white-space:pre-wrap;margin:9px 0;padding:8px 12px;background:#fff;border-left:3px solid #2563eb;border-radius:4px">${esc(text)}</div>`;
  else if(it.kind==='instr')inner=`<div style="margin:7px 0;font-size:12px;color:#7c3aed">⚙ ${esc(text)}</div>`;
  else{let inp='';
   if(it.qtype==='radio')inp=`<select data-qid="${it.id}" data-seq="${it.seq}" onchange="reeval()"><option value=""></option>${it.options.split('|').map(o=>`<option>${esc(o)}</option>`).join('')}</select>`;
   else if(it.qtype==='check')inp=it.options.split('|').map(o=>`<label style="display:block;font-size:12.5px"><input type="checkbox" data-qid="${it.id}" data-seq="${it.seq}" value="${escA(o)}" onchange="reeval()"> ${esc(o)}</label>`).join('');
   else if(it.qtype==='date')inp=`<input type="date" data-qid="${it.id}" data-seq="${it.seq}" onchange="reeval()">`;
   else inp=`<textarea data-qid="${it.id}" data-seq="${it.seq}" style="width:100%;height:44px"></textarea>`;
   inner=`<div style="margin:9px 0"><div style="font-weight:600">${esc(text)}${it.sched==='hcp'?' <span class="muted">(drives call scheduling)</span>':''}${it.dq_vals?' <span class="dnc">contraindication check</span>':''}</div>${inp}</div>`;}
  return `<div class="gitem" data-gseq="${it.seq}" data-show="${escA(it.show_qid||'')}" data-showvals="${escA(it.show_vals||'')}">${inner}</div>`;}).join('')+
 `<div class="row"><button class="good" onclick="submitGuide()">Save answers & schedule next call</button><button class="sec" onclick="$('guide').style.display='none'">cancel</button></div></div>`;
 reeval();g.scrollIntoView({behavior:'smooth'});}
function answerOf(seq){const els=[...document.querySelectorAll(`#guide [data-seq="${seq}"]`)];if(!els.length)return '';
 if(els[0].type==='checkbox')return els.filter(e=>e.checked).map(e=>e.value).join('; ');
 return els[0].value||'';}
function reeval(){document.querySelectorAll('#guide .gitem').forEach(el=>{const ctrl=el.dataset.show;if(!ctrl)return;
 const want=el.dataset.showvals.split('|');const got=answerOf(ctrl);
 el.style.display=(got&&want.some(w=>got.includes(w)))?'':'none';});}
async function submitGuide(){
 const seen=new Set();const answers=[];
 document.querySelectorAll('#guide .gitem').forEach(el=>{if(el.style.display==='none')return;
  const q=el.querySelector('[data-qid]');if(!q)return;const qid=+q.dataset.qid;if(seen.has(qid))return;seen.add(qid);
  const v=answerOf(q.dataset.seq);if(v)answers.push({qid,answer:v});});
 if(!answers.length){toast('Record at least one answer');return;}
 const r=await api('/api/adv/guide_submit',{method:'POST',body:JSON.stringify({member_id:M.member_id,stage:M.stage,answers,served_at:M.served_at,call_click_at:M.call_click_at,text_click_at:M.text_click_at})});
 toast('Saved — '+r.outcome);tally();if(RUNNING){RUNI++;stepRun();}else{OPENMID=null;load();}}
async function disp(d){
 if(d==='Appointment changed'&&!($('newappt')&&$('newappt').value)){toast('Enter the new appointment date first');return;}
 const body={member_id:M.member_id,disposition:d,note:$('note')?$('note').value:'',served_at:M.served_at,
  call_click_at:M.call_click_at,text_click_at:M.text_click_at,
  callback_at:($('cbat')&&$('cbat').value)||null,
  hcp_date:($('newappt')&&$('newappt').value)||null};
 await api('/api/adv/disposition',{method:'POST',body:JSON.stringify(body)});toast(d+' logged');tally();if(RUNNING){RUNI++;stepRun();}else{OPENMID=null;load();}}
tally();load();
</script></body></html>"""
ADVOCATE_HTML = ADVOCATE_HTML.replace('__CSS__', CSS).replace('__JSC__', JS_COMMON)
