"""Real-time advocate progress monitor — director-only, READ-ONLY, self-contained.

Isolated add-on: all logic + page HTML live here. Reuses helpers from main and the shared
stylesheet from ui via read-only imports (importing a module does not edit its file). Runs only
SELECTs — no writes, not even an audit() row — so it never contends with any concurrent DB edit.
Wire-in is a single additive line at the bottom of main.py: app.include_router(router).
"""
import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from main import who, need, db, now          # defined near the top of main.py, before its bottom-of-file
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
        advocates.append({
            'email': em, 'display': a['display'],
            'online': online, 'log_on': None, 'log_off': None,          # literal stubs -> "—"
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
    <div><div class="lbl" style="min-width:0">Log on</div><div>${a.log_on??'—'}</div></div>
    <div><div class="lbl" style="min-width:0">Log off</div><div>${a.log_off??'—'}</div></div></div>
   <div class="muted" style="font-size:var(--fs-2xs);margin-top:2px">log on/off not tracked yet</div>
   <div class="row2" style="margin-top:8px">
    <div class="kpi"><b>${a.calls_today}</b>calls</div>
    <div class="kpi"><b>${a.connected_today}</b>conn</div>
    <div class="kpi"><b>${a.pending+a.served}</b>plate</div>
    <div class="kpi"><b>${a.callbacks}</b>callb</div>
    <div class="kpi"><b style="color:${a.due_now?'var(--bad)':'inherit'}">${a.due_now}</b>due</div></div>
   ${a.calls_today?`<div class="piebar" style="height:20px;margin-top:8px">${pbx.bar}</div>`
     :'<div class="muted" style="margin-top:8px">No calls today.</div>'}</div>`;}).join('');
}
async function refresh(){
 if(BUSY)return; BUSY=true;
 try{ const d=await api('/api/dir/monitor'); render(d); $('asof').textContent='updated '+new Date().toLocaleTimeString(); }
 catch(e){} finally{ BUSY=false; }
}
$('navdir').href='/director'+AS;
refresh(); setInterval(refresh,15000);
</script></body></html>""").replace('__CSS__', CSS).replace('__JSC__', JS_COMMON)
