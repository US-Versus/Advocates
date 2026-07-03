"""Builds app.db from ../CRM_Master.db.
Privacy by construction: member emails and street addresses are NEVER imported.
Run:  python init_db.py [path-to-CRM_Master.db] [director-email]
"""
import sqlite3, re, sys, os, json, collections, datetime

SRC = sys.argv[1] if len(sys.argv)>1 else os.path.join(os.path.dirname(__file__),'..','CRM_Master.db')
DIRECTOR = sys.argv[2] if len(sys.argv)>2 else 'rmandmllc@gmail.com'
DST = os.path.join(os.path.dirname(__file__),'app.db')
HIDE_START,HIDE_END = '2026-03-01','2026-07-01'   # compromised window stays hidden
TODAY = datetime.date.today().isoformat()

STRONG=re.compile(r"spoke|talked|discuss|educat|went over|review(ed)? with|conversation|interview|pre.?call (complet|done)|post.?call complet|survey complet|completed call|warm transfer|transferred to|consent (given|signed)|enrolled|randomiz|connection \(imported",re.I)
WEAK=re.compile(r"call ?back|call (her|him|me|us|them) (then|on|at|next|around|tom)|cb (on|next|at|thur|fri|mon|tue|wed)|no(t| longer)? ?int('|erest)|declined|not?\s+interested",re.I)
CONTENT=re.compile(r"off time|off episode|sinemet|rytary|gocovri|apokyn|inbrija|onapgo|symptom|resource|doctor|dr\.|mds|medicat|dyskinesia|tremor",re.I)
VM=re.compile(r"\blvm\b|voice ?mail|no answer|left (a )?(message|vm)",re.I)
BAD=re.compile(r"wrong number|disconnect|#?oos\b|out of service|bad number|not in service|invalid number",re.I)
ONEWAY=re.compile(r"mailer|fax|letter sent",re.I)
REFUSE=re.compile(r"(req(uest(s|ed)?)?\.?\s*(to be\s*)?remov(al|ed)\b|remov(al|ed)?\s+from\s+(the\s+)?(database|dbase|list|contact|c/l|mailing)|do not (call|contact)(?!\s+(for|until))|refus(es|ed|ing)?\s+(further\s+)?(contact|calls?)|asked\s+(us\s+)?to\s+stop\s+call)",re.I)

def classify(t):
    if ONEWAY.search(t): return '1'
    if BAD.search(t): return 'B'
    if STRONG.search(t): return 'C'
    if (WEAK.search(t) or (len(t)>55 and CONTENT.search(t))) and not VM.search(t): return 'C'
    if not t.strip(): return 'O'
    return 'A'

def e164(p):
    d=re.sub(r'\D','',str(p or ''))
    if len(d)==11 and d.startswith('1'): d=d[1:]
    return '+1'+d if len(d)==10 else ''

src=sqlite3.connect(f'file:{SRC}?mode=ro',uri=True)
if os.path.exists(DST): os.remove(DST)
dst=sqlite3.connect(DST)
dst.executescript('''
CREATE TABLE users(email TEXT PRIMARY KEY, role TEXT CHECK(role IN('director','advocate')), display TEXT, active INTEGER DEFAULT 1);
CREATE TABLE member_core(member_id TEXT PRIMARY KEY, first TEXT, last TEXT, city TEXT, state TEXT,
  phone TEXT, phone_last4 TEXT, age INTEGER, status TEXT, quals TEXT, sflags TEXT,
  conn INTEGER, att INTEGER, last_conn TEXT, att_since INTEGER, refused INTEGER, dnc_cand INTEGER,
  doctor TEXT, clinic TEXT);
CREATE TABLE comm_hist(member_id TEXT, date TEXT, event_type TEXT, detail TEXT, cls TEXT);
CREATE INDEX ix_ch ON comm_hist(member_id);
CREATE TABLE batches(id INTEGER PRIMARY KEY, name TEXT, advocate TEXT, created_by TEXT, created_at TEXT,
  status TEXT DEFAULT 'open', script_hint TEXT);
CREATE TABLE batch_members(batch_id INTEGER, member_id TEXT, seq INTEGER, state TEXT DEFAULT 'pending',
  callback_at TEXT, PRIMARY KEY(batch_id,member_id));
CREATE TABLE activity(id INTEGER PRIMARY KEY, ts TEXT, actor TEXT, action TEXT, member_id TEXT, batch_id INTEGER, meta TEXT);
CREATE TABLE dispositions(id INTEGER PRIMARY KEY, ts TEXT, actor TEXT, member_id TEXT, batch_id INTEGER,
  disposition TEXT, note TEXT, served_at TEXT, call_click_at TEXT, text_click_at TEXT, handle_secs REAL);
CREATE TABLE scripts(stage TEXT PRIMARY KEY, title TEXT, body TEXT);
CREATE TABLE guide_questions(id INTEGER PRIMARY KEY, stage TEXT, seq INTEGER, prompt TEXT, qtype TEXT, options TEXT);
CREATE TABLE answers(id INTEGER PRIMARY KEY, ts TEXT, actor TEXT, member_id TEXT, batch_id INTEGER, stage TEXT,
  question_id INTEGER, prompt TEXT, answer TEXT);
''')
dst.execute("ALTER TABLE batch_members ADD COLUMN stage TEXT DEFAULT 'initial'")
dst.execute("ALTER TABLE batch_members ADD COLUMN hcp_date TEXT")
dst.execute("ALTER TABLE batch_members ADD COLUMN stage_attempts INTEGER DEFAULT 0")
from guides_seed import GUIDE_ITEMS, SCRIPTS
for k,(t,b) in SCRIPTS.items(): dst.execute("INSERT INTO scripts VALUES(?,?,?)",(k,t,b))
dst.executescript("CREATE TABLE guide_items(id INTEGER PRIMARY KEY, stage TEXT, seq INTEGER, kind TEXT, text TEXT, qtype TEXT, options TEXT, show_qid TEXT, show_vals TEXT, dq_vals TEXT, sched TEXT);")
dst.executemany("INSERT INTO guide_items(stage,seq,kind,text,qtype,options,show_qid,show_vals,dq_vals,sched) VALUES(?,?,?,?,?,?,?,?,?,?)", GUIDE_ITEMS)

dst.execute("INSERT INTO users VALUES(?,?,?,1)",(DIRECTOR.lower(),'director','Director'))

# per-member comm computation (window-hidden)
comm=collections.defaultdict(list)
for mid,d,et,det in src.execute("SELECT member_id,date,event_type,detail___outcome FROM communications"):
    dd=d or ''
    if dd and HIDE_START<=dd<HIDE_END: continue
    comm[mid].append((dd,et or '',(det or '')[:400]))

quals=collections.defaultdict(set)
for mid,f,v in src.execute("SELECT member_id,campaign___field,code___value FROM campaign_codes"):
    f=(f or '').lower(); v=str(v or '').lower()
    if not v: continue
    if f=='apokyn' or 'apokyn' in v: quals[mid].add('Apokyn')
    if f.startswith('inbrija') or 'inbrija' in v: quals[mid].add('Inbrija')
    if 'gocovri' in f or 'gocovri' in v: quals[mid].add('Gocovri')
    if 'dyskinesia' in f or 'dyskinesia' in v: quals[mid].add('Dyskinesia')
    if 'onapgo' in f or 'onapgo' in v:
        quals[mid].add('Onapgo')
        if v=='qualified': quals[mid].add('Onapgo Qualified')
    if 'n317' in v or 'n-317' in f: quals[mid].add('N317 trial')
    if 'ipx' in v: quals[mid].add('IPX203 trial')

MC={'offb':'is_off_time_a_problem_for_the_patient?','liver':'does_the_patient_have_liver_insufficiency_or_been_diagnosed_with_liver_disease?',
 'halluc':"parkinson's_disease_medications_can_commonly_cause_side_effects_such_as_hallucinations_or_abnormal_thoughts._we_would_like_to_check_if_you_or_your_loved_one_is_experiences_any_side_effects._does_the_patient_currently_have_or_in_the_past_had_hallucinations_(e.g._seeing_people,_animals,_or_things_are_not_truly_present)_or_delusions_(fixed_unusual_thoughts_such_as_paranoia)?",
 'dementia':'has_the_patient_been_diagnosed_with_dementia?','duopa':'does_the_patient_have_a_duopa_pump?',
 'dbs':'is_the_patient_scheduled_for_deep_brain_stimulation_(dbs)_within_the_next_3_months?'}
sel=', '.join(f'"{v}" AS {k}' for k,v in MC.items())
med={r[0]:r[1:] for r in src.execute(f'SELECT member_id,{sel} FROM medical_attributes')}
def yes(v): return bool(v) and str(v).strip().lower().startswith('yes')

n=0
for r in src.execute("SELECT member_id,first_name,last_name,city,state,phone,additional_phones,membership_status,segment,age_estimate,doctor_name,clinic FROM members"):
    mid,fn,ln,city,st,ph,ap,status,seg,age,doc,clinic=r
    if status in ('Deceased',) or seg in ('Deceased','No Contact'): continue
    pe=e164(ph) or e164(ap)
    ev=sorted(comm.get(mid,[]))
    c=a=bad=0; lastC=''; attSince=0; refused=0; hist=[]
    for d,et,det in ev:
        t=f'{et} {det}'
        if REFUSE.search(t): refused=1
        k=classify(t)
        hist.append((d,et,det,k))
        if k=='C': c+=1; lastC=max(lastC,d); attSince=0
        elif k=='A': a+=1; attSince+=1
        elif k=='B': bad+=1
    m=dict(zip(MC,med.get(mid,[None]*len(MC))))
    sf=[]
    if yes(m.get('liver')): sf.append('Liver')
    if yes(m.get('halluc')): sf.append('Halluc')
    if yes(m.get('dementia')): sf.append('Dementia')
    if yes(m.get('duopa')): sf.append('Duopa')
    if yes(m.get('dbs')): sf.append('DBS sched')
    q=set(quals.get(mid,set()))
    if yes(m.get('offb')): q.add('OFF signals')
    dnc_cand=1 if (bad>0 and c==0 and not e164(ap)) else 0
    dst.execute("INSERT INTO member_core VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (mid,fn or '',ln or '',city or '',st or '',pe,pe[-4:] if pe else '',age,status or 'Active',
       ';'.join(sorted(q)),';'.join(sf),c,a,lastC,attSince,refused,dnc_cand,doc or '',clinic or ''))
    dst.executemany("INSERT INTO comm_hist VALUES(?,?,?,?,?)",[(mid,)+h for h in hist[::-1][:40]])
    n+=1
dst.commit()
print(f'app.db built: {n} members (no emails, no street addresses imported), director={DIRECTOR}')
