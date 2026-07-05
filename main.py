"""Advocacy CRM — director assignment + advocate served queue with Google Voice click-to-dial.
Runs on Cloud Run behind Identity-Aware Proxy. Roles enforced server-side; every action audited.
Local dev:  DEV=1 uvicorn main:app --reload   (then ?as=you@org.com)
"""
import os, re, sqlite3, json, datetime, urllib.parse
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

DB = os.environ.get('APP_DB', os.path.join(os.path.dirname(__file__), 'app.db'))
DEV = os.environ.get('DEV') == '1'
MIN_HANDLE_SECS = 20          # dispositions faster than this get flagged
CONNECT_MIN_SECS = 60         # 'Connected' dispositions faster than this after call-click get flagged
app = FastAPI()

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

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
@app.get('/')
def root(req: Request):
    u = who(req)
    q = '?as='+u['email'] if DEV else ''
    # Director home = the full CRM Review Dashboard (real filters). Console (/director) is a secondary tool.
    return RedirectResponse('/dashboard'+q if u['role']=='director' else '/advocate'+q)

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
    hist=[dict(h) for h in c.execute("SELECT date,event_type,detail,cls FROM comm_hist WHERE member_id=? LIMIT 15",(mid,))]
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

def build_card(c, u, bid, mid):
    m = c.execute("SELECT * FROM member_core WHERE member_id=?",(mid,)).fetchone()
    hist = c.execute("SELECT date,event_type,detail,cls FROM comm_hist WHERE member_id=? LIMIT 15",(mid,)).fetchall()
    b = c.execute("SELECT name,script_hint FROM batches WHERE id=?",(bid,)).fetchone()
    bm = c.execute("SELECT stage,hcp_date,stage_attempts FROM batch_members WHERE batch_id=? AND member_id=?",(bid,mid)).fetchone()
    stage = bm['stage'] or 'initial'
    sc = c.execute("SELECT title,body FROM scripts WHERE stage=?",(stage,)).fetchone()
    qs = [dict(q) for q in c.execute("SELECT id,seq,kind,text,qtype,options,show_qid,show_vals,dq_vals,sched FROM guide_items WHERE stage=? ORDER BY seq",(stage,))]
    left = c.execute("SELECT COUNT(*) n FROM batch_members WHERE batch_id=? AND state='pending'",(bid,)).fetchone()['n']
    d = dict(m)
    num = d.pop('phone')                      # masked in UI; full number travels only inside the GV deep links
    call = 'https://voice.google.com/u/0/calls?a=nc,' + urllib.parse.quote(num)
    text = 'https://voice.google.com/u/0/messages?itemId=t.' + urllib.parse.quote(num)
    body=(sc['body'] if sc else '').replace('{first}',m['first']).replace('{hcp_date}',bm['hcp_date'] or 'your upcoming date').replace('{advocate}',u['display'])
    sms=SMS_TEMPLATES.get(stage,SMS_TEMPLATES['initial']).replace('{first}',m['first']).replace('{advocate}',u['display'])
    d.update(batch_id=bid, batch=b['name'], script=b['script_hint'], remaining=left, sms_text=(sms if SMS_ENABLED else ''),
             call_url=call, text_url=(text if SMS_ENABLED else ''), dial='tel:'+num, served_at=now(),
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
        w={"due":"bm.state='callback' AND replace(bm.callback_at,'T',' ')<=datetime('now','localtime')",
           "callbacks":"bm.state='callback' AND replace(bm.callback_at,'T',' ')>datetime('now','localtime')",
           "queue":"bm.state IN('pending','served')"}.get(view)
        if not w: raise HTTPException(400,'bad view')
        base=f"""FROM batch_members bm JOIN batches b ON b.id=bm.batch_id JOIN member_core m ON m.member_id=bm.member_id
            WHERE b.advocate=? AND b.status='open' AND {w}"""
        tot=c.execute(f"SELECT COUNT(*) n {base}",(email,)).fetchone()['n']
        rows=c.execute(f"""SELECT bm.member_id, m.first,m.last,m.age,m.state st,m.quals,m.conn,m.att,
            bm.stage,bm.state bstate,bm.stage_attempts,bm.callback_at,bm.hcp_date,b.name batch,
            (SELECT d.disposition||' · '||substr(d.ts,6,11) FROM dispositions d WHERE d.member_id=bm.member_id ORDER BY d.id DESC LIMIT 1) last_disp
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
SMS_ENABLED = False  # pilot: texting OFF server-side until PRC/MLR-approved copy
SMS_TEMPLATES = {  # PLACEHOLDER operational texts (opt-out included) — replace with PRC/MLR-approved copy before use
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
    hcp=None; dq=False; lines=[]; call_doctor_yes=False
    for a in (f.get('answers') or []):
        it=c.execute("SELECT * FROM guide_items WHERE id=? AND stage=? AND kind='q'",(a.get('qid'),stage)).fetchone()
        if not it: continue
        val=str(a.get('answer') or '').strip()[:500]
        if not val: continue
        c.execute("INSERT INTO answers(ts,actor,member_id,batch_id,stage,question_id,prompt,answer) VALUES(?,?,?,?,?,?,?,?)",
            (now(),u['email'],mid,bid,stage,it['id'],it['text'][:200],val))
        lines.append(f"{it['text'][:60]} -> {val}")
        if it['sched']=='hcp':
            try: hcp=datetime.date.fromisoformat(val[:10]).isoformat()
            except ValueError: pass  # invalid calendar date -> ignore, advocate can re-ask
        if it['dq_vals'] and it['dq_vals'] in val: dq=True
        if stage=='post_hcp' and it['seq']==5 and val=='Yes': call_doctor_yes=True
    served=f.get('served_at') or now()
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
    if d in ('Refused / Remove','Deceased'):
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
    return {'today': r['n'] or 0, 'connected': r['conn'] or 0}

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
 function applyDelta(d){var n=0;
  for(var mid in d.events){ if(!COM[mid])COM[mid]=[];
   d.events[mid].forEach(function(e){COM[mid].unshift(e);n++;});}
  try{ if(typeof recompute==='function')recompute(); if(typeof apply==='function')apply(); }catch(err){console.warn('live-merge recompute:',err);}
  console.log('CRM live merge: '+n+' advocate events through '+d.through);}
 function go(){ if(!ready()){setTimeout(go,400);return;}
  fetch('/api/dir/dashboard_delta'+AS).then(function(r){return r.json();}).then(applyDelta)
  .catch(function(e){console.warn('live delta unavailable:',e);});}
 go();
})();
</script>"""
    return HTMLResponse(html.replace('</body>', shim + '</body>') if '</body>' in html else html + shim)

@app.get('/api/dir/dashboard_delta')
def dashboard_delta(req: Request):
    """Advocate activity since the dashboard payload was built, shaped as dashboard comm events."""
    u = who(req); need(u, 'director'); c = db()
    ev = {}
    n = 0
    for r in c.execute("""SELECT member_id, ts, actor, disposition, note FROM dispositions ORDER BY id"""):
        kind = r['disposition']
        detail = kind + ((' — ' + r['note']) if r['note'] else '')
        e = [r['ts'][:10], 'Advocacy App', 'Note (' + r['actor'].split('@')[0] + ')', detail[:400], '']
        ev.setdefault(r['member_id'], []).append(e)
    for r in c.execute("""SELECT member_id, date, event_type, detail, cls FROM comm_hist
        WHERE event_type IN ('Assigned to advocate','Unassigned from advocate') ORDER BY rowid"""):
        e = [(r['date'] or '')[:10], 'Advocacy App', r['event_type'], (r['detail'] or '')[:400], r['cls'] or 'O']
        ev.setdefault(r['member_id'], []).append(e)
        n += 1
    audit(u['email'], 'dashboard_delta', meta={'events': n})
    return {'through': now(), 'events': ev, 'count': n}

from ui import DIRECTOR_HTML, ADVOCATE_HTML

@app.get('/director', response_class=HTMLResponse)
def director_page(req: Request):
    u=who(req); need(u,'director'); return DIRECTOR_HTML.replace('__ME__',u['email'])

@app.get('/advocate', response_class=HTMLResponse)
def advocate_page(req: Request):
    u=who(req); need(u,'advocate'); return ADVOCATE_HTML.replace('__ME__',u['display'])
