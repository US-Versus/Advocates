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
    return RedirectResponse('/director'+q if u['role']=='director' else '/advocate'+q)

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
    return {'dispositions':[dict(r) for r in disp], 'summary':[dict(r) for r in summ]}

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
    c=db(); c.execute("INSERT OR REPLACE INTO users(email,role,display,active) VALUES(?,?,?,?)",
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

@app.get('/api/adv/next')
def nxt(req: Request):
    u = who(req); need(u,'advocate'); email=u['email']; c=db()
    c.execute("""UPDATE batch_members SET stage='post_hcp', stage_attempts=0,
        callback_at=date(hcp_date,'+'||? ||' days')||'T09:00'
        WHERE stage='pre_hcp' AND hcp_date IS NOT NULL AND hcp_date<date('now','localtime')
        AND state IN('callback','pending')""",(POST_DELAY_DAYS,)); c.commit()
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
    m = c.execute("SELECT * FROM member_core WHERE member_id=?",(mid,)).fetchone()
    hist = c.execute("SELECT date,event_type,detail,cls FROM comm_hist WHERE member_id=? LIMIT 15",(mid,)).fetchall()
    b = c.execute("SELECT name,script_hint FROM batches WHERE id=?",(bid,)).fetchone()
    bm = c.execute("SELECT stage,hcp_date,stage_attempts FROM batch_members WHERE batch_id=? AND member_id=?",(bid,mid)).fetchone()
    stage = bm['stage'] or 'initial'
    sc = c.execute("SELECT title,body FROM scripts WHERE stage=?",(stage,)).fetchone()
    qs = [dict(q) for q in c.execute("SELECT id,seq,kind,text,qtype,options,show_qid,show_vals,dq_vals,sched FROM guide_items WHERE stage=? ORDER BY seq",(stage,))]
    left = c.execute("SELECT COUNT(*) n FROM batch_members WHERE batch_id=? AND state='pending'",(bid,)).fetchone()['n']
    audit(email,'serve',mid,bid)
    d = dict(m)
    num = d.pop('phone')                      # full number never sent as a plain field
    call = 'https://voice.google.com/u/0/calls?a=nc,' + urllib.parse.quote(num)
    text = 'https://voice.google.com/u/0/messages?itemId=t.' + urllib.parse.quote(num)
    body=(sc['body'] if sc else '').replace('{first}',m['first']).replace('{hcp_date}',bm['hcp_date'] or 'your upcoming date').replace('{advocate}',u['display'])
    d.update(batch_id=bid, batch=b['name'], script=b['script_hint'], remaining=left,
             call_url=call, text_url=text, served_at=now(),
             stage=stage, hcp_date=bm['hcp_date'], stage_attempt=(bm['stage_attempts'] or 0)+1, max_attempts=MAX_STAGE_ATTEMPTS,
             stage_title=(sc['title'] if sc else stage),
             stage_script=body, guide=qs,
             hist=[dict(h) for h in hist])
    return d

@app.post('/api/adv/click')
async def click(req: Request):
    u=who(req); need(u,'advocate'); f=await req.json(); c=db()
    cur = current_card(c, u['email'])
    if not cur or cur['member_id']!=f.get('member_id'): raise HTTPException(403,'not your current card')
    audit(u['email'], 'click_'+('call' if f.get('kind')=='call' else 'text'), cur['member_id'], cur['batch_id'])
    return {'ok': True, 'ts': now()}

STAGE_NEXT = {'initial':'pre_hcp','pre_hcp':'post_hcp','post_hcp':'complete'}
PRE_WINDOW_DAYS, POST_DELAY_DAYS = 10, 28   # pre window opens HCP-10d; post opens HCP+4wks
MAX_STAGE_ATTEMPTS, POST_RETRY_DAYS = 3, 3   # ≤3 serves per window; post retries 3 days apart

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
    cur = current_card(c, u['email'])
    if not cur or cur['member_id']!=f.get('member_id'): raise HTTPException(403,'not your current card')
    bid, mid = cur['batch_id'], cur['member_id']
    bm=c.execute("SELECT stage,hcp_date FROM batch_members WHERE batch_id=? AND member_id=?",(bid,mid)).fetchone()
    stage=bm['stage'] or 'initial'
    hcp=None; dq=False; lines=[]; call_doctor_yes=False
    for a in (f.get('answers') or []):
        it=c.execute("SELECT * FROM guide_items WHERE id=? AND stage=? AND kind='q'",(a.get('qid'),stage)).fetchone()
        if not it: continue
        val=str(a.get('answer') or '').strip()[:500]
        if not val: continue
        c.execute("INSERT INTO answers(ts,actor,member_id,batch_id,stage,question_id,prompt,answer) VALUES(?,?,?,?,?,?,?,?)",
            (now(),u['email'],mid,bid,stage,it['id'],it['text'][:200],val))
        lines.append(f"{it['text'][:60]} -> {val}")
        if it['sched']=='hcp' and re.match(r'^\d{4}-\d{2}-\d{2}',val): hcp=val[:10]
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
    audit(u['email'],'guide_submit',mid,bid,meta={'stage':stage,'answers':len(lines),'outcome':outcome})
    return {'ok':True,'outcome':outcome}

DISPOSITIONS = ['Connected — Educated','Connected — Callback Scheduled','Connected — Not Interested',
                'Left Voicemail','No Answer','Bad Number','Refused / Remove','DQ — Clinical','Deceased','Skipped']

@app.post('/api/adv/disposition')
async def disposition(req: Request):
    u=who(req); need(u,'advocate'); f=await req.json(); c=db()
    cur = current_card(c, u['email'])
    if not cur or cur['member_id']!=f.get('member_id'): raise HTTPException(403,'not your current card')
    d = f.get('disposition')
    if d not in DISPOSITIONS: raise HTTPException(400,'unknown disposition')
    if d=='Skipped' and not (f.get('note') or '').strip(): raise HTTPException(400,'skip requires a reason')
    bid, mid = cur['batch_id'], cur['member_id']
    served = f.get('served_at') or now()
    try: handle = (datetime.datetime.fromisoformat(now())-datetime.datetime.fromisoformat(served)).total_seconds()
    except: handle = None
    cb = f.get('callback_at') if d=='Connected — Callback Scheduled' else None
    c.execute("""INSERT INTO dispositions(ts,actor,member_id,batch_id,disposition,note,served_at,call_click_at,text_click_at,handle_secs)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",(now(),u['email'],mid,bid,d,(f.get('note') or '')[:400],served,
        f.get('call_click_at'),f.get('text_click_at'),handle))
    bm=c.execute("SELECT stage,hcp_date,stage_attempts FROM batch_members WHERE batch_id=? AND member_id=?",(bid,mid)).fetchone()
    stage=bm['stage'] or 'initial'; hcp=bm['hcp_date']; attempts=(bm['stage_attempts'] or 0)+1
    terminal = d in ('Refused / Remove','DQ — Clinical','Deceased','Bad Number') or d.startswith('Connected')
    if cb:
        c.execute("UPDATE batch_members SET state='callback', callback_at=?, stage_attempts=? WHERE batch_id=? AND member_id=?",(cb,attempts,bid,mid))
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
    else:
        c.execute("UPDATE batch_members SET state='done' WHERE batch_id=? AND member_id=?",(bid,mid))
    # write back into the master log table inside app.db mirror (export to CRM_Master.db is a director action)
    c.execute("INSERT INTO comm_hist(member_id,date,event_type,detail,cls) VALUES(?,?,?,?,?)",
        (mid, now()[:10], f'Advocate Call ({u["display"]})', d + ((' — '+f.get('note')) if f.get('note') else ''),
         'C' if d.startswith('Connected') else ('B' if d=='Bad Number' else 'A' if d in('Left Voicemail','No Answer') else 'O')))
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
from ui import DIRECTOR_HTML, ADVOCATE_HTML
@app.get('/director', response_class=HTMLResponse)
def director_page(req: Request):
    u=who(req); need(u,'director'); return DIRECTOR_HTML.replace('__ME__',u['email'])
@app.get('/advocate', response_class=HTMLResponse)
def advocate_page(req: Request):
    u=who(req); need(u,'advocate'); return ADVOCATE_HTML.replace('__ME__',u['display'])
