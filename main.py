"""Advocacy CRM — director assignment + advocate served queue with Google Voice click-to-dial.
Runs on Cloud Run behind Identity-Aware Proxy. Roles enforced server-side; every action audited.
Local dev:  DEV=1 uvicorn main:app --reload   (then ?as=you@org.com)
"""
import os, re, sqlite3, json, datetime, urllib.parse, threading, time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

DB = os.environ.get('APP_DB', os.path.join(os.path.dirname(__file__), 'app.db'))
DEV = os.environ.get('DEV') == '1'
MIN_HANDLE_SECS = 20          # dispositions faster than this get flagged
CONNECT_MIN_SECS = 60         # 'Connected' dispositions faster than this after call-click get flagged
app = FastAPI()

# --- Bridge hardening (Stage 0) ---------------------------------------------
# The live DB is SQLite on a gcsfuse-mounted GCS bucket, served by ONE Cloud Run
# instance. gcsfuse does not reliably honor the POSIX (fcntl) locks SQLite uses,
# and the app writes from a threadpool (sync endpoints) + the event loop (async
# endpoints), so two writers could otherwise collide. We serialize every commit
# through a single process-wide lock (so the OS/gcsfuse never sees two concurrent
# writers from this process) and retry the rare 'database is locked'. busy_timeout
# makes the write-execute phase WAIT for a lock instead of failing immediately.
# Reads never take the lock, so read concurrency is unaffected. This is a bridge
# until the Cloud SQL/Postgres migration (Stage 2); snapshots + versioning cover
# the residual risk.
_WRITE_LOCK = threading.RLock()

class _Conn(sqlite3.Connection):
    def commit(self):
        with _WRITE_LOCK:
            for attempt in range(5):
                try:
                    return super().commit()
                except sqlite3.OperationalError as e:
                    if 'locked' in str(e).lower() and attempt < 4:
                        time.sleep(0.1 * (attempt + 1)); continue
                    raise

def db():
    c = sqlite3.connect(DB, factory=_Conn, timeout=20.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=20000")   # wait through a transient gcsfuse write stall, don't 500
    c.execute("PRAGMA synchronous=NORMAL")   # FULL forces a full GCS object write per commit WHILE holding the
                                             # exclusive lock -> cascading 'database is locked' under load. NORMAL
                                             # keeps commits fast (durability still covered by snapshots+versioning).
    return c

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def who(req: Request):
    email = req.headers.get('X-Goog-Authenticated-User-Email', '')
    email = email.split(':')[-1].lower()
    if not email and DEV: email = (req.query_params.get('as') or '').lower()
    if not email: raise HTTPException(401, 'No identity (IAP header missing)')
    row = db().execute("SELECT * FROM users WHERE email=? AND active=1", (email,)).fetchone()
    if not row: raise HTTPException(403, f'{email} is not enrolled')
    return dict(row)

def need(u, role):
    if u['role'] != role: raise HTTPException(403, 'forbidden')

def audit(actor, action, member_id=None, batch_id=None, meta=None):
    c = db(); c.execute("INSERT INTO activity(ts,actor,action,member_id,batch_id,meta) VALUES(?,?,?,?,?,?)",
        (now(), actor, action, member_id, batch_id, json.dumps(meta or {}))); c.commit()

# ---------------- shared ----------------
@app.get('/', response_class=HTMLResponse)
def root(req: Request):
    u = who(req)
    # One address for everyone (crm.parkinsons.community). Role decides the view, served IN PLACE —
    # nothing to type after the domain, URL bar stays on the bare host.
    if u['role'] == 'director':
        return full_dashboard(req)          # director view = the CRM Review Dashboard (live filters)
    return HTMLResponse(ADVOCATE_HTML.replace('__ME__', u['display']))   # advocate view = the served queue

@app.get('/healthz')
def health(): return {'ok': True}

# ---------------- director API ----------------
QUAL_CHIPS = ['Apokyn','Onapgo Qualified','Onapgo','Inbrija','Gocovri','Dyskinesia','N317 trial','IPX203 trial','OFF signals']

def filter_sql(f):
    w = ["status='Active'", "phone<>''", "refused=0"]; p = []
    today = datetime.date.today()
    def ago(months): return (today - datetime.timedelta(days=30*months)).isoformat()
    # qualification chips: tri-state (include OR'd / exclude AND-not)
    inc=[q for q in (f.get('qual_inc') or f.get('quals') or []) if q in QUAL_CHIPS]
    exc=[q for q in (f.get('qual_exc') or []) if q in QUAL_CHIPS]
    if inc:
        w.append('('+' OR '.join("';'||quals||';' LIKE ?" for _ in inc)+')'); p+=[f'%;{q};%' for q in inc]
    for q in exc:
        w.append("';'||quals||';' NOT LIKE ?"); p.append(f'%;{q};%')
    if f.get('exclude_flags'): w.append("sflags=''")
    # last connection bucket
    lc=f.get('lc') or 'any'
    if lc=='never': w.append('conn=0')
    elif lc=='6m': w.append('last_conn>=?'); p.append(ago(6))
    elif lc=='1y': w.append('last_conn>=? AND last_conn<?'); p+=[ago(12),ago(6)]
    elif lc=='2y': w.append('last_conn>=? AND last_conn<?'); p+=[ago(24),ago(12)]
    elif lc=='old': w.append("last_conn<>'' AND last_conn<?"); p.append(ago(24))
    # attempts-since buckets (multi, OR)
    AS_SQL={'0':'att_since=0','12':'att_since BETWEEN 1 AND 2','35':'att_since BETWEEN 3 AND 5','6p':'att_since>=6'}
    asb=[AS_SQL[k] for k in (f.get('att_since') or []) if k in AS_SQL]
    if asb: w.append('('+' OR '.join(asb)+')')
    # total connections bucket
    tc=f.get('tc') or 'any'
    if tc=='0': w.append('conn=0')
    elif tc=='1': w.append('conn=1')
    elif tc=='2p': w.append('conn>=2')
    # age buckets (multi, OR; 'unk' = no age)
    AGE_SQL={'<50':'age<50','50':'age BETWEEN 50 AND 59','60':'age BETWEEN 60 AND 69','70':'age BETWEEN 70 AND 79','80':'age>=80','unk':'age IS NULL'}
    ab=[AGE_SQL[k] for k in (f.get('ages') or []) if k in AGE_SQL]
    if ab: w.append('('+' OR '.join(ab)+')')
    if f.get('never_attempted'): w.append('conn=0 AND att=0')
    if f.get('att_max') not in (None,''): w.append('att<=?'); p.append(int(f['att_max']))
    if f.get('state'): w.append('state=?'); p.append(f['state'].upper())
    w.append('member_id NOT IN (SELECT member_id FROM batch_members bm JOIN batches b ON b.id=bm.batch_id '
             "WHERE b.status='open' AND bm.state IN('pending','served','callback'))")
    return ' AND '.join(w), p

@app.post('/api/dir/preview_rows')
async def preview_rows(req: Request):
    u = who(req); need(u,'director')
    f = await req.json(); w,p = filter_sql(f)
    rows = db().execute(f"SELECT member_id,first,last,age,state,quals,last_conn,att FROM member_core WHERE {w} ORDER BY att ASC, last_conn DESC LIMIT 10", p).fetchall()
    n = db().execute(f"SELECT COUNT(*) c FROM member_core WHERE {w}", p).fetchone()['c']
    out=[dict(r) for r in rows]
    audit(u['email'],'preview_rows',meta={'filters':f,'count':n,'member_ids':[r['member_id'] for r in out]})
    for r in out: r.pop('member_id',None)
    return {'count': n, 'rows': out}

@app.get('/api/dir/stats')
def dir_stats(req: Request):
    u = who(req); need(u,'director'); c=db()
    eligible = c.execute("SELECT COUNT(*) n FROM member_core WHERE status='Active' AND phone<>'' AND refused=0").fetchone()['n']
    inbatch = c.execute("SELECT COUNT(*) n FROM batch_members bm JOIN batches b ON b.id=bm.batch_id WHERE b.status='open' AND bm.state IN('pending','served','callback')").fetchone()['n']
    today = now()[:10]
    worked = c.execute("SELECT COUNT(*) n FROM dispositions WHERE ts LIKE ?", (today+'%',)).fetchone()['n']
    connected = c.execute("SELECT COUNT(*) n FROM dispositions WHERE ts LIKE ? AND disposition LIKE 'Connected%'", (today+'%',)).fetchone()['n']
    cb = c.execute("SELECT COUNT(*) n FROM batch_members bm JOIN batches b ON b.id=bm.batch_id WHERE b.status='open' AND bm.state='callback' AND bm.callback_at<=?", (now(),)).fetchone()['n']
    return {'eligible':eligible,'in_batch':inbatch,'worked_today':worked,'connected_today':connected,'callbacks_due':cb}

@app.get('/api/dir/pie')
def pie(req: Request):
    u=who(req); need(u,'director'); c=db()
    base="status='Active' AND phone<>'' AND refused=0"
    tot=c.execute(f"SELECT COUNT(*) n FROM member_core WHERE {base}").fetchone()['n']
    OPEN="""SELECT DISTINCT bm.member_id FROM batch_members bm JOIN batches b ON b.id=bm.batch_id
        WHERE b.status='open' AND bm.state IN('pending','served','callback')"""
    inopen=c.execute(f"SELECT COUNT(*) n FROM member_core WHERE {base} AND member_id IN ({OPEN})").fetchone()['n']
    # worked = eligible, not currently plated, with a done batch row; classified by their latest done stage
    rows=c.execute(f"""SELECT stage, COUNT(*) n FROM (
        SELECT bm.member_id, (SELECT bm2.stage FROM batch_members bm2 WHERE bm2.member_id=bm.member_id AND bm2.state='done'
                              ORDER BY bm2.batch_id DESC LIMIT 1) stage
        FROM member_core mc JOIN batch_members bm ON bm.member_id=mc.member_id
        WHERE mc.status='Active' AND mc.phone<>'' AND mc.refused=0
          AND bm.state='done' AND mc.member_id NOT IN ({OPEN})
        GROUP BY bm.member_id) GROUP BY stage""").fetchall()
    done={r['stage'] or 'other': r['n'] for r in rows}
    completed=done.get('complete',0)
    missed=done.get('missed_post',0)+done.get('no_appt',0)
    other_done=sum(done.values())-completed-missed
    worked=completed+missed+other_done
    available=tot-inopen-worked
    refused=c.execute("SELECT COUNT(*) n FROM member_core WHERE status='Active' AND refused=1").fetchone()['n']
    nophone=c.execute("SELECT COUNT(*) n FROM member_core WHERE status='Active' AND phone=''").fetchone()['n']
    return {'eligible':tot,'available':available,'in_progress':inopen,
            'completed':completed,'missed':missed,'other_done':other_done,'worked':worked,
            'refused_dq':refused,'no_phone':nophone}

@app.get('/api/dir/advocates')
def advocates_rollup(req: Request):
    u=who(req); need(u,'director'); c=db()
    out=[]
    for a in c.execute("SELECT email,display FROM users WHERE role='advocate' AND active=1"):
        em=a['email']
        r=c.execute("""SELECT
            SUM(CASE WHEN bm.state='pending' THEN 1 ELSE 0 END) pending,
            SUM(CASE WHEN bm.state='served' THEN 1 ELSE 0 END) served,
            SUM(CASE WHEN bm.state='callback' THEN 1 ELSE 0 END) callbacks,
            SUM(CASE WHEN bm.state='done' THEN 1 ELSE 0 END) done
            FROM batch_members bm JOIN batches b ON b.id=bm.batch_id
            WHERE b.advocate=? AND b.status='open'""",(em,)).fetchone()
        d=c.execute("""SELECT COUNT(*) n, SUM(CASE WHEN disposition LIKE 'Connected%' THEN 1 ELSE 0 END) conn,
            MAX(ts) last FROM dispositions WHERE actor=?""",(em,)).fetchone()
        t=c.execute("SELECT COUNT(*) n FROM dispositions WHERE actor=? AND ts LIKE ?",(em,now()[:10]+'%')).fetchone()
        due=c.execute("""SELECT COUNT(*) n FROM batch_members bm JOIN batches b ON b.id=bm.batch_id
            WHERE b.advocate=? AND b.status='open' AND bm.state='callback' AND bm.callback_at<=?""",(em,now())).fetchone()
        out.append({'email':em,'display':a['display'],'pending':r['pending'] or 0,'served':r['served'] or 0,
            'callbacks':r['callbacks'] or 0,'done_open':r['done'] or 0,'worked_total':d['n'] or 0,
            'connected_total':d['conn'] or 0,'today':t['n'] or 0,'due_now':due['n'] or 0,'last_activity':d['last'] or ''})
    return out

MEM_SORTS={'name':'last,first','age':'age','state':'state','conn':'conn','att':'att','last_conn':'last_conn','att_since':'att_since'}
@app.post('/api/dir/members')
async def members_browse(req: Request):
    u=who(req); need(u,'director')
    f=await req.json()
    w,p=filter_sql(f)
    w=w.replace(" AND member_id NOT IN (SELECT member_id FROM batch_members bm JOIN batches b ON b.id=bm.batch_id WHERE b.status='open' AND bm.state IN('pending','served','callback'))","")
    avail=f.get('avail') or 'all'
    OPEN_SUB="member_id IN (SELECT member_id FROM batch_members bm JOIN batches b ON b.id=bm.batch_id WHERE b.status='open' AND bm.state IN('pending','served','callback'))"
    if avail=='available': w+=f" AND NOT ({OPEN_SUB})"
    elif avail=='assigned': w+=f" AND ({OPEN_SUB})"
    elif avail=='worked': w+=" AND member_id IN (SELECT member_id FROM dispositions)"
    elif avail=='untouched': w+=" AND member_id NOT IN (SELECT member_id FROM batch_members)"
    q=(f.get('q') or '').strip()
    if q: w+=" AND (first||' '||last LIKE ? OR member_id LIKE ?)"; p+=[f'%{q}%',f'%{q}%']
    srt=MEM_SORTS.get(f.get('sort') or 'name','last,first'); dr='DESC' if f.get('dir')=='desc' else 'ASC'
    page=max(0,int(f.get('page') or 0))
    c=db()
    tot=c.execute(f"SELECT COUNT(*) n FROM member_core WHERE {w}",p).fetchone()['n']
    rows=c.execute(f"""SELECT m.member_id,m.first,m.last,m.age,m.state,m.quals,m.sflags,m.conn,m.att,m.last_conn,m.att_since,
        (SELECT b.advocate FROM batch_members bm JOIN batches b ON b.id=bm.batch_id WHERE bm.member_id=m.member_id AND b.status='open' AND bm.state IN('pending','served','callback') LIMIT 1) advocate,
        (SELECT bm.stage FROM batch_members bm JOIN batches b ON b.id=bm.batch_id WHERE bm.member_id=m.member_id ORDER BY b.id DESC LIMIT 1) stage,
        (SELECT d.disposition||' · '||substr(d.ts,6,11) FROM dispositions d WHERE d.member_id=m.member_id ORDER BY d.id DESC LIMIT 1) last_disp
        FROM member_core m WHERE {w} ORDER BY {srt} {dr} LIMIT 50 OFFSET ?""",p+[page*50]).fetchall()
    audit(u['email'],'browse_members',meta={'filters':{k:v for k,v in f.items() if v},'page':page,'returned':len(rows),'total':tot})
    return {'total':tot,'page':page,'rows':[dict(r) for r in rows]}

@app.get('/api/dir/member/{mid}')
def member_detail(mid:str, req: Request):
    u=who(req); need(u,'director'); c=db()
    m=c.execute("SELECT * FROM member_core WHERE member_id=?",(mid,)).fetchone()
    if not m: raise HTTPException(404,'no such member')
    hist=[dict(h) for h in c.execute("SELECT date,event_type,detail,cls FROM comm_hist WHERE member_id=? ORDER BY date DESC, rowid DESC LIMIT 15",(mid,))]
    ans=[dict(a) for a in c.execute("SELECT ts,stage,prompt,answer,actor FROM answers WHERE member_id=? ORDER BY id DESC LIMIT 30",(mid,))]
    bt=[dict(b) for b in c.execute("""SELECT b.id,b.name,b.advocate,b.status,bm.state,bm.stage,bm.callback_at,bm.hcp_date
        FROM batch_members bm JOIN batches b ON b.id=bm.batch_id WHERE bm.member_id=? ORDER BY b.id DESC""",(mid,))]
    d=dict(m); d['phone']='···'+ (d.pop('phone')[-4:] if d.get('phone') else '')
    audit(u['email'],'member_detail',mid)
    return {'member':d,'hist':hist,'answers':ans,'batches':bt}

@app.post('/api/dir/qual_counts')
async def qual_counts(req: Request):
    u = who(req); need(u,'director'); c=db()
    return {q: c.execute("SELECT COUNT(*) n FROM member_core WHERE status='Active' AND phone<>'' AND refused=0 AND ';'||quals||';' LIKE ?",(f'%;{q};%',)).fetchone()['n'] for q in QUAL_CHIPS}

@app.post('/api/dir/preview')
async def preview(req: Request):
    u = who(req); need(u,'director')
    f = await req.json(); w,p = filter_sql(f)
    n = db().execute(f"SELECT COUNT(*) c FROM member_core WHERE {w}", p).fetchone()['c']
    return {'count': n}

@app.post('/api/dir/batch')
async def make_batch(req: Request):
    u = who(req); need(u,'director')
    f = await req.json()
    adv = (f.get('advocate') or '').lower()
    c = db()
    if not c.execute("SELECT 1 FROM users WHERE email=? AND role='advocate' AND active=1",(adv,)).fetchone():
        raise HTTPException(400,'advocate not enrolled')
    size = max(1, min(int(f.get('size') or 25), 200))
    w,p = filter_sql(f)
    rows = c.execute(f"SELECT member_id FROM member_core WHERE {w} ORDER BY att ASC, last_conn DESC LIMIT ?", p+[size]).fetchall()
    if not rows: raise HTTPException(400,'no members match')
    cur = c.execute("INSERT INTO batches(name,advocate,created_by,created_at,script_hint) VALUES(?,?,?,?,?)",
        (f.get('name') or f'Batch {now()[:10]}', adv, u['email'], now(), f.get('script') or ''))
    bid = cur.lastrowid
    c.executemany("INSERT INTO batch_members(batch_id,member_id,seq) VALUES(?,?,?)",
        [(bid, r['member_id'], i) for i,r in enumerate(rows)])
    c.commit()
    audit(u['email'],'batch_create',batch_id=bid,meta={'n':len(rows),'advocate':adv,'filters':f})
    return {'batch_id': bid, 'assigned': len(rows)}

@app.post('/api/dir/push_assignments')
async def push_assignments(req: Request):
    """Dashboard 'push': create a batch per tagged advocate and log the assignment date on each member."""
    u=who(req); need(u,'director'); f=await req.json(); c=db()
    assignments=f.get('assignments') or {}     # {member_id: advocate_name}
    groups={}
    for mid,name in assignments.items():
        if name and mid: groups.setdefault(str(name).strip(),[]).append(mid)
    if not groups: raise HTTPException(400,'no assignments to push')
    users=[dict(r) for r in c.execute("SELECT email,display FROM users WHERE role='advocate' AND active=1")]
    def resolve(name):
        n=name.strip().lower()
        for r in users:
            if r['email'].lower()==n: return r['email']
        for r in users:
            if (r['display'] or '').lower()==n: return r['email']
        for r in users:
            if r['email'].split('@')[0].lower()==n: return r['email']
        return None
    OPEN="member_id IN (SELECT member_id FROM batch_members bm JOIN batches b ON b.id=bm.batch_id WHERE b.status='open' AND bm.state IN('pending','served','callback'))"
    today=now()[:10]; out=[]
    for name,mids in groups.items():
        email=resolve(name)
        if not email:
            out.append({'advocate':name,'resolved':None,'assigned':0,'skipped':len(mids),'note':'advocate not enrolled — add in Team panel (email or matching display name)'}); continue
        elig=[r['member_id'] for r in c.execute(f"SELECT member_id FROM member_core WHERE status='Active' AND phone<>'' AND refused=0 AND member_id IN ({','.join('?'*len(mids))}) AND NOT ({OPEN})", mids)]
        if not elig:
            out.append({'advocate':name,'resolved':email,'assigned':0,'skipped':len(mids),'note':'all ineligible or already in an open batch'}); continue
        bid=c.execute("INSERT INTO batches(name,advocate,created_by,created_at,script_hint) VALUES(?,?,?,?,?)",
            (f'Dashboard push {today} — {name}',email,u['email'],now(),'')).lastrowid
        c.executemany("INSERT INTO batch_members(batch_id,member_id,seq) VALUES(?,?,?)",[(bid,mm,i) for i,mm in enumerate(elig)])
        c.executemany("INSERT INTO comm_hist(member_id,date,event_type,detail,cls) VALUES(?,?,?,?,?)",
            [(mm,today,'Assigned to advocate',f'Assigned to {name} ({email}) by {u["display"]} — dashboard push','O') for mm in elig])
        out.append({'advocate':name,'resolved':email,'batch_id':bid,'assigned':len(elig),'skipped':len(mids)-len(elig)})
    c.commit(); audit(u['email'],'push_assignments',meta={'groups':len(groups),'result':out})
    return {'results':out}

@app.post('/api/dir/unassign_members')
async def unassign_members(req: Request):
    """Remove members from their open batch(es) after a push, and log the removal on each member."""
    u=who(req); need(u,'director'); f=await req.json(); c=db()
    mids=[m for m in (f.get('member_ids') or []) if m]
    if not mids: raise HTTPException(400,'no members to unassign')
    rows=[dict(r) for r in c.execute(f"""SELECT bm.batch_id,bm.member_id,b.advocate FROM batch_members bm JOIN batches b ON b.id=bm.batch_id
        WHERE b.status='open' AND bm.state IN('pending','callback') AND bm.member_id IN ({','.join('?'*len(mids))})""",mids)]
    removed=0
    for r in rows:
        cur=c.execute("UPDATE batch_members SET state='removed' WHERE batch_id=? AND member_id=? AND state IN('pending','callback')",(r['batch_id'],r['member_id']))
        if cur.rowcount:
            removed+=1
            c.execute("INSERT INTO comm_hist(member_id,date,event_type,detail,cls) VALUES(?,?,?,?,?)",
                (r['member_id'],now()[:10],'Unassigned from advocate',f'Removed from {r["advocate"]} by {u["display"]}','O'))
    c.commit(); audit(u['email'],'unassign_members',meta={'removed':removed,'requested':len(mids)})
    return {'removed':removed,'requested':len(mids)}

@app.post('/api/dir/import_batch')
async def import_batch(req: Request):
    """Load a batch CSV exported from the review dashboard: {name, advocate, member_ids:[...]}"""
    u = who(req); need(u,'director')
    f = await req.json()
    adv=(f.get('advocate') or '').lower(); mids=[m for m in (f.get('member_ids') or []) if m]
    c=db()
    if not c.execute("SELECT 1 FROM users WHERE email=? AND role='advocate' AND active=1",(adv,)).fetchone():
        raise HTTPException(400,'advocate not enrolled')
    ok=[r['member_id'] for r in c.execute(f"""SELECT member_id FROM member_core WHERE status='Active' AND phone<>'' AND refused=0
        AND member_id IN ({','.join('?'*len(mids))})
        AND member_id NOT IN (SELECT member_id FROM batch_members bm JOIN batches b ON b.id=bm.batch_id
            WHERE b.status='open' AND bm.state IN('pending','served','callback'))""", mids)] if mids else []
    if not ok: raise HTTPException(400,'no eligible members in list')
    cur=c.execute("INSERT INTO batches(name,advocate,created_by,created_at,script_hint) VALUES(?,?,?,?,?)",
        (f.get('name') or f'Imported {now()[:10]}', adv, u['email'], now(), f.get('script') or ''))
    bid=cur.lastrowid
    c.executemany("INSERT INTO batch_members(batch_id,member_id,seq) VALUES(?,?,?)",[(bid,m,i) for i,m in enumerate(ok)])
    c.commit(); audit(u['email'],'batch_import',batch_id=bid,meta={'requested':len(mids),'accepted':len(ok)})
    return {'batch_id':bid,'accepted':len(ok),'rejected':len(mids)-len(ok)}

@app.get('/api/dir/batches')
def batches(req: Request):
    u = who(req); need(u,'director')
    rows = db().execute("""SELECT b.*, 
      SUM(CASE WHEN bm.state='done' THEN 1 ELSE 0 END) done, COUNT(*) total,
      SUM(CASE WHEN bm.state='callback' THEN 1 ELSE 0 END) callbacks
      FROM batches b JOIN batch_members bm ON bm.batch_id=b.id GROUP BY b.id ORDER BY b.id DESC""").fetchall()
    return [dict(r) for r in rows]

@app.get('/api/dir/batch/{bid}')
def batch_detail(bid:int, req: Request):
    u = who(req); need(u,'director')
    c = db()
    disp = c.execute("""SELECT d.ts,d.actor,d.disposition,d.note,d.handle_secs,m.first,m.last,d.member_id
      FROM dispositions d JOIN member_core m USING(member_id) WHERE d.batch_id=? ORDER BY d.id DESC""",(bid,)).fetchall()
    summ = c.execute("SELECT disposition, COUNT(*) n FROM dispositions WHERE batch_id=? GROUP BY 1 ORDER BY 2 DESC",(bid,)).fetchall()
    left = c.execute("""SELECT m.first,m.last,m.state,bm.state bstate,bm.stage,bm.callback_at FROM batch_members bm
        JOIN member_core m USING(member_id) WHERE bm.batch_id=? AND bm.state IN('pending','served','callback')
        ORDER BY bm.state,bm.seq""",(bid,)).fetchall()
    return {'dispositions':[dict(r) for r in disp], 'summary':[dict(r) for r in summ], 'left':[dict(r) for r in left]}

@app.post('/api/dir/close_batch/{bid}')
def close_batch(bid:int, req: Request):
    u = who(req); need(u,'director')
    c=db(); c.execute("UPDATE batches SET status='closed' WHERE id=?",(bid,)); c.commit()
    audit(u['email'],'batch_close',batch_id=bid); return {'ok':True}

@app.post('/api/dir/user')
async def add_user(req: Request):
    u = who(req); need(u,'director')
    f = await req.json(); em=(f.get('email') or '').lower().strip()
    if not re.match(r'^[^@]+@[^@]+$', em): raise HTTPException(400,'bad email')
    c=db()
    ex=c.execute("SELECT role FROM users WHERE email=?",(em,)).fetchone()
    if ex and ex['role']=='director': raise HTTPException(400,'that email is the director — cannot convert to advocate')
    c.execute("INSERT OR REPLACE INTO users(email,role,display,active) VALUES(?,?,?,?)",
        (em, 'advocate', f.get('display') or em.split('@')[0], 1 if f.get('active',True) else 0)); c.commit()
    audit(u['email'],'user_upsert',meta={'email':em}); return {'ok':True}

@app.get('/api/dir/users')
def users(req: Request):
    u=who(req); need(u,'director')
    return [dict(r) for r in db().execute("SELECT email,role,display,active FROM users ORDER BY role,email")]

@app.get('/api/dir/flags')
def flags(req: Request):
    u=who(req); need(u,'director')
    c=db()
    fast = c.execute("SELECT ts,actor,member_id,disposition,handle_secs FROM dispositions WHERE handle_secs<? ORDER BY id DESC LIMIT 100",(MIN_HANDLE_SECS,)).fetchall()
    quick_conn = c.execute("""SELECT ts,actor,member_id,disposition,
        (julianday(ts)-julianday(call_click_at))*86400 secs_after_click
        FROM dispositions WHERE disposition LIKE 'Connected%' AND call_click_at IS NOT NULL
        AND (julianday(ts)-julianday(call_click_at))*86400 < ? ORDER BY id DESC LIMIT 100""",(CONNECT_MIN_SECS,)).fetchall()
    no_click = c.execute("""SELECT ts,actor,member_id,disposition FROM dispositions
        WHERE disposition NOT IN ('Skipped') AND call_click_at IS NULL AND text_click_at IS NULL
        ORDER BY id DESC LIMIT 100""").fetchall()
    return {'fast_dispositions':[dict(r) for r in fast],
            'connected_too_fast':[dict(r) for r in quick_conn],
            'disposition_without_any_click':[dict(r) for r in no_click]}

@app.get('/api/dir/scripts')
def get_scripts(req: Request):
    u=who(req); need(u,'director'); c=db()
    return {'scripts':[dict(r) for r in c.execute("SELECT * FROM scripts")],
            'questions':[dict(r) for r in c.execute("SELECT id,stage,seq,kind,text AS prompt,qtype,options FROM guide_items ORDER BY stage,seq")]}

@app.post('/api/dir/scripts')
async def save_scripts(req: Request):
    u=who(req); need(u,'director'); f=await req.json(); c=db()
    for sc in (f.get('scripts') or []):
        c.execute("UPDATE scripts SET title=?,body=? WHERE stage=?",(sc['title'],sc['body'],sc['stage']))
    for q in (f.get('questions') or []):
        c.execute("UPDATE guide_items SET text=?,qtype=?,options=? WHERE id=?",
                  (q['prompt'],q['qtype'],q.get('options',''),q['id']))
    c.commit(); audit(u['email'],'scripts_update'); return {'ok':True}

@app.get('/api/dir/funnel')
def funnel(req: Request):
    u=who(req); need(u,'director'); c=db()
    return [dict(r) for r in c.execute("""SELECT bm.stage, bm.state, COUNT(*) n FROM batch_members bm
        JOIN batches b ON b.id=bm.batch_id WHERE b.status='open' GROUP BY 1,2""")]

@app.get('/api/dir/answers')
def get_answers(req: Request):
    u=who(req); need(u,'director'); c=db()
    return [dict(r) for r in c.execute("""SELECT a.ts,a.actor,a.member_id,m.first,m.last,a.stage,a.prompt,a.answer
        FROM answers a JOIN member_core m USING(member_id) ORDER BY a.id DESC LIMIT 200""")]

@app.get('/api/dir/audit')
def get_audit(req: Request):
    u=who(req); need(u,'director')
    return [dict(r) for r in db().execute("SELECT * FROM activity ORDER BY id DESC LIMIT 300")]

def _export_records(c, date_from, date_to):
    """One record per completed guide call: the guide-completed disposition + its answers,
    joined by the [served_at, ts+1s] window (no schema needed; the idempotence guard keeps
    windows unambiguous going forward; legacy same-day duplicates collapse into one record)."""
    w=["d.disposition LIKE 'Connected — Guide completed%'"]; p=[]
    if date_from: w.append("date(d.ts)>=?"); p.append(date_from)
    if date_to:   w.append("date(d.ts)<=?"); p.append(date_to)
    disps=c.execute(f"""SELECT d.id,d.ts,d.actor,d.member_id,d.batch_id,d.disposition,d.note,d.served_at,d.handle_secs,
        m.first,m.last,b.name batch FROM dispositions d JOIN member_core m USING(member_id)
        LEFT JOIN batches b ON b.id=d.batch_id WHERE {' AND '.join(w)} ORDER BY d.ts""",p).fetchall()
    out=[]
    for d in disps:
        stage=(re.search(r'\((\w+)\)$',d['disposition']) or [None,'?'])[1]
        lo=d['served_at'] or (d['ts'][:10])                       # fallback: whole day
        hi=d['ts'][:19]+'~'                                       # '~' > any digit -> +1s-ish inclusive bound
        ans=c.execute("""SELECT a.prompt,a.answer,COALESCE(g.seq,999) seq FROM answers a
            LEFT JOIN guide_items g ON g.id=a.question_id
            WHERE a.member_id=? AND a.batch_id=? AND a.stage=? AND a.ts>=? AND a.ts<=?
            ORDER BY seq,a.id""",(d['member_id'],d['batch_id'],stage,lo,hi)).fetchall()
        out.append({'d':d,'stage':stage,'answers':ans})
    return out

@app.get('/api/dir/export_forms')
def export_forms(req: Request):
    """Proof-of-work export: per-member completed guide (Member ID · date · advocate · every Q→A).
    fmt=csv -> download; fmt=html -> printable packet (one form per page, print to PDF)."""
    u=who(req); need(u,'director'); c=db()
    qp=req.query_params
    fmt=(qp.get('fmt') or 'csv').lower()
    f_, t_ = (qp.get('from') or '')[:10], (qp.get('to') or '')[:10]
    recs=_export_records(c,f_,t_)
    audit(u['email'],'export_forms',meta={'fmt':fmt,'from':f_ or 'all','to':t_ or 'all','forms':len(recs)})
    if fmt=='html':
        import html as H
        e=H.escape
        forms=[]
        for r in recs:
            d=r['d']
            rows=''.join(f"<tr><td class='q'>{e(a['prompt'])}</td><td class='a'>{e(a['answer'])}</td></tr>" for a in r['answers'])
            forms.append(f"""<div class="form"><h2>{e(d['first'])} {e(d['last'])} <span class="mid">{e(d['member_id'])}</span></h2>
<div class="meta">{e(d['ts'][:16].replace('T',' '))} · advocate: {e(d['actor'])} · batch: {e(d['batch'] or '—')} · stage: <b>{e(r['stage'])}</b>
 · outcome: {e((d['note'] or '').split(' | ')[0])}{f" · handle: {int(d['handle_secs'])}s" if d['handle_secs'] else ''}</div>
<table><tr><th>Question</th><th>Answer</th></tr>{rows or '<tr><td colspan=2>(no recorded answers found)</td></tr>'}</table></div>""")
        page=("<!doctype html><html><head><meta charset='utf-8'><title>Advocacy call forms</title><style>"
              "body{font:13px system-ui,sans-serif;margin:24px;color:#111}"
              ".form{page-break-after:always;margin-bottom:28px}h2{margin:0 0 2px}.mid{color:#666;font-size:13px;font-weight:400}"
              ".meta{color:#444;font-size:12px;margin-bottom:8px}table{width:100%;border-collapse:collapse}"
              "td,th{border:1px solid #ccc;padding:5px 8px;vertical-align:top;text-align:left;font-size:12px}"
              ".q{width:55%}.a{font-weight:600}@media print{.noprint{display:none}}"
              f"</style></head><body><div class='noprint' style='margin-bottom:14px'><b>{len(recs)} completed guide call(s)</b>"
              " — Ctrl+P to print / save as PDF</div>"+''.join(forms)+"</body></html>")
        return HTMLResponse(page)
    # csv
    import csv, io
    def nx(s):  # neutralize spreadsheet formula injection in free-text cells (=, +, -, @ prefixes)
        s='' if s is None else str(s)
        return ("'"+s) if s[:1] in ('=','+','-','@') else s
    buf=io.StringIO(); wtr=csv.writer(buf,lineterminator='\n')
    wtr.writerow(['member_id','first','last','call_ts','advocate','batch','stage','outcome','handle_secs','q_seq','question','answer'])
    for r in recs:
        d=r['d']; base=[d['member_id'],nx(d['first']),nx(d['last']),d['ts'],d['actor'],nx(d['batch'] or ''),r['stage'],
                        nx((d['note'] or '').split(' | ')[0]),d['handle_secs'] or '']
        if r['answers']:
            for a in r['answers']: wtr.writerow(base+[a['seq'],nx(a['prompt']),nx(a['answer'])])
        else:
            wtr.writerow(base+['','',''])
    from fastapi import Response
    fname=f"advocacy_forms_{f_ or 'start'}_{t_ or 'now'}.csv"
    return Response(buf.getvalue(),media_type='text/csv',
        headers={'Content-Disposition':f'attachment; filename="{fname}"'})

# ---------------- advocate API ----------------
def current_card(c, email):
    return c.execute("""SELECT bm.batch_id,bm.member_id FROM batch_members bm JOIN batches b ON b.id=bm.batch_id
        WHERE b.advocate=? AND b.status='open' AND bm.state='served' LIMIT 1""",(email,)).fetchone()

def adv_scope(c, email, mid):
    """Member is actionable by this advocate: in one of their OPEN batches, not finished."""
    return c.execute("""SELECT bm.batch_id,bm.member_id,bm.state,bm.stage FROM batch_members bm
        JOIN batches b ON b.id=bm.batch_id
        WHERE b.advocate=? AND b.status='open' AND bm.member_id=? AND bm.state IN('pending','served','callback')
        ORDER BY bm.batch_id DESC LIMIT 1""",(email,mid)).fetchone()

_ENG=('CONDSYM','Advocate engagement (live)'); _OFFG=('CONDSYM','Motor complications — OFF / tremor')
CAPTURE_MAP = {  # guide (stage,seq) -> durable member event: the answer becomes a comm_hist row keyed by member_id,
 # which live-merges into the Review Dashboard timeline + filter facets (and the member cards, newest-first).
 # kind: M=medical  E=engagement  K=contact (Contact: prefix, cls 'O', never reaches the dashboard).
 # grp: (facet box, group) or None = timeline-only.  fan: check answers write one event per selected option.
 ('initial',3):  dict(attr='Sponsor consent', kind='E', grp=_ENG, fan=False),
 ('initial',7):  dict(attr='OFF disruptive confirmed', kind='M', grp=_OFFG, fan=False),
 ('initial',9):  dict(attr='OFF symptoms', kind='M', grp=_OFFG, fan=True),
 ('initial',10): dict(attr='OFF status', kind='M', grp=_OFFG, fan=False),
 ('initial',13): dict(attr='On oral levodopa', kind='M', grp=('TREATMENT','Oral dopaminergic therapy'), fan=False),
 ('initial',22): dict(attr='Contra: 5-HT3 antiemetic', kind='M', grp=None, fan=False),
 ('initial',24): dict(attr='Contra: apomorphine allergy', kind='M', grp=None, fan=False),
 ('initial',26): dict(attr='Contra: sulfite allergy', kind='M', grp=None, fan=False),
 ('initial',28): dict(attr='Contra: hydrochloric acid allergy', kind='M', grp=None, fan=False),
 ('initial',31): dict(attr='GOOD ON — description', kind='M', grp=None, fan=False),
 ('initial',32): dict(attr='GOOD ON — daily amount', kind='M', grp=None, fan=False),
 ('initial',40): dict(attr='Materials requested', kind='E', grp=_ENG, fan=False),
 ('initial',41): dict(attr='Materials preference', kind='K', grp=None, fan=False),
 ('initial',42): dict(attr='Circle of Care interest', kind='E', grp=_ENG, fan=False),
 ('pre_hcp',6):  dict(attr='Materials received', kind='E', grp=_ENG, fan=False),
 ('pre_hcp',13): dict(attr='OFF impact on relationships', kind='M', grp=_OFFG, fan=False),
 ('pre_hcp',15): dict(attr='Sponsor consent (pre-HCP)', kind='E', grp=_ENG, fan=False),
 ('pre_hcp',18): dict(attr='Contra: 5-HT3 antiemetic', kind='M', grp=None, fan=False),
 ('pre_hcp',20): dict(attr='Contra: apomorphine allergy', kind='M', grp=None, fan=False),
 ('pre_hcp',22): dict(attr='Contra: sulfite allergy', kind='M', grp=None, fan=False),
 ('pre_hcp',24): dict(attr='Contra: hydrochloric acid allergy', kind='M', grp=None, fan=False),
 ('pre_hcp',31): dict(attr='Materials requested', kind='E', grp=_ENG, fan=False),
 ('pre_hcp',32): dict(attr='Materials preference', kind='K', grp=None, fan=False),
 ('post_hcp',2): dict(attr='OFF status (post-HCP)', kind='M', grp=_OFFG, fan=False),
 ('post_hcp',3): dict(attr='Treatment change after HCP', kind='M', grp=('TREATMENT','Advocate capture — treatment (live)'), fan=True),
 ('post_hcp',9): dict(attr='Discussed ONAPGO with HCP', kind='E', grp=_ENG, fan=False),
 ('post_hcp',10):dict(attr='Barrier to ONAPGO discussion', kind='E', grp=_ENG, fan=True),
 ('post_hcp',11):dict(attr='ONAPGO concerns (verbatim)', kind='M', grp=None, fan=False),
 ('post_hcp',13):dict(attr='Materials requested', kind='E', grp=_ENG, fan=False),
 ('post_hcp',14):dict(attr='Materials preference', kind='K', grp=None, fan=False),
}
_HCP_ENT = dict(attr='Next HCP appointment', kind='E', grp=None, fan=False)   # any sched='hcp' question
BACKUP_DIR = os.environ.get('DB_BACKUP_DIR', os.path.join(os.path.dirname(os.path.abspath(DB)), 'db-backups'))

def _integrity_check():
    """Detect-only (Stage 0): quick_check the DB and log LOUDLY if it looks corrupt.
    Runs in a BACKGROUND thread a minute after startup, so it NEVER delays the port
    bind — a blocking quick_check on the ~18MB DB over a cold gcsfuse mount can exceed
    the Cloud Run startup probe (that caused a failed deploy). It does NOT auto-restore:
    during a rolling deploy the outgoing instance is still writing, so a boot-time check
    can see a transient torn read, and auto-restoring then would clobber live writes with
    a stale snapshot. Recovery is deliberate — bucket versioning + hourly snapshots in
    BACKUP_DIR."""
    try:
        corrupt = False; detail = None
        try:
            c = sqlite3.connect(DB, timeout=15.0)
            try:
                r = c.execute("PRAGMA quick_check").fetchone()
            finally:
                c.close()
            if not (r and str(r[0]).lower() == 'ok'): corrupt = True; detail = (r and r[0])
        except sqlite3.DatabaseError as e:            # severe corruption makes quick_check itself raise
            corrupt = True; detail = str(e)
        if corrupt:
            snaps = sorted(f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')) if os.path.isdir(BACKUP_DIR) else []
            print('CRITICAL: app.db failed integrity check (%r). Newest snapshot: %s (%s). App is '
                  'serving; if this is NOT a transient mid-deploy read, restore deliberately from a '
                  'db-backups/ snapshot or a prior bucket version.'
                  % (detail, (snaps[-1] if snaps else '(none)'), BACKUP_DIR))
        else:
            print('integrity check: ok')
    except Exception as e:
        print('integrity check skipped:', e)

def _start_integrity_check():
    try:
        t = threading.Timer(60.0, _integrity_check); t.daemon = True; t.start()   # after the deploy settles; non-blocking
    except Exception as e:
        print('integrity check not scheduled:', e)
_start_integrity_check()

def _capture_startup():
    """Log-only sanity: every CAPTURE_MAP key must be a live question. Plus one additive index (idempotent)."""
    try:
        c=db()
        have={(r['stage'],r['seq']) for r in c.execute("SELECT stage,seq FROM guide_items WHERE kind='q'")}
        missing=[k for k in CAPTURE_MAP if k not in have]
        if missing: print('WARN: CAPTURE_MAP keys with no matching guide question:', missing)
        c.execute("CREATE INDEX IF NOT EXISTS ix_ch_et ON comm_hist(event_type, date)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_ans_export ON answers(member_id, batch_id, stage, ts)")
        # punch clock + recurring schedule (additive; live DB gets them here, no migration)
        c.execute("CREATE TABLE IF NOT EXISTS time_punches(id INTEGER PRIMARY KEY, actor TEXT, action TEXT, ts TEXT, signature TEXT, on_time INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_punch_actor ON time_punches(actor, id)")
        c.execute("CREATE TABLE IF NOT EXISTS staff_schedule(email TEXT PRIMARY KEY, blocks TEXT, days TEXT, tz TEXT, ot_permitted INTEGER DEFAULT 0, ot_multiple REAL DEFAULT 1.5, ot_hours REAL DEFAULT 0, updated_by TEXT, updated_ts TEXT)")
        # director-assigned member tiers (synced from the Review Dashboard; visible to advocates + monitor)
        c.execute("CREATE TABLE IF NOT EXISTS member_tiers(member_id TEXT PRIMARY KEY, tier TEXT, updated_by TEXT, updated_ts TEXT)")
        # backfill: any member already marked 'Bad Number' becomes do-not-call (idempotent; flips only 0->1)
        c.execute("UPDATE member_core SET refused=1 WHERE refused=0 AND member_id IN (SELECT DISTINCT member_id FROM dispositions WHERE disposition='Bad Number')")
        c.commit()
    except Exception as e: print('capture startup check skipped:', e)
_capture_startup()
def build_card(c, u, bid, mid):
    m = c.execute("SELECT * FROM member_core WHERE member_id=?",(mid,)).fetchone()
    hist = c.execute("SELECT date,event_type,detail,cls FROM comm_hist WHERE member_id=? ORDER BY date DESC, rowid DESC LIMIT 15",(mid,)).fetchall()
    b = c.execute("SELECT name,script_hint FROM batches WHERE id=?",(bid,)).fetchone()
    bm = c.execute("SELECT stage,hcp_date,stage_attempts FROM batch_members WHERE batch_id=? AND member_id=?",(bid,mid)).fetchone()
    stage = bm['stage'] or 'initial'
    sc = c.execute("SELECT title,body FROM scripts WHERE stage=?",(stage,)).fetchone()
    qs = [dict(q) for q in c.execute("SELECT id,seq,kind,text,qtype,options,show_qid,show_vals,dq_vals,sched FROM guide_items WHERE stage=? ORDER BY seq",(stage,))]
    left = c.execute("SELECT COUNT(*) n FROM batch_members WHERE batch_id=? AND state='pending'",(bid,)).fetchone()['n']
    d = dict(m)
    num = d.pop('phone')                      # masked in UI; full number travels only in call_url + phone_e164 (the Text copy-paste source)
    call = 'https://voice.google.com/u/0/calls?a=nc,' + urllib.parse.quote(num)
    body=(sc['body'] if sc else '').replace('{first}',m['first']).replace('{hcp_date}',bm['hcp_date'] or 'your upcoming date').replace('{advocate}',u['display'])
    sms=SMS_TEMPLATES.get(stage,SMS_TEMPLATES['initial']).replace('{first}',m['first']).replace('{advocate}',u['display'])
    d.update(batch_id=bid, batch=b['name'], script=b['script_hint'], remaining=left, sms_text=(sms if SMS_ENABLED else ''),
             call_url=call, text_url=('https://voice.google.com/u/0/messages' if SMS_ENABLED else ''),  # GV has no compose-to-number URL; advocate pastes the copied number
             phone_e164=(num if SMS_ENABLED else ''), served_at=now(),
             stage=stage, hcp_date=bm['hcp_date'], stage_attempt=(bm['stage_attempts'] or 0)+1, max_attempts=MAX_STAGE_ATTEMPTS,
             stage_title=(sc['title'] if sc else stage), stage_script=body, guide=qs,
             hist=[dict(h) for h in hist])
    return d

STAGE_ORD={'pre_hcp':0,'post_hcp':1,'initial':2}
@app.get('/api/adv/list')
def adv_list(req: Request, view: str='queue', page: int=0):
    u=who(req); need(u,'advocate'); email=u['email']; c=db()
    page=max(0,int(page)); PER=15
    c.execute("""UPDATE batch_members SET stage='post_hcp', stage_attempts=0,
        callback_at=date(hcp_date,'+'||? ||' days')||'T09:00'
        WHERE stage='pre_hcp' AND hcp_date IS NOT NULL AND hcp_date<date('now','localtime')
        AND state IN('callback','pending')""",(POST_DELAY_DAYS,)); c.commit()
    if view=='done':
        rows=c.execute("""SELECT d.member_id, m.first,m.last,m.age,m.state st,m.quals, d.disposition, d.ts
            FROM dispositions d JOIN member_core m USING(member_id)
            WHERE d.actor=? AND d.ts LIKE ? ORDER BY d.id DESC LIMIT ? OFFSET ?""",(email,now()[:10]+'%',PER,page*PER)).fetchall()
        tot=c.execute("SELECT COUNT(*) n FROM dispositions WHERE actor=? AND ts LIKE ?",(email,now()[:10]+'%')).fetchone()['n']
        out=[dict(r) for r in rows]
    else:
        # 'priority' = every scheduled callback (due or upcoming), whether or not it's been opened
        # (state served after open) — these ride at the top of the advocate's list until an outcome is
        # logged. 'queue' is the plain to-call list: pending/served with NO scheduled callback, so a
        # member is never in both bands. ('due'/'callbacks' kept for internal/back-compat, no UI tab.)
        w={"priority":"bm.state IN('callback','served') AND bm.callback_at IS NOT NULL",
           "queue":"bm.state IN('pending','served') AND bm.callback_at IS NULL",
           "due":"bm.state IN('callback','served') AND bm.callback_at IS NOT NULL AND replace(bm.callback_at,'T',' ')<=datetime('now','localtime')",
           "callbacks":"bm.state='callback' AND replace(bm.callback_at,'T',' ')>datetime('now','localtime')"}.get(view)
        if not w: raise HTTPException(400,'bad view')
        base=f"""FROM batch_members bm JOIN batches b ON b.id=bm.batch_id JOIN member_core m ON m.member_id=bm.member_id
            WHERE b.advocate=? AND b.status='open' AND {w}"""
        tot=c.execute(f"SELECT COUNT(*) n {base}",(email,)).fetchone()['n']
        rows=c.execute(f"""SELECT bm.member_id, m.first,m.last,m.age,m.state st,m.quals,
            (SELECT COUNT(*) FROM dispositions d WHERE d.member_id=bm.member_id AND d.disposition LIKE 'Connected%') conn,
            (SELECT COUNT(*) FROM dispositions d WHERE d.member_id=bm.member_id AND d.disposition<>'Skipped') att,
            bm.stage,bm.state bstate,bm.stage_attempts,bm.callback_at,bm.hcp_date,b.name batch,
            (SELECT t.tier FROM member_tiers t WHERE t.member_id=bm.member_id) tier,
            (SELECT d.disposition FROM dispositions d WHERE d.member_id=bm.member_id ORDER BY d.id DESC LIMIT 1) outcome,
            (SELECT d.note FROM dispositions d WHERE d.member_id=bm.member_id ORDER BY d.id DESC LIMIT 1) note
            {base} ORDER BY CASE WHEN bm.callback_at IS NOT NULL THEN bm.callback_at ELSE '9' END,
            CASE bm.stage WHEN 'pre_hcp' THEN 0 WHEN 'post_hcp' THEN 1 ELSE 2 END, bm.seq LIMIT ? OFFSET ?""",
            (email,PER,page*PER)).fetchall()
        out=[dict(r) for r in rows]
    audit(email,'adv_list',meta={'view':view,'page':page,'ids':[r['member_id'] for r in out]})
    return {'total':tot,'page':page,'per':PER,'rows':out}

@app.get('/api/adv/open/{mid}')
def adv_open(mid: str, req: Request):
    u=who(req); need(u,'advocate'); c=db()
    sc=adv_scope(c,u['email'],mid)
    if not sc: raise HTTPException(403,'not in your assigned pool')
    if sc['state'] in ('pending','callback'):
        c.execute("UPDATE batch_members SET state='served' WHERE batch_id=? AND member_id=?",(sc['batch_id'],mid)); c.commit()
    audit(u['email'],'open',mid,sc['batch_id'])
    return build_card(c,u,sc['batch_id'],mid)

@app.get('/api/adv/next')
def nxt(req: Request):
    u = who(req); need(u,'advocate'); email=u['email']; c=db()
    cur = current_card(c, email)
    if not cur:
        cur = c.execute("""SELECT bm.batch_id,bm.member_id FROM batch_members bm JOIN batches b ON b.id=bm.batch_id
            WHERE b.advocate=? AND b.status='open' AND bm.state='callback' AND bm.callback_at<=?
            ORDER BY bm.callback_at LIMIT 1""",(email,now())).fetchone()
    if not cur:
        cur = c.execute("""SELECT bm.batch_id,bm.member_id FROM batch_members bm JOIN batches b ON b.id=bm.batch_id
            WHERE b.advocate=? AND b.status='open' AND bm.state='pending'
            ORDER BY bm.batch_id, bm.seq LIMIT 1""",(email,)).fetchone()
    if not cur:
        return {'empty': True}
    bid, mid = cur['batch_id'], cur['member_id']
    c.execute("UPDATE batch_members SET state='served' WHERE batch_id=? AND member_id=?",(bid,mid)); c.commit()
    audit(email,'serve',mid,bid)
    return build_card(c,u,bid,mid)

@app.get('/api/adv/guide/{mid}')
def adv_guide(mid: str, req: Request, stage: str='initial'):
    u=who(req); need(u,'advocate'); c=db()
    sc=adv_scope(c,u['email'],mid)
    if not sc: raise HTTPException(403,'not in your assigned pool')
    if stage not in ('initial','pre_hcp','post_hcp'): raise HTTPException(400,'bad stage')
    m_=c.execute("SELECT first,doctor FROM member_core WHERE member_id=?",(mid,)).fetchone()
    bm=c.execute("SELECT hcp_date FROM batch_members WHERE batch_id=? AND member_id=?",(sc['batch_id'],mid)).fetchone()
    s=c.execute("SELECT title,body FROM scripts WHERE stage=?",(stage,)).fetchone()
    qs=[dict(q) for q in c.execute("SELECT id,seq,kind,text,qtype,options,show_qid,show_vals,dq_vals,sched FROM guide_items WHERE stage=? ORDER BY seq",(stage,))]
    body=(s['body'] if s else '').replace('{first}',m_['first']).replace('{hcp_date}',bm['hcp_date'] or 'your upcoming date').replace('{advocate}',u['display'])
    audit(u['email'],'guide_view',mid,sc['batch_id'],meta={'stage':stage})
    return {'stage':stage,'stage_title':(s['title'] if s else stage),'stage_script':body,'guide':qs}

@app.post('/api/adv/click')
async def click(req: Request):
    u=who(req); need(u,'advocate'); f=await req.json(); c=db()
    sc = adv_scope(c, u['email'], f.get('member_id') or '')
    if not sc: raise HTTPException(403,'not in your assigned pool')
    if f.get('kind')=='text' and not SMS_ENABLED: raise HTTPException(403,'texting disabled for the pilot')
    audit(u['email'], 'click_'+('call' if f.get('kind')=='call' else 'text'), sc['member_id'], sc['batch_id'])
    return {'ok': True, 'ts': now()}

STAGE_NEXT = {'initial':'pre_hcp','pre_hcp':'post_hcp','post_hcp':'complete'}
PRE_WINDOW_DAYS, POST_DELAY_DAYS = 10, 28   # pre window opens HCP-10d; post opens HCP+4wks
MAX_STAGE_ATTEMPTS, POST_RETRY_DAYS = 3, 3   # ≤3 serves per window; post retries 3 days apart
INITIAL_RETRY_DAYS = 3                        # initial no-connect retries 3 days apart, ≤3 attempts then retire
SMS_ENABLED = True  # texting ON — unbranded outreach texts (opt-out included), no MLR/PRC required per program owner
SMS_TEMPLATES = {  # unbranded outreach texts (opt-out included) — NON-branded, no MLR/PRC required; director-editable copy
 'initial':"Hi {first}, this is {advocate} with Parkinson's Community. I tried reaching you by phone about the information you requested. When's a good time to talk? Reply STOP to opt out.",
 'pre_hcp':"Hi {first}, {advocate} from Parkinson's Community. Following up before your upcoming doctor's appointment — I'd like to help you prepare. When can we talk? Reply STOP to opt out.",
 'post_hcp':"Hi {first}, {advocate} from Parkinson's Community, checking in after your appointment. When's a good time for a quick call? Reply STOP to opt out.",
}

def next_pre_retry(hcp, attempts):
    'space remaining pre-window attempts between today and the appointment'
    today=datetime.date.today(); d0=datetime.date.fromisoformat(hcp)
    left=(d0-today).days
    if left<=1 or attempts>=MAX_STAGE_ATTEMPTS: return None
    gap=max(1, left//(MAX_STAGE_ATTEMPTS-attempts+1))
    return (today+datetime.timedelta(days=gap)).isoformat()+'T09:00'

@app.post('/api/adv/guide_submit')
async def guide_submit(req: Request):
    u=who(req); need(u,'advocate'); f=await req.json(); c=db()
    sc = adv_scope(c, u['email'], f.get('member_id') or '')
    if not sc: raise HTTPException(403,'not in your assigned pool')
    bid, mid = sc['batch_id'], sc['member_id']
    bm=c.execute("SELECT stage,hcp_date FROM batch_members WHERE batch_id=? AND member_id=?",(bid,mid)).fetchone()
    stage=bm['stage'] or 'initial'
    override=f.get('stage')
    if override in ('initial','pre_hcp','post_hcp') and override!=stage:
        stage=override   # advocate corrected the call type (appt happened earlier / hasn't happened yet)
    # idempotence guard — BEFORE any insert. Keyed on served_at (the card-session identity): a
    # double-click or network retry re-posts the SAME served_at and is swallowed; a genuinely new
    # conversation re-opens the card (fresh served_at from build_card) and records normally —
    # including legit same-day same-stage repeats (stage switcher, same-day re-scheduled pre-HCP).
    served=f.get('served_at') or now()
    prev=c.execute("""SELECT note FROM dispositions WHERE member_id=? AND batch_id=? AND disposition=?
        AND served_at=? ORDER BY id DESC LIMIT 1""",
        (mid,bid,'Connected — Guide completed ('+stage+')',served)).fetchone()
    if prev:
        audit(u['email'],'guide_submit',mid,bid,meta={'stage':stage,'dup':True,'served_at':served})
        return {'ok':True,'dup':True,'outcome':(prev['note'] or '').split(' | ')[0]}
    hcp=None; dq=False; lines=[]; call_doctor_yes=False
    for a in (f.get('answers') or []):
        it=c.execute("SELECT * FROM guide_items WHERE id=? AND stage=? AND kind='q'",(a.get('qid'),stage)).fetchone()
        if not it: continue
        val=str(a.get('answer') or '').strip()[:800]
        if not val: continue
        c.execute("INSERT INTO answers(ts,actor,member_id,batch_id,stage,question_id,prompt,answer) VALUES(?,?,?,?,?,?,?,?)",
            (now(),u['email'],mid,bid,stage,it['id'],it['text'][:200],val))
        lines.append(f"{it['text'][:60]} -> {val}")
        ent=(_HCP_ENT if it['sched']=='hcp' else CAPTURE_MAP.get((stage,it['seq'])))
        if ent:
            pre,cls=('Contact: ','O') if ent['kind']=='K' else ('Clinical: ','M')
            if ent['fan'] and it['qtype']=='check':   # one durable event per selected option; exact-match
                opts=(it['options'] or '').split('|') # against the live options drops truncation fragments
                vals=[p.strip() for p in val.split('; ') if p.strip() in opts] or [val[:200]]
            else:
                vals=[val[:200]]
            for v in vals:
                c.execute("INSERT INTO comm_hist(member_id,date,event_type,detail,cls) VALUES(?,?,?,?,?)",
                    (mid,now()[:10],pre+ent['attr'],v,cls))
        if it['sched']=='hcp':
            try: hcp=datetime.date.fromisoformat(val[:10]).isoformat()
            except ValueError: pass  # invalid calendar date -> ignore, advocate can re-ask
        if it['dq_vals'] and it['dq_vals'] in val: dq=True
        if stage=='post_hcp' and it['seq']==5 and val=='Yes': call_doctor_yes=True
    try: handle=(datetime.datetime.fromisoformat(now())-datetime.datetime.fromisoformat(served)).total_seconds()
    except: handle=None
    today=datetime.date.today()
    if dq:
        c.execute("UPDATE batch_members SET state='done', stage='dq' WHERE batch_id=? AND member_id=?",(bid,mid))
        c.execute("UPDATE member_core SET refused=1 WHERE member_id=?",(mid,))
        outcome='DQ — contraindication'
    elif stage=='initial':
        if hcp:
            cb=(datetime.date.fromisoformat(hcp)-datetime.timedelta(days=PRE_WINDOW_DAYS))
            cb=max(cb,today).isoformat()+'T09:00'
            c.execute("UPDATE batch_members SET state='callback', callback_at=?, stage='pre_hcp', hcp_date=?, stage_attempts=0 WHERE batch_id=? AND member_id=?",(cb,hcp,bid,mid))
            outcome=f'Educated; Pre-HCP scheduled (appt {hcp})'
        else:
            c.execute("UPDATE batch_members SET state='done', stage='no_appt' WHERE batch_id=? AND member_id=?",(bid,mid))
            outcome='Educated; no appointment captured'
    elif stage=='pre_hcp':
        hcp=hcp or bm['hcp_date']
        if hcp:
            cb=(datetime.date.fromisoformat(hcp)+datetime.timedelta(days=POST_DELAY_DAYS)).isoformat()+'T09:00'
            c.execute("UPDATE batch_members SET state='callback', callback_at=?, stage='post_hcp', hcp_date=?, stage_attempts=0 WHERE batch_id=? AND member_id=?",(cb,hcp,bid,mid))
            outcome=f'Pre-HCP done; Post-HCP scheduled (appt {hcp})'
        else:
            c.execute("UPDATE batch_members SET state='done', stage='no_appt' WHERE batch_id=? AND member_id=?",(bid,mid))
            outcome='Pre-HCP done; appointment cancelled/no date'
    else:  # post_hcp
        if hcp:  # new appointment -> new cycle
            cb=(datetime.date.fromisoformat(hcp)-datetime.timedelta(days=PRE_WINDOW_DAYS))
            cb=max(cb,today).isoformat()+'T09:00'
            c.execute("UPDATE batch_members SET state='callback', callback_at=?, stage='pre_hcp', hcp_date=?, stage_attempts=0 WHERE batch_id=? AND member_id=?",(cb,hcp,bid,mid))
            outcome=f'Post-HCP done; new cycle (appt {hcp})'
        elif call_doctor_yes:
            cb=(today+datetime.timedelta(days=7)).isoformat()+'T09:00'
            c.execute("UPDATE batch_members SET state='callback', callback_at=?, stage='post_hcp', stage_attempts=0 WHERE batch_id=? AND member_id=?",(cb,bid,mid))
            outcome='Post-HCP done; 1-week follow-up to get new appointment'
        else:
            c.execute("UPDATE batch_members SET state='done', stage='complete' WHERE batch_id=? AND member_id=?",(bid,mid))
            outcome='Post-HCP done; sequence complete'
    c.execute("""INSERT INTO dispositions(ts,actor,member_id,batch_id,disposition,note,served_at,call_click_at,text_click_at,handle_secs)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",(now(),u['email'],mid,bid,'Connected — Guide completed ('+stage+')',
        outcome+' | '+'; '.join(lines)[:300],served,f.get('call_click_at'),f.get('text_click_at'),handle))
    c.execute("INSERT INTO comm_hist(member_id,date,event_type,detail,cls) VALUES(?,?,?,?,?)",
        (mid,now()[:10],f'{stage.replace("_"," ").title()} Call ({u["display"]})',outcome,'C'))
    c.commit()
    audit(u['email'],'guide_submit',mid,bid,meta={'stage':stage,'scheduled_stage':bm['stage'] or 'initial','override':bool(override and override!=(bm['stage'] or 'initial')),'answers':len(lines),'outcome':outcome})
    return {'ok':True,'outcome':outcome}

DISPOSITIONS = ['Connected — Educated','Connected — Callback Scheduled','Connected — Not Interested',
                'Reached someone else','Health event / hospitalized','Appointment changed',
                'Left Voicemail','No Answer','Bad Number','Refused / Remove','DQ — Clinical','Deceased','Skipped']
SITUATION_DAYS = {'Reached someone else':2,'Health event / hospitalized':14}  # member stays in sequence; auto-reschedule

@app.post('/api/adv/disposition')
async def disposition(req: Request):
    u=who(req); need(u,'advocate'); f=await req.json(); c=db()
    sc = adv_scope(c, u['email'], f.get('member_id') or '')
    if not sc: raise HTTPException(403,'not in your assigned pool')
    cur = sc
    d = f.get('disposition')
    if d not in DISPOSITIONS: raise HTTPException(400,'unknown disposition')
    if d=='Skipped' and not (f.get('note') or '').strip(): raise HTTPException(400,'skip requires a reason')
    bid, mid = cur['batch_id'], cur['member_id']
    served = f.get('served_at') or now()
    # idempotence guard (same pattern as guide_submit): an IDENTICAL outcome re-saved from the same
    # card session (same served_at) is a repeat click — skip it (no duplicate row, no burned stage
    # attempt, no inflated counts). A DIFFERENT outcome on the same card still records (correction).
    if c.execute("SELECT 1 FROM dispositions WHERE member_id=? AND batch_id=? AND disposition=? AND served_at=? LIMIT 1",
                 (mid,bid,d,served)).fetchone():
        audit(u['email'],'disposition',mid,bid,meta={'disposition':d,'dup':True,'served_at':served})
        return {'ok':True,'dup':True}
    try: handle = (datetime.datetime.fromisoformat(now())-datetime.datetime.fromisoformat(served)).total_seconds()
    except: handle = None
    cb = f.get('callback_at') if d in ('Connected — Callback Scheduled','Reached someone else','Health event / hospitalized') else None
    if d=='Connected — Callback Scheduled' and not cb: raise HTTPException(400,'Callback Scheduled requires a valid date/time')
    if cb and d in ('Connected — Callback Scheduled','Reached someone else','Health event / hospitalized'):
        try:
            cbdt=datetime.datetime.fromisoformat(str(cb))
            # 24h grace on the lower bound: advocate enters a local wall-clock time while the server
            # clock is UTC (advocates span US Central + Honduras), so a valid same-day callback can
            # read as slightly 'past' — accept it rather than 400 the whole disposition.
            lo=datetime.datetime.now()-datetime.timedelta(hours=24)
            hi=datetime.datetime.now()+datetime.timedelta(days=180)
            if not (lo <= cbdt <= hi): raise ValueError
            cb=cbdt.isoformat(timespec='minutes')
        except (ValueError,TypeError):
            raise HTTPException(400,'Callback Scheduled requires a valid date/time within the next 180 days')
    # situational reschedule: advocate's chosen time, else a sensible default (member stays in sequence)
    if d in SITUATION_DAYS and not cb:
        cb=(datetime.datetime.now()+datetime.timedelta(days=SITUATION_DAYS[d])).isoformat(timespec='minutes')
    appt_new=None
    if d=='Appointment changed':
        try: appt_new=datetime.date.fromisoformat((f.get('hcp_date') or '')[:10])
        except ValueError: raise HTTPException(400,'Appointment changed needs the new appointment date')
    c.execute("""INSERT INTO dispositions(ts,actor,member_id,batch_id,disposition,note,served_at,call_click_at,text_click_at,handle_secs)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",(now(),u['email'],mid,bid,d,(f.get('note') or '')[:400],served,
        f.get('call_click_at'),f.get('text_click_at'),handle))
    bm=c.execute("SELECT stage,hcp_date,stage_attempts FROM batch_members WHERE batch_id=? AND member_id=?",(bid,mid)).fetchone()
    stage=bm['stage'] or 'initial'; hcp=bm['hcp_date']; attempts=(bm['stage_attempts'] or 0)+1
    terminal = d in ('Refused / Remove','DQ — Clinical','Deceased','Bad Number') or d.startswith('Connected')
    if d=='Appointment changed' and appt_new:
        newcb=max(appt_new-datetime.timedelta(days=PRE_WINDOW_DAYS),datetime.date.today()).isoformat()+'T09:00'
        c.execute("UPDATE batch_members SET state='callback', callback_at=?, hcp_date=?, stage='pre_hcp', stage_attempts=0 WHERE batch_id=? AND member_id=?",(newcb,appt_new.isoformat(),bid,mid))
        c.execute("INSERT INTO comm_hist(member_id,date,event_type,detail,cls) VALUES(?,?,?,?,?)",
            (mid,now()[:10],f'Appointment updated ({u["display"]})',f'New HCP appt {appt_new.isoformat()} — Pre-HCP re-scheduled','O'))
    elif cb:
        c.execute("UPDATE batch_members SET state='callback', callback_at=?, stage_attempts=? WHERE batch_id=? AND member_id=?",(cb,(bm['stage_attempts'] or 0),bid,mid))
    elif stage=='pre_hcp' and not terminal and hcp:
        retry=next_pre_retry(hcp,attempts)
        if retry:
            c.execute("UPDATE batch_members SET state='callback', callback_at=?, stage_attempts=? WHERE batch_id=? AND member_id=?",(retry,attempts,bid,mid))
        else:  # window exhausted → roll to post-HCP schedule
            post=(datetime.date.fromisoformat(hcp)+datetime.timedelta(days=POST_DELAY_DAYS)).isoformat()+'T09:00'
            c.execute("UPDATE batch_members SET state='callback', callback_at=?, stage='post_hcp', stage_attempts=0 WHERE batch_id=? AND member_id=?",(post,bid,mid))
            c.execute("INSERT INTO comm_hist(member_id,date,event_type,detail,cls) VALUES(?,?,?,?,?)",
                (mid,now()[:10],'Pre-HCP window closed','Not reached in 3 attempts before appointment — rolled to post-HCP','O'))
    elif stage=='post_hcp' and not terminal:
        if attempts<MAX_STAGE_ATTEMPTS:
            retry=(datetime.date.today()+datetime.timedelta(days=POST_RETRY_DAYS)).isoformat()+'T09:00'
            c.execute("UPDATE batch_members SET state='callback', callback_at=?, stage_attempts=? WHERE batch_id=? AND member_id=?",(retry,attempts,bid,mid))
        else:
            c.execute("UPDATE batch_members SET state='done', stage='missed_post' WHERE batch_id=? AND member_id=?",(bid,mid))
            c.execute("INSERT INTO comm_hist(member_id,date,event_type,detail,cls) VALUES(?,?,?,?,?)",
                (mid,now()[:10],'Post-HCP window closed','Not reached in 3 post-HCP attempts','O'))
    elif stage=='initial' and not terminal:
        if attempts<MAX_STAGE_ATTEMPTS:
            retry=(datetime.date.today()+datetime.timedelta(days=INITIAL_RETRY_DAYS)).isoformat()+'T09:00'
            c.execute("UPDATE batch_members SET state='callback', callback_at=?, stage_attempts=? WHERE batch_id=? AND member_id=?",(retry,attempts,bid,mid))
        else:
            c.execute("UPDATE batch_members SET state='done', stage='no_contact' WHERE batch_id=? AND member_id=?",(bid,mid))
            c.execute("INSERT INTO comm_hist(member_id,date,event_type,detail,cls) VALUES(?,?,?,?,?)",
                (mid,now()[:10],'Initial outreach closed','Not reached in 3 attempts','O'))
    else:
        c.execute("UPDATE batch_members SET state='done' WHERE batch_id=? AND member_id=?",(bid,mid))
    # write back into the master log table inside app.db mirror (export to CRM_Master.db is a director action)
    c.execute("INSERT INTO comm_hist(member_id,date,event_type,detail,cls) VALUES(?,?,?,?,?)",
        (mid, now()[:10], f'Advocate Call ({u["display"]})', d + ((' — '+f.get('note')) if f.get('note') else ''),
         'C' if (d.startswith('Connected') or d in('Reached someone else','Appointment changed')) else ('B' if d=='Bad Number' else 'A' if d in('Left Voicemail','No Answer') else 'O')))
    if d in ('Refused / Remove','Deceased','Bad Number'):   # Bad Number -> do-not-call: flag it so it's excluded from future pushes + tracked by the director
        c.execute("UPDATE member_core SET refused=1 WHERE member_id=?",(mid,))
    c.commit()
    audit(u['email'],'disposition',mid,bid,meta={'d':d,'handle':handle})
    return {'ok':True}

@app.get('/api/adv/summary')
def adv_summary(req: Request):
    u=who(req); need(u,'advocate'); c=db()
    today = now()[:10]
    r = c.execute("""SELECT COUNT(*) n, SUM(CASE WHEN disposition LIKE 'Connected%' THEN 1 ELSE 0 END) conn
        FROM dispositions WHERE actor=? AND ts LIKE ?""",(u['email'],today+'%')).fetchone()
    f = c.execute("""SELECT SUM(CASE WHEN ts LIKE ? THEN 1 ELSE 0 END) ftoday, COUNT(*) fmonth
        FROM dispositions WHERE actor=? AND disposition LIKE 'Connected — Guide completed%' AND ts LIKE ?""",
        (today+'%',u['email'],today[:7]+'%')).fetchone()
    return {'today': r['n'] or 0, 'connected': r['conn'] or 0,
            'forms_today': f['ftoday'] or 0, 'forms_month': f['fmonth'] or 0}

# ================= punch clock + recurring schedule + OT policy =================
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo=None
DEFAULT_TZ='America/Denver'; GRACE_MIN=15
_TZLBL={'America/Denver':'MTN','America/Chicago':'CTN','America/New_York':'ETN','America/Los_Angeles':'PTN','America/Tegucigalpa':'HN'}
_DABBR={'1':'M','2':'Tu','3':'W','4':'Th','5':'F','6':'Sa','7':'Su'}
def _utcnow(): return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
def _tz(name):
    if not ZoneInfo: return datetime.timezone.utc
    try: return ZoneInfo(name or DEFAULT_TZ)
    except Exception:
        try: return ZoneInfo(DEFAULT_TZ)
        except Exception: return datetime.timezone.utc
def _to_local(ts, tzname):
    if not ts: return None
    try: dt=datetime.datetime.fromisoformat(ts)
    except ValueError: return None
    if dt.tzinfo is None: dt=dt.replace(tzinfo=datetime.timezone.utc)   # stored punches are UTC-aware
    return dt.astimezone(_tz(tzname))
def _sched_row(c, email): return c.execute("SELECT * FROM staff_schedule WHERE email=?",(email,)).fetchone()
def _sched_tz(c, email):
    s=_sched_row(c,email); return (s['tz'] if s and s['tz'] else DEFAULT_TZ)
def _sched_text(s):
    try: blocks=json.loads(s['blocks'] or '[]')
    except Exception: blocks=[]
    bt=', '.join(f"{a}–{b}" for a,b in blocks) or '—'
    days=s['days'] or ''
    dt='M-F' if days=='12345' else (''.join(_DABBR.get(d,'') for d in days) if days else '?')
    return f"{bt} · {dt} · {_TZLBL.get(s['tz'],s['tz'] or DEFAULT_TZ)}"
def _mins(hm):
    try: h,m=hm.split(':'); return int(h)*60+int(m)
    except Exception: return 0
def _sched_today(c, email):
    """Today's blocks/expected in-out/hours in the advocate's tz, or {'today':False}/None."""
    s=_sched_row(c,email)
    if not s: return None
    tzname=s['tz'] or DEFAULT_TZ
    wd=str(datetime.datetime.now(_tz(tzname)).isoweekday())   # 1=Mon..7=Sun
    if wd not in (s['days'] or ''): return {'today':False,'tz':tzname}
    try: blocks=json.loads(s['blocks'] or '[]')
    except Exception: blocks=[]
    if not blocks: return {'today':False,'tz':tzname}
    hrs=sum(max(0,_mins(b)-_mins(a)) for a,b in blocks)/60.0
    return {'today':True,'tz':tzname,'blocks':blocks,'in':blocks[0][0],'out':blocks[-1][1],'hours':round(hrs,2)}
def _on_time(c, email, ts_utc, action):
    st=_sched_today(c,email)
    if not st or not st.get('today'): return None
    loc=_to_local(ts_utc, st['tz'])
    if not loc: return None
    tmin=_mins(st['in'] if action=='in' else st['out'])
    return 1 if abs((loc.hour*60+loc.minute)-tmin)<=GRACE_MIN else 0
def _parse_utc(ts):
    try: dt=datetime.datetime.fromisoformat(ts)
    except (ValueError,TypeError): return None
    return dt.replace(tzinfo=datetime.timezone.utc) if dt.tzinfo is None else dt.astimezone(datetime.timezone.utc)
def _overlap_h(a,b,s,e):
    lo=a if a>s else s; hi=b if b<e else e
    return max(0.0,(hi-lo).total_seconds()/3600.0)
def _local_day_bounds_utc(tzname, day_iso=None):
    """[start,end) UTC datetimes bounding the given local calendar day (default today).
    Both bounds are TRUE local midnights, so DST-transition days (23h/25h) stay exact —
    end is next-day-midnight, not start+24h."""
    tz=_tz(tzname); utc=datetime.timezone.utc
    d=None
    if day_iso:
        try: d=datetime.date.fromisoformat(str(day_iso)[:10])
        except (ValueError,TypeError): d=None
    if d is None: d=datetime.datetime.now(tz).date()
    nd=d+datetime.timedelta(days=1)
    ds=datetime.datetime(d.year,d.month,d.day,tzinfo=tz).astimezone(utc)
    de=datetime.datetime(nd.year,nd.month,nd.day,tzinfo=tz).astimezone(utc)
    return ds, de
def _worked_hours_day(c, email, tzname, day_iso=None):
    """Hours inside the given local day (default today): pair in→out, CLIP each shift to
    [day 00:00, +1d). All arithmetic in UTC, so DST offset changes and cross-midnight/
    forgot-to-punch-out shifts are correct."""
    utc=datetime.timezone.utc; now_utc=datetime.datetime.now(utc)
    ds,de=_local_day_bounds_utc(tzname, day_iso)
    total=0.0; open_utc=None
    for r in c.execute("SELECT action,ts FROM time_punches WHERE actor=? ORDER BY id",(email,)):
        dt=_parse_utc(r['ts'])
        if not dt: continue
        if r['action']=='in': open_utc=dt
        elif r['action']=='out' and open_utc: total+=_overlap_h(open_utc,dt,ds,de); open_utc=None
    if open_utc: total+=_overlap_h(open_utc,now_utc,ds,de)   # still on the clock
    return round(total,2)
def _worked_hours(c, email, tzname): return _worked_hours_day(c, email, tzname)
def _punch_status(c, email):
    """on_clock from the LAST punch (matches /api/adv/timecard); display today's local in/out."""
    tzname=_sched_tz(c,email); today=datetime.datetime.now(_tz(tzname)).date().isoformat()
    rows=list(c.execute("SELECT action,ts,on_time FROM time_punches WHERE actor=? ORDER BY id",(email,)))
    last=rows[-1] if rows else None
    on=bool(last and last['action']=='in')
    fin=lout=in_ot=out_ot=None
    if on:
        loc=_to_local(last['ts'],tzname); fin=loc.strftime('%H:%M') if loc else None; in_ot=last['on_time']
    else:
        for r in rows:
            loc=_to_local(r['ts'],tzname)
            if not loc or loc.date().isoformat()!=today: continue
            if r['action']=='in' and fin is None: fin=loc.strftime('%H:%M'); in_ot=r['on_time']
            if r['action']=='out': lout=loc.strftime('%H:%M'); out_ot=r['on_time']
    return {'in':fin,'out':(None if on else lout),'on_clock':on,'hours':_worked_hours(c,email,tzname),
            'in_ontime':in_ot,'out_ontime':out_ot}
def _ot_status(c, email, worked):
    s=_sched_row(c,email)
    if not s: return None
    st=_sched_today(c,email); sched_h=(st.get('hours') if st and st.get('today') else 0) or 0
    if worked<=sched_h+0.02: return {'over':False,'sched':sched_h}
    over=round(worked-sched_h,2); permitted=bool(s['ot_permitted']); cap=s['ot_hours'] or 0
    return {'over':True,'over_hours':over,'permitted':permitted,'multiple':s['ot_multiple'],'cap':cap,
            'ok':permitted and (cap==0 or over<=cap+0.02),'sched':sched_h}

@app.post('/api/adv/punch')
async def punch(req: Request):
    u=who(req); need(u,'advocate'); f=await req.json(); c=db(); em=u['email']
    sig=(f.get('signature') or '').strip()
    if not sig: raise HTTPException(400,'Type your name to sign the punch')
    last=c.execute("SELECT action FROM time_punches WHERE actor=? ORDER BY id DESC LIMIT 1",(em,)).fetchone()
    action='in' if (not last or last['action']=='out') else 'out'
    ts=_utcnow(); ot=_on_time(c,em,ts,action)
    c.execute("INSERT INTO time_punches(actor,action,ts,signature,on_time) VALUES(?,?,?,?,?)",(em,action,ts,sig[:80],ot))
    c.commit(); audit(em,'punch',meta={'action':action,'on_time':ot})
    return {'ok':True,'action':action,'ts':ts,'on_clock':action=='in','hours_today':_worked_hours(c,em,_sched_tz(c,em))}

@app.get('/api/adv/timecard')
def timecard(req: Request):
    u=who(req); need(u,'advocate'); c=db(); em=u['email']
    last=c.execute("SELECT action,ts FROM time_punches WHERE actor=? ORDER BY id DESC LIMIT 1",(em,)).fetchone()
    on=bool(last and last['action']=='in'); s=_sched_row(c,em); tz=(s['tz'] if s else DEFAULT_TZ)
    out={'on_clock':on,'since':(last['ts'] if on else None),'hours_today':_worked_hours(c,em,tz)}
    out['sched_text']=(_sched_text(s) if s else None)
    out['ot']=({'permitted':bool(s['ot_permitted']),'multiple':s['ot_multiple'],'hours':s['ot_hours']} if s else None)
    return out

# ---------------- Work Log (advocate self-review; director oversight) ----------------
def _worklog(c, em, tz, day=''):
    """Time-ordered day log for advocate `em`: punches + their call/form dispositions,
    bucketed by their schedule tz (default America/Denver). Shared by the advocate's own
    Work Log and the director monitor — all times localized (Mountain by default)."""
    today=datetime.datetime.now(_tz(tz)).date().isoformat()
    try: d=datetime.date.fromisoformat((day or today)[:10])
    except (ValueError,TypeError): d=datetime.date.fromisoformat(today)
    if d.isoformat()>today: d=datetime.date.fromisoformat(today)      # never the future
    day=d.isoformat()
    ds,de=_local_day_bounds_utc(tz,day)
    lo=ds.replace(tzinfo=None).isoformat(); hi=de.replace(tzinfo=None).isoformat()   # dispositions.ts is naive-UTC
    events=[]; calls=connected=forms=0
    for r in c.execute("""SELECT d.ts,d.member_id,m.first,m.last,d.disposition,d.note,d.handle_secs
        FROM dispositions d JOIN member_core m USING(member_id)
        WHERE d.actor=? AND d.ts>=? AND d.ts<? ORDER BY d.ts""",(em,lo,hi)):
        loc=_to_local(r['ts'],tz); disp=r['disposition'] or ''
        isform=disp.startswith('Connected — Guide completed'); isconn=disp.startswith('Connected')
        calls+=1; connected+=1 if isconn else 0; forms+=1 if isform else 0
        events.append({'t':(loc.strftime('%H:%M') if loc else ''),'sort':r['ts'],   # sort on the UTC instant (naive-UTC ts), DST-fold safe
            'kind':('form' if isform else 'call'),'member_id':r['member_id'],
            'member':(str(r['first'] or '')+' '+str(r['last'] or '')).strip(),'outcome':disp,'note':r['note'],
            'handle_secs':r['handle_secs'],'connected':isconn,
            'stage':((re.search(r'\((\w+)\)$',disp) or [None,''])[1] if isform else '')})
    for r in c.execute("SELECT action,ts,on_time,signature FROM time_punches WHERE actor=? ORDER BY id",(em,)):
        loc=_to_local(r['ts'],tz); pu=_parse_utc(r['ts'])
        if not loc or loc.date().isoformat()!=day: continue
        events.append({'t':loc.strftime('%H:%M'),'sort':(pu.replace(tzinfo=None).isoformat() if pu else r['ts']),'kind':'punch',
            'action':r['action'],'on_time':r['on_time'],'signature':r['signature']})
    events.sort(key=lambda e:e['sort'])
    s=_sched_row(c,em); prev=(d-datetime.timedelta(days=1)).isoformat(); nxt=(d+datetime.timedelta(days=1)).isoformat()
    return {'day':day,'today':today,'prev':prev,'next':(nxt if nxt<=today else None),
            'sched_text':(_sched_text(s) if s else None),'hours':_worked_hours_day(c,em,tz,day),
            'summary':{'calls':calls,'connected':connected,'forms':forms},'events':events}

@app.get('/api/adv/worklog')
def adv_worklog(req: Request, day: str=''):
    u=who(req); need(u,'advocate'); c=db()
    return _worklog(c, u['email'], _sched_tz(c,u['email']), day)

@app.get('/api/dir/worklog')
def dir_worklog(req: Request, email: str='', day: str=''):
    """Director oversight: the exact Work Log an advocate sees for their own day."""
    u=who(req); need(u,'director'); c=db(); em=(email or '').lower().strip()
    if not c.execute("SELECT 1 FROM users WHERE email=? AND role='advocate'",(em,)).fetchone():
        raise HTTPException(400,'not an advocate')
    return _worklog(c, em, _sched_tz(c,em), day)

# ---------------- Member tiers (director-assigned; DB-backed) ----------------
@app.get('/api/dir/tiers')
def get_tiers(req: Request):
    """The full member_id -> tier map (director-only)."""
    u=who(req); need(u,'director'); c=db()
    return {'tiers':{r['member_id']:r['tier'] for r in c.execute("SELECT member_id,tier FROM member_tiers")}}

@app.post('/api/dir/tiers_sync')
async def tiers_sync(req: Request):
    """Persist the dashboard's tier labels. Per-browser delta: upsert the posted map and
    delete the explicitly-removed ids. No global replace, so multiple directors' tiers
    merge instead of clobbering, and a fresh/empty browser never wipes existing tiers."""
    u=who(req); need(u,'director'); f=await req.json(); c=db()
    posted=f.get('tiers') or {}
    clean={str(k):str(v).strip()[:80] for k,v in posted.items() if k and v and str(v).strip()}
    removed=[str(x) for x in (f.get('removed') or []) if x]
    if clean:
        c.executemany("""INSERT INTO member_tiers(member_id,tier,updated_by,updated_ts) VALUES(?,?,?,?)
            ON CONFLICT(member_id) DO UPDATE SET tier=excluded.tier,updated_by=excluded.updated_by,updated_ts=excluded.updated_ts""",
            [(k,v,u['email'],now()) for k,v in clean.items()])
    if removed:
        c.execute(f"DELETE FROM member_tiers WHERE member_id IN ({','.join('?'*len(removed))})",removed)
    c.commit()
    total=c.execute("SELECT COUNT(*) n FROM member_tiers").fetchone()['n']
    audit(u['email'],'tiers_sync',meta={'upserted':len(clean),'removed':len(removed),'total':total})
    return {'ok':True,'upserted':len(clean),'removed':len(removed),'total':total}

@app.get('/api/adv/worklog_search')
def adv_worklog_search(req: Request, q: str=''):
    """Find a person THIS advocate contacted, by name / phone / member ID."""
    u=who(req); need(u,'advocate'); c=db(); em=u['email']; q=(q or '').strip()
    if len(q)<2: return {'rows':[]}
    like='%'+q.replace('%','').replace('_','')+'%'
    qd=re.sub(r'\D','',q)                        # digits only — phone is stored E.164 '+1XXXXXXXXXX'
    ors=["m.first LIKE ?","m.last LIKE ?","(m.first||' '||m.last) LIKE ?","m.member_id LIKE ?"]
    op=[like,like,like,like]
    if len(qd)>=3:                               # match a phone typed in ANY format (dashes/parens/spaces/+1) against the digits-only stored number
        ors.append("REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(m.phone,'+',''),'-',''),'(',''),')',''),' ',''),'.','') LIKE ?")
        op.append('%'+qd+'%')
        ors.append("m.phone_last4 LIKE ?"); op.append('%'+qd+'%')
    rows=c.execute(f"""SELECT m.member_id,m.first,m.last,m.city,m.state,
        (SELECT d.ts FROM dispositions d WHERE d.member_id=m.member_id AND d.actor=? ORDER BY d.id DESC LIMIT 1) last_ts,
        (SELECT d.disposition FROM dispositions d WHERE d.member_id=m.member_id AND d.actor=? ORDER BY d.id DESC LIMIT 1) last_outcome
        FROM member_core m
        WHERE m.member_id IN (SELECT member_id FROM dispositions WHERE actor=?
            UNION SELECT bm.member_id FROM batch_members bm JOIN batches b ON b.id=bm.batch_id WHERE b.advocate=? AND bm.state IN('served','callback','done'))
        AND ({' OR '.join(ors)})
        ORDER BY last_ts DESC LIMIT 20""",(em,em,em,em,*op)).fetchall()
    tz=_sched_tz(c,em); out=[]
    for r in rows:
        loc=_to_local(r['last_ts'],tz) if r['last_ts'] else None
        out.append({'member_id':r['member_id'],'first':r['first'],'last':r['last'],'city':r['city'],'state':r['state'],
            'last_contact':(loc.strftime('%Y-%m-%d') if loc else None),'last_outcome':r['last_outcome']})
    return {'rows':out}

@app.get('/api/adv/member_review/{mid}')
def adv_member_review(mid: str, req: Request):
    """Read-only profile of a member this advocate has worked (phone masked). Ownership-gated;
    NOT actionable like adv_open — lets them review past contacts even after the member is done."""
    u=who(req); need(u,'advocate'); c=db(); em=u['email']
    owned=(c.execute("SELECT 1 FROM dispositions WHERE actor=? AND member_id=? LIMIT 1",(em,mid)).fetchone()
        or c.execute("SELECT 1 FROM batch_members bm JOIN batches b ON b.id=bm.batch_id WHERE b.advocate=? AND bm.member_id=? AND bm.state IN('served','callback','done') LIMIT 1",(em,mid)).fetchone())
    if not owned: raise HTTPException(403,'not one of your contacts')
    m=c.execute("SELECT member_id,first,last,city,state,age,quals,phone FROM member_core WHERE member_id=?",(mid,)).fetchone()   # explicit whitelist — no internal flags to the client
    if not m: raise HTTPException(404,'no such member')
    d=dict(m); ph=d.pop('phone',None); d['phone']='···'+((ph or '')[-4:])   # masked — review, not dial
    tz=_sched_tz(c,em)
    hist=[dict(h) for h in c.execute("SELECT date,event_type,detail,cls FROM comm_hist WHERE member_id=? ORDER BY date DESC, rowid DESC LIMIT 60",(mid,))]
    calls=[]
    for r in c.execute("SELECT ts,disposition,note,handle_secs FROM dispositions WHERE actor=? AND member_id=? ORDER BY id DESC LIMIT 40",(em,mid)):
        loc=_to_local(r['ts'],tz)
        calls.append({'when':(loc.strftime('%Y-%m-%d %H:%M') if loc else r['ts']),'disposition':r['disposition'],
            'note':r['note'],'handle_secs':r['handle_secs']})
    forms=[]
    for fr in c.execute("""SELECT ts,served_at,disposition FROM dispositions
        WHERE actor=? AND member_id=? AND disposition LIKE 'Connected — Guide completed%' ORDER BY id DESC LIMIT 20""",(em,mid)):
        stage=(re.search(r'\((\w+)\)$',fr['disposition'] or '') or [None,''])[1]
        lo=fr['served_at'] or (fr['ts'][:10]); hi=fr['ts'][:19]+'~'
        qa=[{'prompt':a['prompt'],'answer':a['answer']} for a in c.execute(
            """SELECT a.prompt,a.answer,COALESCE(g.seq,999) seq FROM answers a LEFT JOIN guide_items g ON g.id=a.question_id
               WHERE a.actor=? AND a.member_id=? AND a.stage=? AND a.ts>=? AND a.ts<=? ORDER BY seq,a.id""",(em,mid,stage,lo,hi))]
        loc=_to_local(fr['ts'],tz)
        forms.append({'when':(loc.strftime('%Y-%m-%d %H:%M') if loc else fr['ts']),'stage':stage,'qa':qa})
    return {'member':d,'hist':hist,'calls':calls,'forms':forms}

@app.post('/api/dir/schedule')
async def set_schedule(req: Request):
    u=who(req); need(u,'director'); f=await req.json(); c=db()
    em=(f.get('email') or '').lower().strip()
    if not em: raise HTTPException(400,'email required')
    if not c.execute("SELECT 1 FROM users WHERE email=?",(em,)).fetchone(): raise HTTPException(400,'not an enrolled user')
    days=''.join(d for d in str(f.get('days') or '') if d in '1234567') or '12345'
    cb=[]
    for b in (f.get('blocks') or []):
        try:
            a,z=str(b[0]),str(b[1])
            if re.match(r'^\d{1,2}:\d{2}$',a) and re.match(r'^\d{1,2}:\d{2}$',z): cb.append([a,z])
        except Exception: pass
    tz=(f.get('tz') or DEFAULT_TZ).strip()
    c.execute("""INSERT INTO staff_schedule(email,blocks,days,tz,ot_permitted,ot_multiple,ot_hours,updated_by,updated_ts)
        VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(email) DO UPDATE SET blocks=excluded.blocks,days=excluded.days,tz=excluded.tz,
          ot_permitted=excluded.ot_permitted,ot_multiple=excluded.ot_multiple,ot_hours=excluded.ot_hours,
          updated_by=excluded.updated_by,updated_ts=excluded.updated_ts""",
        (em,json.dumps(cb),days,tz,1 if f.get('ot_permitted') else 0,
         float(f.get('ot_multiple') or 1.5),float(f.get('ot_hours') or 0),u['email'],now()))
    c.commit(); audit(u['email'],'set_schedule',meta={'email':em,'days':days,'blocks':cb})
    return {'ok':True}

# ---------------- pages ----------------
DASH_PATH = os.environ.get('DASH_PATH', os.path.join(os.path.dirname(DB), 'dashboard.html'))

@app.get('/dashboard', response_class=HTMLResponse)
def full_dashboard(req: Request):
    """The director's own CRM Review Dashboard — served byte-for-byte, unchanged.
    Director-only, IAP-fronted, access audited. Contains full member payload incl. emails."""
    u = who(req); need(u, 'director')
    if not os.path.exists(DASH_PATH):
        raise HTTPException(404, 'dashboard.html not found on the data volume — upload it: '
            'gcloud storage cp "CRM Review Dashboard.html" gs://research-catalyst-crm-data/dashboard.html')
    audit(u['email'], 'dashboard_open')
    html = open(DASH_PATH, encoding='utf-8').read()
    # LIVE SHIM — appended, never modifies the dashboard's own code. After the dashboard's
    # init() finishes, fetch every advocate action logged since the payload was built,
    # append them as communication events, and rerun the dashboard's own recompute/apply.
    # tiny fixed link to the batch console (dashboard stays 100% unchanged otherwise)
    console_link = '<a href="/director'+('?as='+u['email'] if DEV else '')+'" style="position:fixed;top:8px;right:12px;z-index:9999;background:#101828;color:#fff;padding:6px 12px;border-radius:8px;font:600 12px system-ui,sans-serif;text-decoration:none;box-shadow:0 1px 3px #0003">⚙ Batch console ↗</a>'
    shim = console_link + """
<script>
(function(){
 var qs=new URLSearchParams(location.search); var AS=qs.get('as')?('?as='+qs.get('as')):'';
 function ready(){return (typeof DATA!=='undefined')&&(typeof COM!=='undefined')&&DATA&&DATA.length&&document.getElementById('app')&&document.getElementById('app').style.display!=='none';}
 function key3(e){return (e[0]||'')+'|'+(e[2]||'')+'|'+(e[3]||'');}
 function applyDelta(d){var n=0, meta=d.meta||{}, touched={};
  for(var mid in d.events){ if(!COM[mid])COM[mid]=[];
   var seen={}; COM[mid].forEach(function(e){seen[key3(e)]=1;});                 // tuple dedupe: idempotent vs
   d.events[mid].forEach(function(e){var k=key3(e);                              // baked-in rows, re-runs, and
    if(!seen[k]){seen[k]=1;COM[mid].unshift(e);n++;}});}                         // historical double-submits
  if(d.tl&&typeof TL!=='undefined'){for(var m2 in d.tl){ if(!TL[m2])TL[m2]=[];
   var s2={}; TL[m2].forEach(function(e){s2[key3(e)]=1;});
   d.tl[m2].forEach(function(e){var k=key3(e); if(!s2[k]){s2[k]=1;TL[m2].unshift(e);n++;}});
   touched[m2]=1;}}
  try{
   if(typeof TL!=='undefined'&&typeof memAttr!=='undefined'){
    for(var m3 in touched){ var mm={};
     TL[m3].forEach(function(ev){(mm[ev[2]]||(mm[ev[2]]=new Set())).add(ev[3]);});
     for(var at in mm){ var mt=meta[at];                                          // latest-wins for radios:
      if(mt&&mt.single){ var best=null;                                           // the member's CURRENT state,
       TL[m3].forEach(function(ev){if(ev[2]===at&&(!best||ev[0]>best))best=ev[0];});// not the union of history
       var got=false, keep=new Set();
       TL[m3].forEach(function(ev){if(ev[2]===at&&ev[0]===best&&!got){keep.add(ev[3]);got=true;}});
       mm[at]=keep;}}
     memAttr[m3]=mm;}
    if(typeof VCNT!=='undefined'){ VCNT={}; var av={};                            // full count rebuild (init's own
     for(var m4 in memAttr){ var a4=memAttr[m4];                                  // loop) — fixes stale chip counts
      for(var at2 in a4){ a4[at2].forEach(function(v){ VCNT[at2+'|'+v]=(VCNT[at2+'|'+v]||0)+1;
       (av[at2]||(av[at2]=new Set())).add(v);});}}
     if(typeof FG!=='undefined'){ for(var at3 in av){ var mt3=meta[at3]; if(!mt3)continue;
      var box=FG[mt3.box]; if(!box)continue;                                      // find-or-create group + facet so
      var grp=null; box.forEach(function(g){if(g[0]===mt3.grp)grp=g;});           // brand-new live attrs get chips;
      if(!grp){grp=[mt3.grp,[]];box.push(grp);}                                   // no-op once a regen bakes them in
      var fac=null; grp[1].forEach(function(f){if(f.name===at3)fac=f;});
      if(!fac){fac={name:at3,vals:[]};grp[1].push(fac);}
      av[at3].forEach(function(v){if(fac.vals.indexOf(v)<0)fac.vals.push(v);});}
      if(typeof renderBox==='function'){renderBox('TREATMENT');renderBox('CONDSYM');} // renderBox binds no handlers
      if(typeof syncChipStates==='function')syncChipStates();}}}                  // (container-delegated) — never
  }catch(err){console.warn('live-merge facets:',err);}                            // re-call buildFilters()
  try{ if(typeof recompute==='function')recompute(); if(typeof buildStats==='function')buildStats(); if(typeof apply==='function')apply(); }catch(err){console.warn('live-merge recompute:',err);}
  console.log('CRM live merge: '+n+' advocate events through '+d.through);}
 function go(){ if(!ready()){setTimeout(go,400);return;}
  // APP_DATA_THROUGH is a forward-compat hook: gen_final18 will bake it (= app->master export
  // cutoff). Until then it is undefined -> full replay, which the tuple dedupe makes safe.
  var since=(typeof APP_DATA_THROUGH!=='undefined')?((AS?'&':'?')+'since='+APP_DATA_THROUGH):'';
  fetch('/api/dir/dashboard_delta'+AS+since).then(function(r){return r.json();}).then(applyDelta)
  .catch(function(e){console.warn('live delta unavailable:',e);});}
 go();
 // --- tier sync: mirror the dashboard's localStorage crm_tiers into the DB so advocates + the
 // monitor see director-assigned tiers. Per-browser delta (upsert + explicit removes) — no wipe.
 (function(){ var prev='{}';
  function sync(){ try{
    var cur=localStorage.getItem('crm_tiers')||'{}'; if(cur===prev)return;
    var curObj=JSON.parse(cur), prevObj=JSON.parse(prev);
    var removed=Object.keys(prevObj).filter(function(k){return !(k in curObj);});
    fetch('/api/dir/tiers_sync'+AS,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tiers:curObj,removed:removed})}).then(function(){prev=cur;}).catch(function(){});
  }catch(e){} }
  sync(); setInterval(sync,15000);
  document.addEventListener('visibilitychange',function(){ if(!document.hidden)sync(); }); })();
})();
</script>"""
    return HTMLResponse(html.replace('</body>', shim + '</body>') if '</body>' in html else html + shim)

@app.get('/api/dir/dashboard_delta')
def dashboard_delta(req: Request):
    """Advocate activity shaped as dashboard comm + clinical-timeline events, plus facet metadata.
    ?since=YYYY-MM-DD limits replay (inclusive; the shim's tuple-dedupe absorbs boundary overlap
    and full replays alike, so empty since = full replay is safe)."""
    u = who(req); need(u, 'director'); c = db()
    since = (req.query_params.get('since') or '')[:10]
    ev = {}
    n = 0
    q = "SELECT member_id, ts, actor, disposition, note FROM dispositions" + (" WHERE ts>=?" if since else "") + " ORDER BY id"
    for r in c.execute(q, (since,) if since else ()):
        kind = r['disposition']
        detail = kind + ((' — ' + r['note']) if r['note'] else '')
        # HH:MM suffix makes same-day repeat calls distinct tuples for the shim dedupe
        # (true replays of the same row stay identical), and shows the director the call time
        e = [r['ts'][:10], 'Advocacy App', 'Note (' + r['actor'].split('@')[0] + ')', detail[:400] + ' · ' + r['ts'][11:16], '']
        ev.setdefault(r['member_id'], []).append(e)
        n += 1
    q = """SELECT member_id, date, event_type, detail, cls FROM comm_hist
        WHERE event_type IN ('Assigned to advocate','Unassigned from advocate')""" + (" AND date>=?" if since else "") + " ORDER BY rowid"
    for r in c.execute(q, (since,) if since else ()):
        e = [(r['date'] or '')[:10], 'Advocacy App', r['event_type'], (r['detail'] or '')[:400], r['cls'] or 'O']
        ev.setdefault(r['member_id'], []).append(e)
        n += 1
    # live options per fan attr — legacy joined rows are split on the FULL detail and each piece
    # exact-matched against the options, so [:500]-era truncation fragments never become chips
    fan_opts = {}
    for k, v in CAPTURE_MAP.items():
        if v['fan']:
            r0 = c.execute("SELECT options FROM guide_items WHERE stage=? AND seq=?", k).fetchone()
            if r0 and r0['options']: fan_opts.setdefault(v['attr'], set()).update(r0['options'].split('|'))
    tl = {}
    q = "SELECT member_id, date, event_type, detail FROM comm_hist WHERE event_type LIKE 'Clinical: %'" + (" AND date>=?" if since else "") + " ORDER BY rowid"
    for r in c.execute(q, (since,) if since else ()):
        attr = r['event_type'][10:]; det = (r['detail'] or '')
        if attr in fan_opts and '; ' in det:
            parts = [p.strip() for p in det.split('; ') if p.strip() in fan_opts[attr]] or [det[:200]]
        else:
            parts = [det[:200]]
        for p in parts:
            tl.setdefault(r['member_id'], []).append([(r['date'] or '')[:10], 'C', attr, p[:200]])
    # facet metadata for the shim: attr -> {box, grp, single} or None (timeline-only). Contact attrs never ship.
    qt = {(r['stage'], r['seq']): r['qtype'] for r in c.execute("SELECT stage,seq,qtype FROM guide_items WHERE kind='q'")}
    fmeta = {'Next HCP appointment': None}
    for k, v in CAPTURE_MAP.items():
        if v['kind'] == 'K': continue
        if fmeta.get(v['attr']) is None:   # first grp'd occurrence wins; shared attrs are consistent by construction
            fmeta[v['attr']] = ({'box': v['grp'][0], 'grp': v['grp'][1], 'single': qt.get(k) == 'radio'} if v['grp'] else None)
    audit(u['email'], 'dashboard_delta', meta={'events': n, 'since': since or 'all'})
    return {'through': now(), 'events': ev, 'tl': tl, 'meta': fmeta, 'count': n}

from ui import DIRECTOR_HTML, ADVOCATE_HTML

@app.get('/director', response_class=HTMLResponse)
def director_page(req: Request):
    u=who(req); need(u,'director'); return DIRECTOR_HTML.replace('__ME__',u['email'])

@app.get('/advocate', response_class=HTMLResponse)
def advocate_page(req: Request):
    u=who(req); need(u,'advocate'); return ADVOCATE_HTML.replace('__ME__',u['display'])

@app.get('/CRM', response_class=HTMLResponse)      # friendly alias -> advocates land here (crm.parkinsons.community/CRM)
@app.get('/crm', response_class=HTMLResponse)
def crm_page(req: Request):
    u=who(req); need(u,'advocate'); return ADVOCATE_HTML.replace('__ME__',u['display'])

# ---------------- monitor (isolated add-on: read-only director view; all code in monitor.py) ----------------
from monitor import router as monitor_router   # import last so who/need/db/now already exist (no circular trap)
app.include_router(monitor_router)
