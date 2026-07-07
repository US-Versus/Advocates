"""Real-time advocate progress monitor — director-only, READ-ONLY, self-contained.

Isolated add-on: all logic + page HTML live here. Reuses helpers from main and the shared
stylesheet from ui via read-only imports (importing a module does not edit its file). Runs only
SELECTs — no writes, not even an audit() row — so it never contends with any concurrent DB edit.
Wire-in is a single additive line at the bottom of main.py: app.include_router(router).
"""
import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from main import who, need, db, now, _punch_status, _ot_status, _sched_row, _sched_text   # defined in main before its bottom-of-file
from ui import CSS, JS_COMMON                 # include line triggers this import -> no circular trap

router = APIRouter()
ONLINE_SECS = 300                             # "active now" if last activity within 5 minutes


def _within(ts, ref, secs):
    """True if ISO timestamp `ts` is within `secs` seconds of ISO `ref`."""
    if not ts:
        return False
    try:
        delta = (datetime.datetime.fromisoformat(ref) - datetime.datetime.fromisoformat(ts)).total_seconds()
        return 0 <= delta <= secs          # 0..secs; a future-dated ts (clock skew) is not "active"
    except ValueError:
        return False


@router.get('/api/dir/monitor')
def monitor_data(req: Request):
    """Aggregate (today, all advocates) + per-advocate rollup. Read-only; no audit write."""
    u = who(req); need(u, 'director'); c = db()
    ref = now(); today = ref[:10]; like = today + '%'

    # --- aggregate outcomes (all actors, today) — computed independently of the roster ---
    agg_disp = {r['disposition']: r['n'] for r in c.execute(
        "SELECT disposition, COUNT(*) n FROM dispositions WHERE ts LIKE ? GROUP BY disposition", (like,))}
    calls_today = sum(agg_disp.values())
    connected_today = sum(v for k, v in agg_disp.items() if str(k).startswith('Connected'))

    # --- per-advocate boxes ---
    advocates = []; active = 0
    for a in c.execute("SELECT email, display FROM users WHERE role='advocate' AND active=1 ORDER BY display"):
        em = a['email']
        disp = {r['disposition']: r['n'] for r in c.execute(
            "SELECT disposition, COUNT(*) n FROM dispositions WHERE actor=? AND ts LIKE ? GROUP BY disposition",
            (em, like))}
        ctoday = sum(v for k, v in disp.items() if str(k).startswith('Connected'))
        r = c.execute("""SELECT
            SUM(CASE WHEN bm.state='pending'  THEN 1 ELSE 0 END) pending,
            SUM(CASE WHEN bm.state='served'   THEN 1 ELSE 0 END) served,
            SUM(CASE WHEN bm.state='callback' THEN 1 ELSE 0 END) callbacks,
            SUM(CASE WHEN bm.state='done'     THEN 1 ELSE 0 END) done
            FROM batch_members bm JOIN batches b ON b.id=bm.batch_id
            WHERE b.advocate=? AND b.status='open'""", (em,)).fetchone()
        due = c.execute("""SELECT COUNT(*) n FROM batch_members bm JOIN batches b ON b.id=bm.batch_id
            WHERE b.advocate=? AND b.status='open' AND bm.state='callback' AND bm.callback_at<=?""",
            (em, ref)).fetchone()['n']
        last = c.execute("SELECT MAX(ts) m FROM activity WHERE actor=?", (em,)).fetchone()['m']
        online = _within(last, ref, ONLINE_SECS)
        if online:
            active += 1
        ps = _punch_status(c, em); sch = _sched_row(c, em); ot = _ot_status(c, em, ps['hours'])
        advocates.append({
            'email': em, 'display': a['display'],
            'online': online,
            # punch-clock (today, advocate tz)
            'punch_in': ps['in'], 'punch_out': ps['out'], 'punched_in': ps['on_clock'],
            'in_ontime': ps['in_ontime'], 'out_ontime': ps['out_ontime'],
            'hours_today': ps['hours'], 'sched_text': (_sched_text(sch) if sch else None),
            'schedule': (dict(sch) if sch else None), 'ot': ot,
            'calls_today': sum(disp.values()), 'connected_today': ctoday, 'last_activity': last or '',
            'dispositions': disp,
            'pending': r['pending'] or 0, 'served': r['served'] or 0,
            'callbacks': r['callbacks'] or 0, 'done_open': r['done'] or 0, 'due_now': due,
        })

    # --- chronological call log (today, all advocates), oldest first ---
    log = [dict(x) for x in c.execute("""
        SELECT d.ts, d.actor, COALESCE(u.display, d.actor) display, d.member_id,
               TRIM(COALESCE(m.first,'') || ' ' || COALESCE(m.last,'')) name,
               d.disposition, COALESCE(d.note,'') note
        FROM dispositions d
        LEFT JOIN member_core m USING(member_id)
        LEFT JOIN users u ON u.email = d.actor
        WHERE d.ts LIKE ? ORDER BY d.ts LIMIT 200""", (like,))]

    return {
        'as_of': ref, 'date': today,
        'aggregate': {
            'calls_today': calls_today, 'connected_today': connected_today,
            'advocates_active': active, 'dispositions': agg_disp, 'log': log,
        },
        'advocates': advocates,
    }


@router.get('/monitor', response_class=HTMLResponse)
def monitor_page(req: Request):
    u = who(req); need(u, 'director')          # director-only, same guard as /director and /dashboard
    return HTMLResponse(MONITOR_HTML.replace('__ME__', u['email']))


MONITOR_HTML = ("""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CRM — Monitor</title><style>__CSS__</style></head><body>
<header><h1>📡 Monitor</h1>
 <a id="navdir" href="/director" style="margin-left:14px;color:#93c5fd;font-size:13px;font-weight:600;text-decoration:none">🎖 Director ↗</a>
 <span class="sp"></span><span class="me" id="asof"></span><span class="me">__ME__</span></header>
<div class="wrap">
 <div class="panel">
  <h3>📊 Today — all advocates <span class="muted" id="datelbl"></span></h3>
  <div class="stats" id="aggstats"></div>
  <div class="lbl" style="margin-bottom:6px">Outcomes</div>
  <div class="piebar" id="aggbar"></div>
  <div class="pieleg" id="aggleg"></div>
  <h4>Call log</h4>
  <div style="max-height:340px;overflow-y:auto">
   <table><thead><tr><th>When</th><th>Advocate</th><th>Member</th><th>Outcome</th><th>Note</th></tr></thead>
   <tbody id="agglog"></tbody></table>
  </div>
 </div>
 <div class="panel">
  <h3>🕐 Staff time <span class="muted">· today · ⚠ = outside the 15-min window</span></h3>
  <div class="tscroll"><table><thead><tr><th>Advocate</th><th>Scheduled</th><th>In</th><th>Out</th><th>Hours</th><th>OT</th></tr></thead>
   <tbody id="stafftbl"></tbody></table></div>
  <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--line)">
   <div class="lbl">Set schedule &amp; OT policy</div>
   <div class="row" style="flex-wrap:wrap;gap:8px;align-items:center">
    <select id="schadv" onchange="fillSchForm()"></select>
    <span class="muted">Days</span><span id="schdays"></span>
    <span class="muted">Shift</span>
    <input type="time" id="b1s"><span>–</span><input type="time" id="b1e">
    <span class="muted">&amp;</span><input type="time" id="b2s"><span>–</span><input type="time" id="b2e">
    <select id="schtz"><option value="America/Denver">MTN</option><option value="America/Chicago">CTN</option><option value="America/New_York">ETN</option><option value="America/Los_Angeles">PTN</option><option value="America/Tegucigalpa">Honduras</option></select>
   </div>
   <div class="row" style="flex-wrap:wrap;gap:8px;align-items:center;margin-top:6px">
    <label><input type="checkbox" id="otperm"> OT permitted</label>
    <span class="muted">multiple</span><input id="otmult" value="1.25" style="width:64px">
    <span class="muted">max OT hrs</span><input id="othrs" value="10" style="width:64px">
    <button class="good" onclick="saveSched()">Save schedule</button>
    <span class="muted" style="font-size:var(--fs-2xs)">no schedule = "work honestly", time still tracked</span>
   </div>
  </div>
 </div>
 <div class="panel">
  <h3>Advocates</h3>
  <div class="advcards" id="advboxes"></div>
 </div>
</div>
<div class="toast" id="toast"></div>
<script>__JSC__
let BUSY=false;
const DCOL={'Reached someone else':'var(--brand)','Left Voicemail':'#64748b','No Answer':'var(--warn)',
 'Bad Number':'var(--bad)','Refused / Remove':'var(--bad)','Deceased':'var(--bad)','DQ — Clinical':'var(--bad)',
 'Health event / hospitalized':'var(--warn)','Appointment changed':'var(--brand)','Skipped':'var(--faint)'};
function dcol(k){return (k&&k.indexOf('Connected')===0)?'var(--good)':(DCOL[k]||'#64748b');}
function dclass(k){if(k&&k.indexOf('Connected')===0)return 'C';
 if(['Bad Number','Refused / Remove','Deceased','DQ — Clinical'].indexOf(k)>=0)return 'B';
 if(['Reached someone else','Appointment changed'].indexOf(k)>=0)return 'C';return 'A';}
function piebar(disp){
 const e=Object.entries(disp||{}).sort((a,b)=>b[1]-a[1]);
 const tot=Math.max(1,e.reduce((s,x)=>s+x[1],0));
 const bar=e.map(([k,v])=>{const w=v/tot*100;
  return `<div style="background:${dcol(k)};width:${Math.max(w,1.5)}%" title="${escA(k)}: ${v}">${w>9?v:''}</div>`;}).join('');
 const leg=e.map(([k,v])=>`<span><i class="dotc" style="background:${dcol(k)}"></i>${esc(k)} <b>${v}</b></span>`).join('');
 return {bar,leg,empty:e.length===0};
}
function render(d){
 const ag=d.aggregate;
 $('datelbl').textContent='· '+d.date;
 $('aggstats').innerHTML=[['Calls today',ag.calls_today],['Connected today',ag.connected_today],
  ['Advocates active',ag.advocates_active]].map(s=>`<div class="stat"><div class="n">${s[1]}</div><div class="l">${s[0]}</div></div>`).join('');
 const pb=piebar(ag.dispositions);
 $('aggbar').innerHTML=pb.empty?'<div style="background:var(--faint);width:100%">no calls yet today</div>':pb.bar;
 $('aggleg').innerHTML=pb.leg;
 $('agglog').innerHTML=ag.log.length?ag.log.slice().reverse().map(x=>{
  const t=(x.ts||'').slice(11,16), who=(x.name||'').trim()||x.member_id;
  return `<tr><td class="muted">${t}</td><td>${esc(x.display)}</td><td>${esc(who)}</td>`
   +`<td><span class="dot ${dclass(x.disposition)}">●</span> ${esc(x.disposition)}</td>`
   +`<td class="muted">${esc((x.note||'').slice(0,60))}</td></tr>`;}).join('')
  :'<tr><td colspan="5" class="muted">No calls logged today.</td></tr>';
 $('advboxes').innerHTML=d.advocates.map(a=>{
  const pbx=piebar(a.dispositions), last=a.last_activity?a.last_activity.slice(11,16):'—';
  return `<div class="advcard">
   <div style="display:flex;justify-content:space-between;align-items:center">
    <b>${a.online?'🟢':'⚪'} ${esc(a.display)}</b><span class="muted">last ${last}</span></div>
   <div class="row2" style="margin-top:6px">
    <div><div class="lbl" style="min-width:0">In</div><div>${a.punch_in?esc(a.punch_in)+(a.in_ontime===0?' ⚠':''):'—'}${a.punched_in?' <span style="color:var(--good)">● on</span>':''}</div></div>
    <div><div class="lbl" style="min-width:0">Out</div><div>${a.punch_out?esc(a.punch_out)+(a.out_ontime===0?' ⚠':''):(a.punched_in?'on clock':'—')}</div></div></div>
   <div class="muted" style="font-size:var(--fs-2xs);margin-top:2px">${a.hours_today?a.hours_today+'h today':'—'}${a.sched_text?' · '+esc(a.sched_text):' · work honestly'}${a.ot&&a.ot.over?(a.ot.ok?' · <span style="color:var(--warn)">OT '+a.ot.over_hours+'h</span>':' · <span style="color:var(--bad)">⚠ OT '+a.ot.over_hours+'h '+(a.ot.permitted?'over cap':'not permitted')+'</span>'):''}</div>
   <div class="row2" style="margin-top:8px">
    <div class="kpi"><b>${a.calls_today}</b>calls</div>
    <div class="kpi"><b>${a.connected_today}</b>conn</div>
    <div class="kpi"><b>${a.pending+a.served}</b>plate</div>
    <div class="kpi"><b>${a.callbacks}</b>callb</div>
    <div class="kpi"><b style="color:${a.due_now?'var(--bad)':'inherit'}">${a.due_now}</b>due</div></div>
   ${a.calls_today?`<div class="piebar" style="height:20px;margin-top:8px">${pbx.bar}</div>`
     :'<div class="muted" style="margin-top:8px">No calls today.</div>'}</div>`;}).join('');
 // --- staff time table ---
 window._MON=d;
 $('stafftbl').innerHTML=d.advocates.map(a=>{const ot=a.ot;
  const otc=ot&&ot.over?(ot.ok?`<span class="tchip" style="background:var(--warn)">OT ${ot.over_hours}h</span>`:`<span class="tchip" style="background:var(--bad)">⚠ OT ${ot.over_hours}h ${ot.permitted?'over cap':'not permitted'}</span>`):(a.sched_text?'<span class="muted">on track</span>':'<span class="muted">honor</span>');
  return `<tr><td><b>${esc(a.display)}</b></td><td class="muted">${a.sched_text?esc(a.sched_text):'work honestly'}</td>`
   +`<td>${a.punch_in?esc(a.punch_in)+(a.in_ontime===0?' ⚠':''):'—'}${a.punched_in?' <span style="color:var(--good)">●</span>':''}</td>`
   +`<td>${a.punch_out?esc(a.punch_out)+(a.out_ontime===0?' ⚠':''):(a.punched_in?'on clock':'—')}</td>`
   +`<td><b>${a.hours_today}h</b></td><td>${otc}</td></tr>`;}).join('')||'<tr><td colspan="6" class="muted">No advocates.</td></tr>';
 if($('schadv')&&!$('schadv').options.length)initSchForm(d);
}
function initSchForm(d){
 $('schdays').innerHTML=[['1','M'],['2','Tu'],['3','W'],['4','Th'],['5','F'],['6','Sa'],['7','Su']].map(x=>`<label style="margin-right:4px"><input type="checkbox" value="${x[0]}"> ${x[1]}</label>`).join('');
 $('schadv').innerHTML=d.advocates.map(a=>`<option value="${escA(a.email)}">${esc(a.display)}</option>`).join('')||'<option value="">(no advocates)</option>';
 fillSchForm();
}
function fillSchForm(){const d=window._MON;if(!d)return;const a=d.advocates.find(x=>x.email===$('schadv').value);const s=a&&a.schedule;
 const days=(s&&s.days)||'12345';$('schdays').querySelectorAll('input').forEach(cb=>cb.checked=days.indexOf(cb.value)>=0);
 let bl=[];try{bl=s&&s.blocks?JSON.parse(s.blocks):[]}catch(e){}
 $('b1s').value=(bl[0]&&bl[0][0])||'08:00';$('b1e').value=(bl[0]&&bl[0][1])||'12:00';
 $('b2s').value=(bl[1]&&bl[1][0])||'';$('b2e').value=(bl[1]&&bl[1][1])||'';
 $('schtz').value=(s&&s.tz)||'America/Denver';
 $('otperm').checked=!!(s&&s.ot_permitted);$('otmult').value=(s&&s.ot_multiple)||1.25;$('othrs').value=(s&&s.ot_hours)||10;}
async function saveSched(){if(!$('schadv').value){toast('Pick an advocate');return;}
 const days=[...$('schdays').querySelectorAll('input:checked')].map(x=>x.value).join('');const blocks=[];
 if($('b1s').value&&$('b1e').value)blocks.push([$('b1s').value,$('b1e').value]);
 if($('b2s').value&&$('b2e').value)blocks.push([$('b2s').value,$('b2e').value]);
 try{await api('/api/dir/schedule',{method:'POST',body:JSON.stringify({email:$('schadv').value,days,blocks,tz:$('schtz').value,ot_permitted:$('otperm').checked,ot_multiple:parseFloat($('otmult').value)||1.25,ot_hours:parseFloat($('othrs').value)||0})});
  toast('✅ Schedule saved');refresh();}catch(e){toast('Save failed');}}
async function refresh(){
 if(BUSY)return; BUSY=true;
 try{ const d=await api('/api/dir/monitor'); render(d); $('asof').textContent='updated '+new Date().toLocaleTimeString(); }
 catch(e){} finally{ BUSY=false; }
}
$('navdir').href='/director'+AS;
refresh(); setInterval(refresh,15000);
</script></body></html>""").replace('__CSS__', CSS).replace('__JSC__', JS_COMMON)
