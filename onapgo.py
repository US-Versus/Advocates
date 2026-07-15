"""Client-facing REAL-TIME ONAPGO report at /onapgo — a presentation-style deck that reproduces the
Research Catalyst "ONAPGO Patient Education" monthly report and ties the Patient Advocacy Center metrics
(Initial / Pre-HCP / Post-HCP call completions) to LIVE CRM data. Historical months (Jan-May 2026) are the
client-reviewed baked figures from the May deck; the current month(s) are computed live from the CRM's
`Connected — Guide completed (stage)` dispositions. Director + client roles only. Downloadable (print->PDF).

Self-contained add-on (like monitor.py): imports helpers from main, wired by ONE include line at the
bottom of main.py. Brand assets live in onapgo_assets/ and are served through /onapgo/asset/<name>.
"""
import os, re, datetime, hmac, hashlib
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, PlainTextResponse
from main import who, db, DEFAULT_TZ, _tz, DEV, _local_day_bounds_utc  # reuse identity + DB + tz + day-bounds

router = APIRouter()
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'onapgo_assets')

# PUBLIC_REPORT=1 turns THIS container (a 2nd, allow-unauthenticated Cloud Run service) into a
# password-only public report at /spn26 — no Google/IAP login, for the client (report.researchcat.com/spn26).
# A middleware then 404s every non-report path so the public surface can never reach any CRM endpoint.
PUBLIC_REPORT = os.environ.get('PUBLIC_REPORT') == '1'
REPORT_PW = os.environ.get('REPORT_PW')  # gate password supplied ONLY via Cloud Run env — never hardcode a secret


# Neutral cookie name — carries no client identifier (was 'spn'). Overridable via env.
COOKIE_NAME = os.environ.get('REPORT_COOKIE_NAME', 'rc_session')


def _cookie_val():
    secret = (os.environ.get('REPORT_COOKIE_SECRET') or REPORT_PW or 'rc-report-cookie-salt').encode()
    return hmac.new(secret, b'spn26-ok', hashlib.sha256).hexdigest()


def _cookie_ok(req: Request):
    t = req.cookies.get(COOKIE_NAME) or ''
    return bool(t) and hmac.compare_digest(t, _cookie_val())

# --- Baked, client-reviewed monthly figures from the May-2026 deck (slide 4). These are authoritative
# for Jan-May (pre-CRM); the CRM only began logging guide completions in July 2026. ------------------
HIST = {
    'initial':  {'2026-01': 46, '2026-02': 51, '2026-03': 43, '2026-04': 41, '2026-05': 123, '2026-06': 108},
    'pre_hcp':  {'2026-01': 58, '2026-02': 68, '2026-03': 73, '2026-04': 69, '2026-05': 220, '2026-06': 211},
    'post_hcp': {'2026-01': 50, '2026-02': 65, '2026-03': 59, '2026-04': 66, '2026-05': 165, '2026-06': 183},
}   # June from the advocate-provided "ONAPGO Report June 2026" (502 discussions: 108/211/183)
STAGES = [('initial', 'Initial Discussions'), ('pre_hcp', 'Pre-HCP Discussions'), ('post_hcp', 'Post-HCP Discussions')]
_MON = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


def _onapgo_clients():
    return set(x.strip().lower() for x in os.environ.get('ONAPGO_CLIENTS', '').split(',') if x.strip())


def _gate(req: Request):
    """Access to the ONAPGO report, by ANY of: (1) a valid password cookie (the /spn26 public flow,
    no Google login); (2) an enrolled director (IAP); (3) a client on the ONAPGO_CLIENTS allowlist (IAP).
    Clients need NO users row, so every OTHER CRM endpoint's who() rejects them — total report isolation."""
    if _cookie_ok(req):
        return {'email': 'spn26-client', 'display': 'Supernus', 'role': 'client'}
    email = req.headers.get('X-Goog-Authenticated-User-Email', '').split(':')[-1].lower()
    if not email and DEV:
        email = (req.query_params.get('as') or '').lower()
    if not email:
        raise HTTPException(401, 'No identity (IAP header missing)')
    row = db().execute("SELECT role, display FROM users WHERE email=? AND active=1", (email,)).fetchone()
    if row and row['role'] == 'director':
        return {'email': email, 'display': row['display'], 'role': 'director'}
    if email in _onapgo_clients():
        return {'email': email, 'display': email.split('@')[0], 'role': 'client'}
    raise HTTPException(403, 'The ONAPGO report is restricted to the program team and the client.')


def _live_by_month(c):
    """CRM guide-completions grouped by MOUNTAIN calendar month + stage: {'2026-07': {'initial': n, ...}}."""
    rows = c.execute("SELECT disposition, ts FROM dispositions WHERE disposition LIKE 'Connected — Guide completed%'").fetchall()
    tz = _tz(DEFAULT_TZ)
    out = {}
    for r in rows:
        d = r['disposition'] if not isinstance(r, (list, tuple)) else r[0]
        ts = r['ts'] if not isinstance(r, (list, tuple)) else r[1]
        m = re.search(r'\((\w+)\)', d or '')
        stg = m.group(1) if m else None
        if stg not in ('initial', 'pre_hcp', 'post_hcp'):
            continue
        try:                                            # ts is stored ~UTC (naive isoformat in the UTC container)
            dt = datetime.datetime.fromisoformat(str(ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            ym = dt.astimezone(tz).strftime('%Y-%m')    # Mountain calendar month
        except Exception:
            continue
        out.setdefault(ym, {'initial': 0, 'pre_hcp': 0, 'post_hcp': 0})[stg] += 1
    return out


@router.get('/api/onapgo/metrics')
def onapgo_metrics(req: Request):
    _gate(req); c = db()
    live = _live_by_month(c)
    baked_months = sorted({m for s in HIST.values() for m in s})           # 2026-01 .. 2026-05
    live_months = sorted(m for m, v in live.items() if m not in baked_months and sum(v.values()) > 0)  # e.g. 2026-07
    months = baked_months + live_months
    cols = []
    stages = {k: {} for k, _ in STAGES}
    for ym in months:
        is_live = ym in live_months
        cols.append({'ym': ym, 'label': _MON[int(ym[5:7])], 'year': ym[:4], 'live': is_live})
        for k, _ in STAGES:
            stages[k][ym] = (live.get(ym, {}).get(k, 0) if is_live else HIST[k].get(ym, 0))
    now_mt = datetime.datetime.now(_tz(DEFAULT_TZ))
    return {
        'months': cols, 'stages': stages,
        'stage_labels': {k: lbl for k, lbl in STAGES},
        'as_of': now_mt.strftime('%B %-d, %Y · %-I:%M %p') if os.name != 'nt' else now_mt.strftime('%B %d, %Y'),
        'as_of_iso': now_mt.isoformat(timespec='minutes'),
        'live_month': (_MON[int(live_months[-1][5:7])] if live_months else None),
    }


def _live_by_day(c, ym):
    """CRM guide-completions for month `ym`, grouped by LOCAL (Mountain) calendar day + stage."""
    rows = c.execute("SELECT disposition, ts FROM dispositions WHERE disposition LIKE 'Connected — Guide completed%'").fetchall()
    tz = _tz(DEFAULT_TZ)
    out = {}
    for r in rows:
        d = r['disposition'] if not isinstance(r, (list, tuple)) else r[0]
        ts = r['ts'] if not isinstance(r, (list, tuple)) else r[1]
        m = re.search(r'\((\w+)\)', d or '')
        stg = m.group(1) if m else None
        if stg not in ('initial', 'pre_hcp', 'post_hcp'):
            continue
        try:
            dt = datetime.datetime.fromisoformat(str(ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            key = dt.astimezone(tz).strftime('%Y-%m-%d')
        except Exception:
            continue
        if not key.startswith(ym):
            continue
        out.setdefault(key, {'initial': 0, 'pre_hcp': 0, 'post_hcp': 0})[stg] += 1
    return out


@router.get('/api/onapgo/live')
def onapgo_live(req: Request):
    """Real-time operations feed for the CURRENT month: MTD stage totals, per-day series,
    today's tally, and a simple linear pace projection vs the monthly branded-call target.
    This is what the July real-time interface polls (every ~25s)."""
    _gate(req)
    import calendar
    c = db()
    tz = _tz(DEFAULT_TZ)
    now = datetime.datetime.now(tz)
    ym = now.strftime('%Y-%m')
    byday = _live_by_day(c, ym)
    total = {'initial': 0, 'pre_hcp': 0, 'post_hcp': 0}
    days = []
    for day in sorted(byday):
        v = byday[day]
        for k in total:
            total[k] += v[k]
        days.append({'date': day, 'initial': v['initial'], 'pre_hcp': v['pre_hcp'],
                     'post_hcp': v['post_hcp'], 'total': v['initial'] + v['pre_hcp'] + v['post_hcp']})
    mtd = total['initial'] + total['pre_hcp'] + total['post_hcp']
    tkey = now.strftime('%Y-%m-%d')
    td = byday.get(tkey, {'initial': 0, 'pre_hcp': 0, 'post_hcp': 0})
    dim = calendar.monthrange(now.year, now.month)[1]
    dom = now.day
    projected = int(round(mtd / dom * dim)) if dom else mtd
    asof = now.strftime('%B %-d, %Y · %-I:%M %p') if os.name != 'nt' else now.strftime('%B %d, %Y · %I:%M %p')
    return {
        'month': _MON[now.month] + ' ' + str(now.year), 'ym': ym,
        'as_of': asof, 'as_of_iso': now.isoformat(timespec='minutes'),
        'stages': total, 'total': mtd,
        'today': {'initial': td['initial'], 'pre_hcp': td['pre_hcp'], 'post_hcp': td['post_hcp'],
                  'total': td['initial'] + td['pre_hcp'] + td['post_hcp']},
        'days': days, 'target': 500, 'projected': projected,
        'day_of_month': dom, 'days_in_month': dim,
    }


# Normalizers: map the guide's "check all that apply" option text (and stray free-text) to the short
# labels the report uses. First keyword hit wins; unmatched free-text is dropped from the tally.
# COMPLIANCE: never surface ONAPGO prescription/start status — disclosing that identifiable patients were
# prescribed the sponsor's drug is prohibited. There is deliberately NO mapping for the "prescribed ONAPGO /
# started ONAPGO" answer, so _tally drops it; _rx_scrub() also strips it from any free-text before display.
_TRT_MAP = [
    ('made no changes', 'No changes (revisit next appt)'),
    ('prescribed another', 'Prescribed another treatment'),
    ('dose/timing of my c/l', 'Changed dose / timing (C/L)'),
    ('dose/timing of my current medications', 'Changed dose / timing (not C/L)'),
    ('physical/occupational therapy', 'Suggested PT / OT / exercise'),
    ('deep brain', 'Suggested DBS'), ('dbs', 'Suggested DBS'),
    ('subcutaneous', 'Suggested another subq infusion'), ('subq', 'Suggested another subq infusion'),
    ('off symptoms not bad', 'OFF "not bad enough"'),
]
_BAR_MAP = [
    ('did not bring onapgo up', "Doctor didn't raise it"),
    ('other concerns', 'Other concerns discussed instead'),
    ("express my off", "Didn't express OFF time"),
    ('not interested', 'Not interested in ONAPGO'),
    ('much time', 'Doctor running behind'), ('running behind', 'Doctor running behind'),
    ('different treatment', 'Discussed a different treatment'),
    ('side effect', 'Worried about side effects'),
    ('cost', 'Concerned about cost'),
]

def _tally(rows, mapping):
    counts, order = {}, [lbl for _, lbl in mapping]
    for r in rows:
        ans = (r['answer'] if not isinstance(r, (list, tuple)) else r[0]) or ''
        n = (r['n'] if not isinstance(r, (list, tuple)) else r[1])
        for part in str(ans).split(';'):
            p = part.strip().lower()
            if not p:
                continue
            for kw, lbl in mapping:
                if kw in p:
                    counts[lbl] = counts.get(lbl, 0) + n
                    break
    seen = []
    for lbl in order:
        if lbl in counts and lbl not in [x[0] for x in seen]:
            seen.append([lbl, counts[lbl]])
    return sorted(seen, key=lambda x: -x[1])


# Additional post-HCP guide questions to surface (title, prompt LIKE, answer-normalizer or None, multi-select).
_POSTHCP_Q = [
    ('Are you still experiencing OFF time?', '%still experiencing OFF time and is it both%',
     [('disrupts my day', 'OFF disruptive & bothersome'), ('not bothersome', 'OFF present, not bothersome'), ('no longer', 'No longer experiencing OFF')], False),
    ('Requested ONAPGO® patient information?', '%Would you like the ONAPGO Patient Information sent%', None, False),
    ('Preferred delivery method', '%Preference on how it is sent%', [('email', 'Email'), ('mail', 'Mail')], False),
    ('Open to resources / earlier appointment?', '%receive feedback from patients in between%', None, False),
]

def _qbreak(c, like, prompt_like, mapping=None, split=False, topn=8):
    try:
        rows = c.execute("SELECT answer, COUNT(*) n FROM answers WHERE ts LIKE ? AND stage='post_hcp' AND prompt LIKE ? GROUP BY answer", (like, prompt_like)).fetchall()
    except Exception:
        return []
    counts = {}
    for r in rows:
        ans = (r['answer'] if not isinstance(r, (list, tuple)) else r[0]) or ''
        n = (r['n'] if not isinstance(r, (list, tuple)) else r[1])
        for part in (str(ans).split(';') if split else [str(ans)]):
            p = part.strip()
            if not p:
                continue
            if mapping:
                pl, lbl = p.lower(), None
                for kw, l in mapping:
                    if kw in pl:
                        lbl = l
                        break
                if lbl is None:
                    continue
            else:
                lbl = p if len(p) <= 44 else p[:44]
            counts[lbl] = counts.get(lbl, 0) + n
    return [[l, counts[l]] for l in sorted(counts, key=lambda x: -counts[x])][:topn]


def _rx_scrub(s):
    """COMPLIANCE guard: True if free text would disclose an ONAPGO prescription/start for a patient.
    Such rows are dropped before any display — the sponsor must never learn who was prescribed the drug."""
    t = (s or '').lower()
    if 'onapgo' not in t and 'apomorphine' not in t:
        return False
    return any(w in t for w in ('prescrib', 'started', 'starting', 'initiat', 'began', 'on onapgo',
                                'taking onapgo', 'using onapgo', 'on the pump', 'started the pump'))


@router.get('/api/onapgo/qual')
def onapgo_qual(req: Request):
    """Live qualitative panels for a month, computed from the CRM answers/comm_hist — so the
    current month's report renders the SAME panels as a finished month, populated in real time."""
    _gate(req)
    c = db()
    ym = req.query_params.get('ym') or datetime.datetime.now(_tz(DEFAULT_TZ)).strftime('%Y-%m')
    like = ym + '%'
    def arows(where, args):
        try:
            return [dict(r) for r in c.execute(
                "SELECT answer, COUNT(*) n FROM answers WHERE ts LIKE ? AND " + where + " GROUP BY answer", (like,) + args).fetchall()]
        except Exception:
            return []
    disc = arows("prompt LIKE ?", ('%discuss ONAPGO with your doctor at this recent appointment%',))
    yes = sum(r['n'] for r in disc if str(r['answer']).strip().lower() == 'yes')
    no = sum(r['n'] for r in disc if str(r['answer']).strip().lower() == 'no')
    barriers = _tally(arows("prompt LIKE ?", ('%Why do you think you were not able to discuss ONAPGO%',)), _BAR_MAP)
    treatment = _tally(arows("stage='post_hcp' AND prompt LIKE ?", ('%make any changes to your Parkinson%',)), _TRT_MAP)
    # member questions — real verbatim captures (not a synthetic tally)
    try:
        qrows = c.execute("SELECT answer, COUNT(*) n FROM answers WHERE ts LIKE ? AND (prompt LIKE ? OR prompt LIKE ?) GROUP BY answer ORDER BY n DESC",
                          (like, 'Member questions before closing%', 'Do you have any questions%')).fetchall()
    except Exception:
        qrows = []
    STOP = {'', 'no', 'none', 'n/a', 'na', 'no questions', 'no.', 'none.', 'no thank you', 'nope', '-', 'no thanks', 'no q', 'test', 'yes', 'no questions.'}
    questions, qtotal = [], 0
    for r in qrows:
        a = (r['answer'] if not isinstance(r, (list, tuple)) else r[0])
        n = (r['n'] if not isinstance(r, (list, tuple)) else r[1])
        s = str(a or '').strip()
        # keep only genuine member questions (contain a question mark), drop advocate notes / junk / Rx disclosures
        if s.lower() in STOP or len(s) < 6 or '?' not in s or _rx_scrub(s):
            continue
        qtotal += n
        if len(questions) < 12:
            questions.append([s[:150], n])
    try:
        h = c.execute("SELECT COUNT(*) n FROM comm_hist WHERE date LIKE ? AND event_type='HCP Appointment'", (like,)).fetchone()
        hcp_appts = (h['n'] if not isinstance(h, (list, tuple)) else h[0]) if h else 0
    except Exception:
        hcp_appts = 0
    posthcp = []
    for title, pl, mp, sp in _POSTHCP_Q:
        a = _qbreak(c, like, pl, mp, sp)
        if a:
            posthcp.append({'q': title, 'a': a})
    try:
        ap = c.execute("SELECT COUNT(*) n FROM answers WHERE ts LIKE ? AND stage='post_hcp' AND prompt LIKE ?", (like, '%next appointment scheduled%')).fetchone()
        appts_scheduled = (ap['n'] if not isinstance(ap, (list, tuple)) else ap[0]) if ap else 0
    except Exception:
        appts_scheduled = 0
    return {'ym': ym, 'discussed': {'yes': yes, 'no': no}, 'barriers': barriers,
            'treatment': treatment, 'questions': questions, 'questions_total': qtotal,
            'hcp_appts': hcp_appts, 'posthcp': posthcp, 'appts_scheduled': appts_scheduled}


@router.get('/api/onapgo/hcplog')
def onapgo_hcplog(req: Request):
    """Real-time HCP appointment / NPI log — one row per Post-HCP 'did you discuss ONAPGO'
    response captured this month, joined to the neurologist on file. Columns the report shows:
    NPI · Doctor · HCP appointment month · date logged · discussed-ONAPGO. Sorted by appointment
    month. De-identified: NO member name/id/phone leaves the endpoint. NPI is read defensively —
    member_core has no npi column yet, so we fall back to NULL until NPI capture is added (durable
    storage lands the moment that column exists; this endpoint then surfaces it with no change)."""
    _gate(req)
    c = db()
    ym = req.query_params.get('ym') or datetime.datetime.now(_tz(DEFAULT_TZ)).strftime('%Y-%m')
    like = ym + '%'
    disc_prompt = '%discuss ONAPGO with your doctor at this recent appointment%'
    # Appointment date ON FILE for the member. NOTE (data reality): the CRM keeps ONE evolving
    # appointment field (batch_members.hcp_date); the post-HCP guide's "next appointment" answer
    # rolls it forward, so for a post-HCP responder this is their NEXT / scheduled visit, not the
    # past one they're reporting on (the CRM doesn't durably store that past date). We surface the
    # scheduled visit honestly and let "Date Logged" be the firm per-response date. Prefer the
    # answer's own batch; fall back to the member's latest known appointment. Scalar — no fan-out.
    hcp_sub = ("COALESCE("
               "(SELECT bm.hcp_date FROM batch_members bm WHERE bm.member_id=a.member_id "
               "AND bm.batch_id=a.batch_id AND bm.hcp_date IS NOT NULL AND bm.hcp_date<>'' LIMIT 1),"
               "(SELECT bm.hcp_date FROM batch_members bm WHERE bm.member_id=a.member_id "
               "AND bm.hcp_date IS NOT NULL AND bm.hcp_date<>'' ORDER BY bm.hcp_date DESC LIMIT 1))")

    def _run(npi_sel):
        sql = ("SELECT " + npi_sel + " mc.doctor AS doctor, " + hcp_sub + " AS hcp_date, "
               "a.ts AS logged, a.answer AS discussed "
               "FROM answers a LEFT JOIN member_core mc ON mc.member_id=a.member_id "
               "WHERE a.ts LIKE ? AND a.prompt LIKE ?")
        return [dict(r) for r in c.execute(sql, (like, disc_prompt)).fetchall()]

    def _has_col(tbl, col):
        # metadata probe (no member data). Detect the npi column WITHOUT running a query that
        # would fail — a failed query aborts the Postgres transaction and would poison the real
        # SELECT that follows. sqlite (DEV) has no information_schema -> caught -> treated as absent.
        try:
            return bool(c.execute("SELECT 1 FROM information_schema.columns WHERE table_name=? AND column_name=?",
                                  (tbl, col)).fetchone())
        except Exception:
            return False

    has_npi_col = _has_col('member_core', 'npi')
    try:
        rows = _run("mc.npi AS npi," if has_npi_col else "NULL AS npi,")
    except Exception as e:
        try:
            c.rollback()          # clear any aborted tx so the request doesn't 500
        except Exception:
            pass
        print('onapgo_hcplog query failed:', str(e)[:200])   # empty log is otherwise silent to triage
        rows = []

    out, yes, no = [], 0, 0
    for r in rows:
        ans = str(r.get('discussed') or '').strip().lower()
        if ans == 'yes':
            yes += 1
        elif ans == 'no':
            no += 1
        hd = r.get('hcp_date') or ''
        out.append({
            'npi': (str(r.get('npi')).strip() if r.get('npi') else ''),
            'doctor': (str(r.get('doctor')).strip() if r.get('doctor') else ''),
            'appt_month': (hd[:7] if hd else ''),
            'appt_date': (hd[:10] if hd else ''),
            'logged': (str(r.get('logged') or '')[:10]),
            'discussed': ('Yes' if ans == 'yes' else ('No' if ans == 'no' else '')),
        })
    # sort by appointment month (unknown dates last), then by date logged
    out.sort(key=lambda x: (x['appt_month'] or '9999-99', x['logged']))
    npi_captured = sum(1 for x in out if x['npi'])
    return {'ym': ym, 'rows': out, 'total': len(out), 'yes': yes, 'no': no,
            'npi_captured': npi_captured, 'npi_column': has_npi_col}


@router.get('/api/onapgo/advocates')
def onapgo_advocates(req: Request):
    """Live advocate roster + clock status: each advocate is 'on shift' when their most recent
    time_punches row is an 'in'. Polled by the Live view so the roster lights up in real time."""
    _gate(req)
    c = db()
    try:
        advs = [dict(r) for r in c.execute("SELECT email, display FROM users WHERE role='advocate' AND active=1 ORDER BY display").fetchall()]
    except Exception:
        advs = []
    # latest punch per actor (id is monotonic → newest first)
    latest = {}
    try:
        for p in c.execute("SELECT actor, action, ts, signature FROM time_punches ORDER BY id DESC").fetchall():
            act = p['actor'] if not isinstance(p, (list, tuple)) else p[0]
            if act in latest:
                continue
            latest[act] = {'action': (p['action'] if not isinstance(p, (list, tuple)) else p[1]),
                           'ts': (p['ts'] if not isinstance(p, (list, tuple)) else p[2]),
                           'sig': (p['signature'] if not isinstance(p, (list, tuple)) else p[3])}
    except Exception:
        pass
    by_email = {a['email']: a['display'] for a in advs}
    out, seen = [], set()
    for a in advs:
        lp = latest.get(a['email'])
        out.append({'name': a['display'], 'clocked_in': bool(lp and lp['action'] == 'in'),
                    'since': (lp['ts'] if lp else None)})
        seen.add(a['email'])
    for act, lp in latest.items():
        if act in seen:
            continue
        out.append({'name': by_email.get(act) or lp.get('sig') or act.split('@')[0],
                    'clocked_in': lp['action'] == 'in', 'since': lp['ts']})
    out.sort(key=lambda x: (not x['clocked_in'], x['name']))
    return {'advocates': out, 'on_now': sum(1 for x in out if x['clocked_in']), 'total': len(out)}


@router.get('/api/onapgo/perf')
def onapgo_perf(req: Request):
    """Per-advocate daily performance — Calls / Assist / Forms for today (Mountain day) — for the race view."""
    _gate(req)
    c = db()
    ds, de = _local_day_bounds_utc(DEFAULT_TZ, None)
    lo = ds.replace(tzinfo=None).isoformat(); hi = de.replace(tzinfo=None).isoformat()
    try:
        advs = [dict(r) for r in c.execute("SELECT email, display FROM users WHERE role='advocate' AND active=1 AND email<>'support@researchcat.com' ORDER BY display").fetchall()]
    except Exception:
        advs = []
    out = []
    for a in advs:
        em = a['email']; calls = forms = assists = 0
        try:
            r = c.execute("SELECT COUNT(*) calls, "
                          "SUM(CASE WHEN disposition LIKE 'Connected — Guide completed%' AND disposition NOT LIKE '%(aivspd)%' THEN 1 ELSE 0 END) forms "
                          "FROM dispositions WHERE actor=? AND ts>=? AND ts<?", (em, lo, hi)).fetchone()
            if r: calls = r['calls'] or 0; forms = r['forms'] or 0
        except Exception:
            try: c.rollback()
            except Exception: pass
        try:
            ar = c.execute("SELECT COUNT(*) n FROM activity WHERE actor=? AND action='assist' AND ts>=? AND ts<?", (em, lo, hi)).fetchone()
            if ar: assists = ar['n'] or 0
        except Exception:
            try: c.rollback()
            except Exception: pass
        out.append({'name': a['display'], 'calls': calls, 'assists': assists, 'forms': forms})
    return {'advocates': out}


@router.get('/onapgo/asset/{name}')
def onapgo_asset(name: str, req: Request):
    _gate(req)                                          # director or allow-listed client (matches the report gate)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', name or ''):
        raise HTTPException(404, 'no')
    p = os.path.join(ASSET_DIR, name)
    if not os.path.isfile(p):
        raise HTTPException(404, 'no such asset')
    return FileResponse(p, headers={'Cache-Control': 'private, max-age=86400'})   # behind IAP — browser-only cache


@router.get('/onapgo', response_class=HTMLResponse)
def onapgo_report(req: Request):
    u = _gate(req)
    return HTMLResponse(ONAPGO_HTML.replace('__ME__', u['display']))


# ---- Public password-only entry at the BARE DOMAIN (report.researchcat.com): the client reaches the
# report WITHOUT any Google login — just the password. No client-identifying token appears anywhere on
# the public/pre-auth surface (URL path, page title, logo, or cookie). On success a signed cookie is set
# and the report is served in place at '/'. The GET entry is owned by the PUBLIC_REPORT middleware below.
DASHBOARD_HTML = r"""<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&display=swap" rel="stylesheet">
<title>ONAPGO® Patient Education — Program Report</title>
<style>
  .rc *{box-sizing:border-box;margin:0;padding:0}
  .rc{
    --teal:#65BC7B;--teal-d:#2F7D4A;--accent:#65BC7B;--accent-ink:#2F7D4A;--accent-wash:#eef7f1;--accent-line:#cfe7d6;
    --lime:#65BC7B;--cyan:#8FCBA0;--blue:#33475B;--amber:#FF5D29;--rust:#FF5D29;
    --slate:#2A3035;--heading:#0A0A0A;--ink:#3F3F3F;--ink-2:#555555;--muted:#666666;
    --line:#E7E7E7;--line-2:#efefef;--paper:#ffffff;--wash:#f4f4f4;--wash2:#eef7f1;--field:#F8F8F8;
    --navy:#0A0A0A;--navy2:#2A3035;--tile:#2A3035;--tile-2:#33475B;--tile-ink:#c9ced2;--tile-accent:#8FD6A2;
    --r-sm:8px;--r-md:10px;--r-lg:10px;--r-hero:12px;
    --sh-1:0 1px 2px rgba(10,10,10,.04);
    --sh-2:0 1px 3px rgba(10,10,10,.06);
    --sh-3:0 10px 30px rgba(10,10,10,.10);
    font-family:'Inter Tight','Helvetica Neue',Arial,sans-serif;color:var(--ink);background:var(--field);line-height:1.5;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums;
  }
  .rc{max-width:1200px;margin:0 auto;padding:18px}

  /* hero */
  .rc .hero{position:relative;overflow:hidden;border-radius:16px;background:var(--tile);color:#fff;padding:26px 32px 22px;box-shadow:0 18px 44px rgba(5,7,15,.28)}
  .rc .hero .bg{position:absolute;inset:0;background-size:cover;background-position:center;opacity:.28}
  .rc .hero .veil{position:absolute;inset:0;background:linear-gradient(105deg,var(--tile)F2 34%,#0b1120aa 100%)}
  .rc .hero .row{position:relative;z-index:2;display:flex;justify-content:space-between;align-items:flex-start;gap:24px;flex-wrap:wrap}
  .rc .hero .eyebrow{font-size:11.5px;letter-spacing:2.4px;text-transform:uppercase;color:#8FD6A2;font-weight:700}
  .rc .hero h1{font-size:26px;font-weight:700;color:#fff;margin-top:9px;letter-spacing:.2px;line-height:1.15;max-width:660px}
  .rc .hero .accent{width:70px;height:4px;background:var(--teal);border-radius:3px;margin-top:13px}
  .rc .hero .meta{position:relative;z-index:2;text-align:right;display:flex;flex-direction:column;gap:10px;align-items:flex-end}
  .rc .hero .logo{height:42px;filter:brightness(0) invert(1);opacity:.95}
  .rc .hero .period{font-size:12.5px;color:#c4d3e6}
  .rc .hero .period b{color:#fff;font-weight:700}
  .rc .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent);margin-right:6px;vertical-align:middle;box-shadow:0 0 0 0 rgba(101,188,123,.45);animation:pulse 1.6s infinite}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(101,188,123,.45)}70%{box-shadow:0 0 0 8px rgba(101,188,123,0)}100%{box-shadow:0 0 0 0 rgba(101,188,123,0)}}
  @keyframes flash{0%{background:#d8f3e9}100%{background:transparent}}
  .rc .flash{animation:flash 1s ease-out}

  /* mode switch */
  .rc .modeswitch{display:flex;gap:8px;margin-top:14px;background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:6px;width:fit-content;box-shadow:0 2px 8px rgba(31,42,55,.04)}
  .rc .mbtn{border:none;background:transparent;border-radius:9px;padding:9px 18px;font-size:13.5px;font-weight:700;color:var(--slate);cursor:pointer;font-family:inherit;display:flex;align-items:center;gap:7px}
  .rc .mbtn:hover{background:var(--wash)}
  .rc .mbtn.on{background:var(--teal);color:#fff}
  .rc .mbtn.on:hover{background:var(--teal)}
  .rc .mbtn .ld{width:8px;height:8px;border-radius:50%;background:var(--accent);animation:pulse 1.6s infinite}
  .rc .mbtn.on .ld{background:#eafff6}

  /* month tabs (reports) */
  .rc .nav{display:flex;gap:10px;margin-top:14px;overflow-x:auto;padding:4px 2px 8px}
  .rc .mtab{flex:0 0 auto;min-width:150px;background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:12px 16px;cursor:pointer;text-align:left;transition:all .12s;box-shadow:0 2px 8px rgba(31,42,55,.04)}
  .rc .mtab:hover{border-color:#bcd;transform:translateY(-1px)}
  .rc .mtab.on{border-color:var(--teal);box-shadow:0 0 0 2px var(--teal) inset,0 6px 16px rgba(101,188,123,.16)}
  .rc .mtab .mo{font-size:14px;font-weight:700;color:var(--slate)} .rc .mtab.on .mo{color:var(--teal-d)}
  .rc .mtab .st{font-size:11px;color:var(--muted);margin-top:3px}
  .rc .mtab .badge{display:inline-block;font-size:9.5px;font-weight:700;letter-spacing:.5px;color:#2F7D4A;background:var(--wash2);border:1px solid #b7e3d3;border-radius:10px;padding:1px 7px;margin-left:6px;vertical-align:middle}
  .rc .mtab .badge .d{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--accent);margin-right:4px;animation:pulse 1.6s infinite}

  /* KPI row */
  .rc .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-top:14px}
  .rc .kpi{background:var(--paper);border:1px solid var(--line);border-top:4px solid var(--teal);border-radius:12px;padding:16px;box-shadow:0 2px 8px rgba(31,42,55,.04)}
  .rc .kpi .n{font-size:32px;font-weight:700;color:var(--teal);line-height:1}
  .rc .kpi .n.sm{font-size:22px;padding-top:5px}
  .rc .kpi .l{font-size:12px;color:var(--slate);font-weight:700;margin-top:9px;line-height:1.25}
  .rc .kpi .s{font-size:11px;color:var(--muted);margin-top:5px;line-height:1.3}

  /* grid + panels */
  .rc .grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px;margin-top:14px}
  .rc .panel{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:18px 20px;box-shadow:0 2px 8px rgba(31,42,55,.04)}
  .rc .col-8{grid-column:span 8} .rc .col-7{grid-column:span 7} .rc .col-6{grid-column:span 6} .rc .col-5{grid-column:span 5} .rc .col-4{grid-column:span 4} .rc .col-12{grid-column:span 12}
  .rc .ph{display:flex;align-items:baseline;justify-content:space-between;gap:12px;border-bottom:2px solid var(--teal);padding-bottom:8px;margin-bottom:14px}
  .rc .ph h2{font-size:16px;color:var(--slate);font-weight:700} .rc .ph .sub{font-size:11.5px;color:var(--muted);font-weight:600;text-align:right}

  /* live: big number + counters */
  .rc .livehead{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--teal-d);font-weight:700}
  .rc .bignum{font-size:72px;font-weight:700;color:var(--teal);line-height:1;letter-spacing:-1px;border-radius:8px}
  .rc .biglbl{font-size:13px;color:var(--slate);font-weight:700;margin-top:6px}
  .rc .bigsub{font-size:11.5px;color:var(--muted);margin-top:4px}
  .rc .pbar{height:12px;background:var(--field);border-radius:8px;overflow:hidden;margin-top:14px}
  .rc .pfill{height:100%;border-radius:8px;background:linear-gradient(90deg,#65BC7B,#65BC7B);transition:width .6s}
  .rc .pacegrid{display:flex;justify-content:space-between;margin-top:8px;font-size:11.5px;color:var(--slate)}
  .rc .pacegrid b{color:var(--teal-d);font-weight:700}
  .rc .scards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
  .rc .scard{background:var(--wash);border:1px solid var(--line);border-top:4px solid var(--teal);border-radius:10px;padding:14px}
  .rc .scard .n{font-size:29px;font-weight:600;color:var(--accent-ink)}
  .rc .scard .l{font-size:11px;color:var(--slate);font-weight:600;margin-top:5px}
  .rc .scard .tdy{font-size:10.5px;color:var(--teal-d);font-weight:700;margin-top:4px}
  .rc .scard.today{border-top-color:var(--teal);background:linear-gradient(#eafff6,#f7fafc)}
  .rc .scard.today .n{color:var(--teal-d)}
  #confettiC{position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:99999}
  /* advocates on shift */
  .rc .advhead{font-size:12.5px;color:var(--slate);margin-bottom:12px} .rc .advhead b{color:var(--teal-d);font-size:16px}
  .rc .advgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
  .rc .advchip{display:flex;align-items:center;gap:10px;background:var(--wash);border:1px solid var(--line);border-radius:10px;padding:12px 14px;opacity:.6;transition:all .25s}
  .rc .advchip .advdot{width:11px;height:11px;border-radius:50%;background:#c2ccd8;flex:0 0 auto}
  .rc .advchip .advn{font-size:13px;font-weight:700;color:var(--slate)} .rc .advchip .advs{font-size:10.5px;color:var(--muted);margin-left:auto;font-weight:600}
  .rc .advchip.on{opacity:1;border-color:var(--teal);background:linear-gradient(#eafff6,#f7fafc);box-shadow:0 0 0 1px var(--teal),0 4px 14px rgba(101,188,123,.18)}
  .rc .advchip.on .advdot{background:var(--accent);box-shadow:0 0 0 0 rgba(101,188,123,.45);animation:pulse 1.6s infinite}
  .rc .advchip.on .advn{color:var(--teal-d)} .rc .advchip.on .advs{color:var(--teal-d)}
  .rc .advchip.onb{opacity:.8;border-style:dashed;background:var(--field)}
  .rc .advchip.onb .advdot{background:#C2CCD8}
  .rc .advchip.onb .advn{color:var(--slate)} .rc .advchip.onb .advs{color:var(--muted);font-weight:600}
  /* daily advocate performance — race view (green ramp: Calls light · Assist mid · Forms dark) */
  .rc .rleg{display:flex;gap:16px;font-size:11px;color:var(--muted);margin-bottom:12px}
  .rc .rleg i{display:inline-block;width:9px;height:9px;border-radius:2px;vertical-align:-1px;margin-right:5px}
  .rc .rsw.c{background:#9FD4B4}.rc .rsw.a{background:#65BC7B}.rc .rsw.f{background:#2F7D4A}
  .rc .race{display:flex;flex-direction:column;gap:14px}
  .rc .rlane{display:flex;align-items:center;gap:14px}
  .rc .rname{width:140px;flex:none;font-size:13px;font-weight:600;color:var(--heading);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .rc .rbars{flex:1;min-width:0}
  .rc .rrow{display:flex;align-items:center;gap:8px;margin:3px 0}
  .rc .rn{width:28px;flex:none;text-align:right;font-size:11px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--ink-2)}
  .rc .rtrack{flex:1;height:9px;background:var(--wash);border-radius:5px;overflow:hidden}
  .rc .rfill{height:100%;border-radius:5px;min-width:2px}
  .rc .rfill.c{background:#9FD4B4}.rc .rfill.a{background:#65BC7B}.rc .rfill.f{background:#2F7D4A}
  @media (max-width:900px){.rc .rname{width:104px;font-size:12px}}

  /* daily activity chart (stacked per day) */
  .rc .daychart{display:flex;align-items:flex-end;gap:5px;height:180px;padding-top:18px;border-bottom:2px solid var(--line)}
  .rc .dcol{flex:1;min-width:0;height:100%;display:flex;flex-direction:column;justify-content:flex-end;position:relative}
  .rc .dbar{width:100%;display:flex;flex-direction:column;border-radius:4px 4px 0 0;overflow:hidden;min-height:2px}
  .rc .dbar .seg{width:100%}
  .rc .dbar .si{background:#65BC7B} .rc .dbar .sp{background:#36AFCE} .rc .dbar .so{background:#F19D19}
  .rc .dcol .dt{position:absolute;top:-16px;left:0;right:0;text-align:center;font-size:9.5px;font-weight:700;color:var(--slate)}
  .rc .dxlab{display:flex;gap:5px;margin-top:6px}
  .rc .dxlab>div{flex:1;text-align:center;font-size:9px;color:var(--muted)}
  .rc .leg{display:flex;gap:16px;margin-top:14px;font-size:12px;font-weight:600;color:var(--slate);flex-wrap:wrap}
  .rc .leg i{display:inline-block;width:13px;height:13px;border-radius:3px;vertical-align:-2px;margin-right:6px}
  .rc .bi{background:#65BC7B} .rc .bp{background:#36AFCE} .rc .bo{background:#F19D19}

  /* tables */
  .rc table.rep{border-collapse:collapse;width:100%;font-size:12.5px}
  .rc table.rep th,.rc table.rep td{border:1px solid var(--line);padding:6px 9px;text-align:center;white-space:nowrap}
  .rc table.rep th{background:var(--slate);color:#fff;font-weight:700;font-size:11.5px}
  .rc table.rep td.lbl,.rc table.rep th.lbl{text-align:left;font-weight:700;color:var(--slate);background:var(--wash)}
  .rc table.rep tr.tot td{background:var(--wash2);font-weight:700;color:var(--teal-d)}
  .rc table.rep .sel{background:#e8f7f1} .rc table.rep th.sel{background:var(--teal)}

  /* reports: grouped bars */
  .rc .chartwrap{display:flex;flex-direction:column;gap:18px}
  .rc .chart{width:100%;padding-top:20px}
  .rc .bars{display:flex;align-items:flex-end;gap:30px;height:210px;padding:0 10px;border-bottom:2px solid var(--line)}
  .rc .grp{flex:1;min-width:0;display:flex;align-items:flex-end;justify-content:center;gap:10px;height:100%}
  .rc .grp.cur{background:linear-gradient(#1d9a7814,#1d9a7800);border-radius:6px 6px 0 0}
  .rc .bar{flex:1 1 0;max-width:38px;min-width:8px;border-radius:5px 5px 0 0;position:relative;min-height:3px}
  .rc .bar span{position:absolute;bottom:calc(100% + 5px);left:50%;transform:translateX(-50%);font-size:11px;font-weight:700;color:var(--slate)}
  .rc .barI{background:linear-gradient(#65BC7B,#65BC7B)} .rc .barP{background:linear-gradient(#57c6e6,#36AFCE)} .rc .barO{background:linear-gradient(#f7b13f,#F19D19)}
  .rc .xlab{display:flex;gap:30px;margin-top:8px;padding:0 10px} .rc .xlab>div{flex:1;text-align:center;font-size:12px;font-weight:700;color:var(--slate)} .rc .xlab .cur{color:var(--teal-d)}

  /* horizontal bars / hcp / donut / quotes / email */
  .rc .hbars{display:flex;flex-direction:column;gap:8px}
  .rc .hrow{display:grid;grid-template-columns:1fr auto;gap:8px 10px;align-items:center;font-size:12.5px}
  .rc .hrow .lab{color:var(--ink)} .rc .htrack{grid-column:1/2;height:9px;background:var(--field);border-radius:6px;overflow:hidden;margin-top:2px}
  .rc .hfill{height:100%;border-radius:6px;background:linear-gradient(90deg,#65BC7B,#65BC7B)} .rc .hrow .val{font-weight:700;color:var(--teal-d)}
  .rc .qfill{background:linear-gradient(90deg,#5aa0d0,#1D6FA9)} .rc .hrow.q .val{color:var(--blue)}
  .rc .hcp{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
  .rc .stat{background:var(--wash);border:1px solid var(--line);border-top:4px solid var(--teal);border-radius:10px;padding:14px}
  .rc .stat .n{font-size:26px;font-weight:600;color:var(--accent-ink)}
  .rc .stat .l{font-size:11px;color:var(--slate);font-weight:600;margin-top:5px}
  .rc .hcpband{margin-top:12px;background:var(--tile);color:#fff;border-radius:10px;padding:14px 16px;display:flex;align-items:center;gap:14px}
  .rc .hcpband .big{font-size:28px;font-weight:700;color:#8FD6A2} .rc .hcpband .t{font-size:12.5px;color:#c4d3e6}
  .rc .donutwrap{display:flex;gap:20px;align-items:center;flex-wrap:wrap}
  .rc .donut{position:relative;width:150px;height:150px;flex:0 0 auto}
  .rc .donut .ctr{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
  .rc .donut .ctr .p{font-size:30px;font-weight:700;color:var(--teal-d);line-height:1} .rc .donut .ctr .t{font-size:10.5px;color:var(--muted);font-weight:700;letter-spacing:.4px}
  .rc .dleg{font-size:12.5px;color:var(--slate)} .rc .dleg .r{display:flex;align-items:center;gap:8px;margin-bottom:7px} .rc .dleg i{width:12px;height:12px;border-radius:3px;display:inline-block}
  .rc .quote{background:var(--wash);border-left:4px solid var(--teal);border-radius:0 10px 10px 0;padding:12px 15px;font-size:12.5px;font-style:italic;color:#33424f;line-height:1.5}
  .rc .quote.b2{border-left-color:var(--cyan)} .rc .quote.b3{border-left-color:var(--amber)}
  .rc .qlist{display:flex;flex-direction:column;gap:8px}
  .rc .qitem{background:var(--wash);border-left:3px solid var(--cyan);border-radius:0 8px 8px 0;padding:9px 12px;font-size:12.5px;color:#33424f;font-style:italic}
  .rc .qn{font-style:normal;color:var(--muted);font-weight:700;font-size:11px}
  .rc .accum{background:var(--wash);border:1px dashed #cfd8e3;border-radius:10px;padding:16px;text-align:center;color:var(--muted);font-size:12px}
  /* post-HCP sub-blocks */
  .rc .phq{margin-bottom:12px}
  .rc .phq .qh{font-size:12px;font-weight:700;color:var(--slate);margin-bottom:6px}
  /* schedule of events */
  .rc .sched{display:flex;flex-direction:column}
  .rc .evrow{display:grid;grid-template-columns:58px 6px 1fr;gap:11px;align-items:center;padding:9px 4px;border-bottom:1px solid var(--line)}
  .rc .evrow:last-child{border-bottom:none}
  .rc .evdate{font-size:12px;font-weight:700;color:var(--slate);text-align:right;white-space:nowrap}
  .rc .evbar{width:6px;height:26px;border-radius:3px;background:var(--slate)}
  .rc .evbar.t-email{background:var(--blue)} .rc .evbar.t-webinar{background:var(--teal)} .rc .evbar.t-mailer{background:var(--amber)}
  .rc .evlab{font-size:12.5px;color:var(--ink)}
  .rc .ev-past{opacity:.5}
  .rc .ev-next{background:var(--wash2);border-radius:8px}
  .rc .evnext{background:var(--teal);color:#fff;font-size:9px;font-weight:700;padding:1px 7px;border-radius:10px;margin-left:6px;letter-spacing:.4px}
  .rc .evdone{color:var(--teal-d);font-size:10.5px;font-weight:700;margin-left:6px}
  .rc .evreq{background:var(--amber);color:#fff;font-size:9px;font-weight:700;padding:1px 7px;border-radius:10px;margin-left:6px;letter-spacing:.4px}
  .rc .ev-req{background:#fff7ec;border-radius:8px}
  .rc .evleg{display:flex;gap:16px;margin-top:12px;font-size:11.5px;font-weight:600;color:var(--slate);flex-wrap:wrap}
  .rc .evleg i{display:inline-block;width:11px;height:11px;border-radius:3px;vertical-align:-1px;margin-right:5px}
  .rc .etiles{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
  .rc .etile{background:var(--wash);border:1px solid var(--line);border-radius:10px;padding:12px;text-align:center}
  .rc .etile .n{font-size:20px;font-weight:700;color:var(--blue)} .rc .etile .l{font-size:10.5px;color:var(--slate);font-weight:600;margin-top:4px}
  .rc .note{font-size:11px;color:var(--muted);margin-top:10px;line-height:1.45}
  .rc .foot{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:11px;margin:18px 4px 6px;border-top:1px solid var(--line);padding-top:12px} .rc .foot b{color:var(--slate)}
  @media (max-width:900px){.rc .kpis,.rc .scards{grid-template-columns:repeat(2,1fr)}.rc .col-8,.rc .col-7,.rc .col-6,.rc .col-5,.rc .col-4{grid-column:span 12}.rc .etiles{grid-template-columns:repeat(2,1fr)}.rc .bignum{font-size:56px}}
  :root[data-theme="dark"] .rc,:root[data-theme="light"] .rc{background:var(--field);color:var(--ink)}

  /* ============ PLATFORM & ROADMAP ============ */
  .rc .betachip{display:inline-block;background:var(--amber);color:#fff;font-size:9.5px;font-weight:700;letter-spacing:.6px;padding:2px 8px;border-radius:10px;margin-right:6px;vertical-align:middle}
    .rc .psec>.ph2{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:4px}
  .rc .psec>.ph2 h2{font-weight:700;color:var(--slate)}
  .rc .psec>.ph2 .k{font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--teal-d)}
  .rc .psec>.psub{font-size:13.5px;color:var(--muted);margin-bottom:14px;max-width:760px;line-height:1.5}
  .rc .rmchip{display:inline-block;background:#eef4fb;color:var(--blue);border:1px solid #cfe0f2;font-size:9.5px;font-weight:700;letter-spacing:.5px;padding:2px 8px;border-radius:10px;margin-left:8px;vertical-align:middle}
  .rc .liveflag{display:inline-block;background:var(--wash2);color:var(--teal-d);border:1px solid #b7e3d3;font-size:9.5px;font-weight:700;letter-spacing:.5px;padding:2px 8px;border-radius:10px;margin-left:8px;vertical-align:middle}
  .rc .liveflag .d{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--accent);margin-right:4px;animation:pulse 1.6s infinite}

  /* thesis */
  .rc .thlead{max-width:820px}
  .rc .thlead p{font-size:14.5px;color:var(--ink);line-height:1.65;margin-bottom:12px}
  .rc .thlead p b{color:var(--slate)}
  .rc .thgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:14px}
  .rc .thstat{background:var(--tile);color:#fff;border-radius:12px;padding:16px 18px}
  .rc .thstat .n{font-size:30px;font-weight:700;color:#8FD6A2;letter-spacing:-.5px;font-variant-numeric:tabular-nums}
  .rc .thstat .l{font-size:11.5px;color:#c4d3e6;margin-top:6px;line-height:1.4}
  .rc .thstat .s{font-size:9.5px;color:#7d92ab;margin-top:8px;letter-spacing:.3px;text-transform:uppercase;font-weight:700}
  .rc .thstat.t2{background:var(--paper);border:1px solid var(--line)}
  .rc .thstat.t2 .n{color:var(--teal-d)} .rc .thstat.t2 .l{color:var(--ink)} .rc .thstat.t2 .s{color:var(--muted)}
  .rc .thsub{font-size:12px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--slate);margin-top:20px}
  .rc .srcline{font-size:11px;color:var(--slate);margin-top:26px;line-height:1.7;border-top:1px solid var(--line);padding-top:10px}

  /* app frame — the app's real tokens: navy #202C59 · cream #F5EFE1 · gold #C8A23C */
  .rc .appchrome{height:44px;background:#F5EFE1;border-bottom:1px solid rgba(32,44,89,.10);display:flex;align-items:center;justify-content:center;gap:1px;position:relative}
  .rc .awm{font-size:16px;font-weight:700;color:#202C59;letter-spacing:.5px}
  .rc .awv{font-family:Georgia,'Times New Roman',serif;font-style:italic;font-size:15px;font-weight:600;color:#C8A23C;padding:0 1px}
  .rc .awlive{position:absolute;right:10px;font-size:8.5px;font-weight:700;letter-spacing:.5px;color:#2F7D4A;background:#eafff6;border:1px solid #b7e3d3;border-radius:8px;padding:1px 6px}
  .rc .awlive .d{display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--accent);margin-right:3px;animation:pulse 1.6s infinite}
  .rc .cpill{display:inline-block;background:#F5EFE1;border:1px solid rgba(32,44,89,.14);color:#202C59;border-radius:999px;padding:3px 9px;font-size:10.5px;font-weight:600;margin:0 4px 5px 0}
  .rc .clusrow{margin-bottom:12px}
  .rc .clchip{display:inline-block;background:var(--wash);border:1px solid var(--line);border-radius:999px;padding:4px 11px;font-size:11px;color:var(--slate);font-weight:600;margin:0 6px 6px 0}
  .rc .clchip b{color:var(--teal-d)}

  /* the protocol article demo — the template's real tokens: #1e3a8a / #facc15 */
  .rc .artwrap{display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start}
  .rc .artdemo{flex:1.6;min-width:300px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:22px 24px;box-shadow:0 8px 28px rgba(30,58,138,.10)}
  .rc .abadge{font-size:10px;font-weight:700;color:#1e3a8a;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:6px 10px;display:inline-block}
  .rc .atitle{font-size:20px;font-weight:700;color:#1e3a8a;line-height:1.25;margin-top:12px}
  .rc .ameta{font-size:10.5px;color:#64748b;margin-top:4px;letter-spacing:.3px}
  .rc .abluf{background:#eff6ff;border-left:4px solid #1e3a8a;border-radius:8px;padding:13px 15px;font-size:13px;color:#1f2937;line-height:1.55;margin-top:14px}
  .rc .abluf .ah{font-size:9.5px;font-weight:700;letter-spacing:.7px;color:#1e3a8a;margin-bottom:5px}
  .rc .astat{background:linear-gradient(135deg,#1e3a8a,#312e81);color:#fff;border-radius:10px;padding:16px 18px;text-align:center;margin-top:12px}
  .rc .astat .al{font-size:9.5px;font-weight:700;letter-spacing:.8px;color:#c7d2fe}
  .rc .astat .an{font-size:40px;font-weight:700;color:#facc15;line-height:1.1;margin-top:4px}
  .rc .astat .at{font-size:11.5px;color:#e0e7ff;margin-top:6px;line-height:1.45;max-width:430px;margin-left:auto;margin-right:auto}
  .rc .avig{border-left:4px solid #facc15;background:#fefce8;border-radius:8px;padding:13px 15px;font-size:12.5px;font-style:italic;color:#374151;line-height:1.6;margin-top:12px}
  .rc .astrat{display:flex;gap:12px;margin-top:12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:13px 15px}
  .rc .asn{flex:0 0 34px;height:34px;border-radius:9px;background:#1e3a8a;color:#facc15;font-size:15px;font-weight:700;display:flex;align-items:center;justify-content:center}
  .rc .ast{font-size:13.5px;font-weight:700;color:#1e3a8a}
  .rc .awycdt{font-size:11.5px;color:#374151;line-height:1.5;margin-top:6px;background:#fefce8;border:1px dashed #eab308;border-radius:7px;padding:8px 10px}
  .rc .awycdt b{font-size:9px;letter-spacing:.7px;color:#a16207;display:block;margin-bottom:3px}
  .rc table.atable{border-collapse:collapse;width:100%;font-size:11.5px;margin-top:12px}
  .rc table.atable th{background:#1e3a8a;color:#fff;font-weight:700;padding:7px 10px;text-align:left;font-size:10.5px}
  .rc table.atable td{border:1px solid #e2e8f0;padding:7px 10px;color:#374151}
  .rc .acite{font-size:10.5px;color:#64748b;line-height:1.55;margin-top:12px;border-top:1px solid #e2e8f0;padding-top:10px}
  .rc .a911{background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:11px 13px;font-size:11px;color:#7f1d1d;line-height:1.5;margin-top:12px}
  .rc .acta{background:linear-gradient(135deg,#111827,#1e3a8a);border-radius:10px;padding:16px;text-align:center;margin-top:12px}
  .rc .acta b{display:block;color:#fff;font-size:14px} .rc .acta span{display:inline-block;background:#facc15;color:#1e3a8a;font-size:12px;font-weight:700;border-radius:8px;padding:9px 18px;margin-top:9px} .rc .acta i{display:block;font-size:9.5px;color:#9ca3af;margin-top:7px;font-style:normal}
  .rc .artbtn{display:block;width:100%;margin-top:14px;background:#fff;border:2px solid #1e3a8a;color:#1e3a8a;font-size:12.5px;font-weight:700;border-radius:10px;padding:10px;cursor:pointer;font-family:inherit}
  .rc .artbtn:hover{background:#eff6ff}
  .rc .artside{flex:1;min-width:250px;display:flex;flex-direction:column;gap:12px}

  /* the reviewer console mock — the app's real cream/navy/gold */
  .rc .revwrap{display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start}
  .rc .revmock{flex:1.4;min-width:300px;max-width:520px;background:#F5EFE1;border:1px solid rgba(32,44,89,.14);border-radius:18px;padding:16px;box-shadow:0 10px 30px rgba(32,44,89,.14)}
  .rc .rvbeta{font-size:9px;font-weight:700;letter-spacing:.6px;color:#B74919;background:#fff3ec;border:1px solid #f0cdb8;border-radius:7px;padding:3px 8px;display:inline-block}
  .rc .rvcrumb{font-size:10px;color:#586179;margin-top:8px;font-weight:600}
  .rc .rvtitle{font-size:16.5px;font-weight:700;color:#202C59;margin-top:3px;line-height:1.25}
  .rc .rvmeta{font-size:11px;color:#586179;margin-top:3px} .rc .rvmeta b{color:#7A6015}
  .rc .rvcard{background:#FAF6EA;border:1px solid rgba(32,44,89,.10);border-radius:14px;padding:12px 14px;margin-top:10px}
  .rc .rvch{font-size:11px;font-weight:700;color:#202C59;display:flex;justify-content:space-between;gap:8px;align-items:baseline}
  .rc .rvch em{font-size:9px;color:#586179;font-weight:600;font-style:normal;letter-spacing:.2px}
  .rc .rvpass{font-size:12px;font-weight:700;color:#2E7D46;margin-top:7px}
  .rc .rvdom{font-size:10.5px;color:#586179;padding:5px 0;border-top:1px dashed rgba(32,44,89,.12);display:flex;justify-content:space-between}
  .rc .rvdom span{color:#2E7D46;font-weight:700}
  .rc .rvsec{font-size:8.5px;font-weight:700;letter-spacing:.8px;color:#586179;margin-top:10px}
  .rc .rvsent{font-size:12px;color:#1C2540;line-height:1.55;padding:8px 10px;border-radius:9px;cursor:pointer;margin-top:4px;border:1px dashed transparent;transition:all .12s}
  .rc .rvsent:hover{background:#fff;border-color:rgba(32,44,89,.2)}
  .rc .rvsent.sel{background:#fff;border-color:#C8A23C;box-shadow:0 0 0 2px #f1e6c4}
  .rc .rvsent.flag{background:#FAF6EA;border-color:#C8A23C}
  .rc .rvsheet{background:#fff;border:1px solid rgba(32,44,89,.16);border-radius:14px;padding:13px 15px;margin-top:10px;box-shadow:0 -6px 24px rgba(32,44,89,.12)}
  .rc .rvq{font-size:10.5px;font-style:italic;color:#586179;line-height:1.45}
  .rc .rvradio{display:flex;gap:7px;margin-top:9px}
  .rc .rvradio span{font-size:10.5px;font-weight:700;border:1.5px solid rgba(32,44,89,.2);color:#586179;border-radius:999px;padding:4px 12px}
  .rc .rvradio span.on{background:#202C59;border-color:#202C59;color:#fff}
  .rc .rvlab{font-size:9.5px;font-weight:700;color:#202C59;margin-top:9px}
  .rc .rvbox{font-size:11px;color:#9aa2b5;border:1px solid rgba(32,44,89,.16);border-radius:9px;padding:9px 11px;margin-top:4px;background:#fff}
  .rc .rvbtns{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}
  .rc .ghostb{font-size:11px;font-weight:700;color:#202C59;border:1.5px solid rgba(32,44,89,.25);border-radius:10px;padding:7px 13px;cursor:pointer}
  .rc .solidb{font-size:11px;font-weight:700;color:#fff;background:#202C59;border-radius:10px;padding:7px 13px;cursor:pointer}
  .rc .rvchanges{margin-top:10px;background:#FAF6EA;border:1px solid rgba(32,44,89,.10);border-radius:14px;padding:12px 14px}
  .rc .rvchg{font-size:11px;color:#1C2540;margin-top:6px} .rc .rvchg em{display:block;font-size:9.5px;color:#586179;font-style:normal;margin-top:2px}
  .rc .flagchip{font-size:9px;font-weight:700;background:#fff3ec;color:#B74919;border-radius:7px;padding:2px 7px;margin-right:4px}
  .rc .rvbar{display:flex;gap:7px;margin-top:12px}
  .rc .rvbar span{flex:1;text-align:center;font-size:11px;font-weight:700;border-radius:12px;padding:11px 4px;cursor:pointer}
  .rc .rvappr{background:#2E7D46;color:#fff} .rc .rvappr:hover{background:#256b3a}
  .rc .rvedit{border:2px solid #202C59;color:#202C59} .rc .rvrev{border:2px solid rgba(32,44,89,.25);color:#586179}
  .rc .rvdone{margin-top:12px}
  .rc .rvattr{background:#fff;border:2px solid #C8A23C;border-radius:14px;padding:13px 15px;font-size:12px;color:#1C2540;line-height:1.6}
  .rc .rvah{font-size:8.5px;font-weight:700;letter-spacing:.8px;color:#7A6015;margin-bottom:5px}
  .rc .rvsucc{background:#202C59;color:#fff;border-radius:14px;padding:14px 16px;font-size:13px;font-weight:700;margin-top:9px;line-height:1.6}
  .rc .rvsucc b{color:#C8A23C;font-size:17px} .rc .rvsucc span{font-size:10.5px;color:#c7d3ec;font-weight:600}
  .rc .rvreset{font-size:10.5px;color:#586179;text-decoration:underline;cursor:pointer;margin-top:8px;text-align:center}
  .rc .revside{flex:1;min-width:260px;display:flex;flex-direction:column;gap:12px}

  /* compliance engine extras */
  .rc .codeblk{background:#0d1526;color:#d7e3f4;border:1px solid #1d2a44;border-radius:10px;padding:13px 15px;font-family:Consolas,Menlo,monospace;font-size:11px;line-height:1.6;overflow-x:auto;white-space:pre;margin:0}
  .rc .gateread{margin-top:10px;border-radius:10px;padding:10px 13px;font-size:12.5px;font-weight:600}
  .rc .gateread.pass{background:var(--wash2);border:1px solid #b7e3d3;color:#0f5c47}
  .rc .gateread.fail{background:#fdecec;border:1px solid #f5c2c2;color:#8a1f24}
  .rc .glight{cursor:pointer} .rc .glight:hover{border-color:#bcd}
  .rc .conout{margin-top:12px;background:#0d1526;color:#c7d3e8;border-radius:10px;padding:12px 14px;font-family:Consolas,Menlo,monospace;font-size:10.5px;line-height:1.7;overflow-x:auto}
  .rc .conout .coh{font-family:Arial,sans-serif;font-size:9px;font-weight:700;letter-spacing:.7px;color:#7d92ab;text-transform:uppercase;margin-bottom:6px}
  .rc .cofail{color:#ff8a8a;font-weight:700}
  .rc .rulegrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin-top:16px}
  .rc .rulecard{background:var(--paper);border:1px solid var(--line);border-top:4px solid var(--slate);border-radius:12px;padding:11px 13px}
  .rc .rid{font-family:Consolas,Menlo,monospace;font-size:11px;font-weight:700;background:var(--wash);border:1px solid var(--line);border-radius:6px;padding:1px 7px;color:var(--slate)}
  .rc .rsev{font-size:8.5px;font-weight:700;letter-spacing:.5px;color:#8a1f24;background:#fdecec;border:1px solid #f5c2c2;border-radius:7px;padding:2px 7px;margin-left:6px}
  .rc .rsev.adv{color:#7a5c14;background:#fdf6e3;border-color:#ecd9a0}
  .rc .rtx{font-size:11.5px;color:var(--ink);line-height:1.5;margin-top:7px}
  .rc .trirow{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:16px}
  .rc .tri{border-radius:12px;padding:14px 16px;border:1px solid var(--line);background:var(--paper);border-top:4px solid var(--slate)}
  .rc .tri.att{border-top-color:#B74919} .rc .tri.mds{border-top-color:var(--cyan)} .rc .tri.cmo{border-top-color:#6ba52f}
  .rc .tri .th{font-size:13px;font-weight:700;color:var(--slate)} .rc .tri .th i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:1px}
  .rc .tri .tb{font-size:11.5px;color:var(--ink);line-height:1.55;margin-top:7px}
  .rc .scalegrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
  .rc .scstat{background:var(--paper);border:1px solid var(--line);border-top:4px solid var(--teal);border-radius:12px;padding:14px 16px}
  .rc .scstat .n{font-size:26px;font-weight:700;color:var(--teal-d);letter-spacing:-.4px;font-variant-numeric:tabular-nums}
  .rc .scstat .l{font-size:11.5px;color:var(--ink);font-weight:700;margin-top:5px;line-height:1.35}
  .rc .scstat .s{font-size:9.5px;color:var(--muted);margin-top:5px;text-transform:uppercase;letter-spacing:.3px;font-weight:700}

  /* ===== App Launch v2: brand mark, product tour, design sweep ===== */
  .rc .psec{margin-top:42px}
  .rc .psec>.ph2 h2{font-size:23px;letter-spacing:-.3px}
  .rc .psec>.ph2 .k{color:var(--teal-d);opacity:.85}
  .rc .rvl{opacity:0;transform:translateY(14px);transition:opacity .55s ease,transform .55s ease}
  .rc .rvl.vis{opacity:1;transform:none}
  /* live brand mark */
  .rc .vplogo{display:inline-flex;align-items:center;gap:7px}
  .rc .vpword{display:inline-flex;align-items:center;font-weight:700;color:#202C59;letter-spacing:.3px;line-height:1}
  .rc .vpword i{display:inline-block;background:#C8A23C}
  .rc .vpword i.d{width:.17em;height:.17em;border-radius:50%;margin:0 .07em 0 .06em;transform:translateY(-.02em)}
  .rc .vpword i.b{width:.1em;height:.62em;border-radius:.05em;transform:skewX(-14deg);margin:0 .14em}
  .rc .vpword b{color:#586179;font-weight:700}
  /* phone shell for the tour */
  .rc .pshell{width:288px;max-width:100%;background:#F5EFE1;border:8px solid #0b1120;border-radius:30px;overflow:hidden;box-shadow:0 20px 46px rgba(14,21,36,.22)}
  .rc .pph{height:42px;background:#F5EFE1;border-bottom:1px solid rgba(32,44,89,.10);display:flex;align-items:center;justify-content:space-between;padding:0 12px}
  .rc .pham{display:inline-flex;flex-direction:column;gap:3px;width:18px}
  .rc .pham i{height:2px;background:#202C59;border-radius:2px;display:block}
  .rc .ppsr{width:26px;height:26px;border-radius:50%;border:1.5px solid #202C59;display:flex;align-items:center;justify-content:center}
  .rc .ppsr i{display:block;width:9px;height:9px;border:1.5px solid #202C59;border-radius:50%;position:relative;margin:-2px 0 0 -2px}
  .rc .ppsr i:after{content:"";position:absolute;width:5px;height:1.5px;background:#202C59;transform:rotate(45deg);right:-4px;bottom:-1px}
  .rc .pbody{height:470px;overflow:hidden;position:relative}
  .rc .scr-pad{padding:14px 14px 0}
  .rc .th1{font-size:17px;font-weight:700;color:#202C59;line-height:1.2}
  .rc .th2{font-size:12.5px;font-weight:700;color:#202C59;margin-top:12px}
  .rc .tintro{font-size:10.5px;color:#586179;line-height:1.5;margin-top:6px}
  /* landing */
  .rc .scr-land{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:20px 18px;gap:9px}
  .rc .mbpill{background:#F1E6C4;color:#7A6015;font-size:8.5px;font-weight:700;letter-spacing:.8px;border-radius:999px;padding:4px 11px}
  .rc .lh{font-family:Georgia,'Times New Roman',serif;font-size:21px;font-weight:600;color:#202C59;line-height:1.22;max-width:230px}
  .rc .ls{font-size:11px;color:#586179;line-height:1.55;max-width:230px}
  .rc .ls i{font-style:italic}
  .rc .goldbtn{background:#C8A23C;color:#202C59;font-size:12px;font-weight:700;border-radius:14px;padding:12px 22px;margin-top:6px}
  .rc .lbeta{font-size:8.5px;color:#8a93a8;line-height:1.5;max-width:230px;margin-top:8px}
  /* triage */
  .rc .scr-strip{height:26px;background:#202C59;color:#fff;font-size:8.5px;font-weight:600;display:flex;align-items:center;justify-content:center;letter-spacing:.2px}
  .rc .tsearch{display:flex;align-items:center;gap:8px;border:1.5px solid #202C59;border-radius:12px;background:#fff;padding:9px 6px 9px 11px;margin-top:10px}
  .rc .tmag{color:#8a93a8;font-size:13px;font-weight:700} .rc .tph{flex:1;font-size:10.5px;color:#8a93a8}
  .rc .tmic{width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,#202C59,#172554);color:#fff;font-size:12px;display:flex;align-items:center;justify-content:center}
  .rc .tpills{display:flex;gap:6px;margin-top:10px;overflow:hidden;mask-image:linear-gradient(90deg,#000 82%,transparent);-webkit-mask-image:linear-gradient(90deg,#000 82%,transparent)}
  .rc .tpills span{flex:0 0 auto;background:#C8A23C;color:#202C59;font-size:8.5px;font-weight:700;border-radius:999px;padding:5px 10px;white-space:nowrap}
  .rc .tfilter{display:flex;justify-content:space-between;align-items:center;background:#FAF6EA;border-top:1px solid rgba(32,44,89,.1);border-bottom:1px solid rgba(32,44,89,.1);margin:10px -14px 0;padding:7px 14px;font-size:9.5px;color:#586179}
  .rc .tfilter b{color:#202C59;font-size:10px}
  .rc .tcard{background:#fff;border:1px solid rgba(32,44,89,.1);border-radius:14px;padding:11px 12px;margin-top:10px;box-shadow:0 1px 3px rgba(32,44,89,.08)}
  .rc .tbrow{display:flex;gap:5px;flex-wrap:wrap}
  .rc .tmds{background:#202C59;color:#fff;font-size:8px;font-weight:700;border-radius:6px;padding:2.5px 7px}
  .rc .thelp{background:#F1E6C4;color:#7A6015;font-size:8px;font-weight:700;border-radius:6px;padding:2.5px 7px}
  .rc .tct{font-size:11.5px;font-weight:700;color:#202C59;line-height:1.3;margin-top:7px}
  .rc .tcs{font-size:9px;color:#586179;line-height:1.45;margin-top:4px}
  .rc .tcb{display:flex;justify-content:space-between;align-items:center;margin-top:8px}
  .rc .tclu{background:#C8A23C;color:#202C59;font-size:8px;font-weight:700;border-radius:999px;padding:3px 9px}
  .rc .tchev{color:#202C59;font-size:14px;font-weight:700}
  /* ask */
  .rc .tnote{background:#fff;border:1px solid rgba(32,44,89,.12);border-radius:12px;padding:8px 10px;font-size:9px;color:#586179;line-height:1.5;margin-top:8px}
  .rc .bub{display:inline-block;max-width:86%;border-radius:14px;padding:8px 11px;font-size:9.5px;line-height:1.5;margin-top:9px}
  .rc .bub.u{background:#202C59;color:#fff;float:right;clear:both}
  .rc .bub.a{background:#FAF6EA;color:#1C2540;float:left;clear:both;border:1px solid rgba(32,44,89,.08)}
  .rc .bub .cite{display:block;font-size:8px;color:#202C59;opacity:.75;margin-top:5px;font-weight:600}
  .rc .tinput{display:flex;gap:7px;align-items:center;clear:both;padding-top:12px}
  .rc .tinput span{flex:1;border:1px solid rgba(32,44,89,.14);background:#fff;border-radius:12px;padding:10px 11px;font-size:9.5px;color:#8a93a8}
  .rc .tinput b{background:#202C59;color:#fff;font-size:10px;font-weight:700;border-radius:12px;padding:10px 16px}
  /* records */
  .rc .tdash{border:2px dashed #202C59;background:#F5EFE1;border-radius:14px;padding:16px;text-align:center;margin-top:10px}
  .rc .tdash b{display:block;font-size:12px;color:#202C59} .rc .tdash span{display:block;font-size:9px;color:#586179;margin-top:3px}
  .rc .trec{background:#fff;border:1px solid rgba(32,44,89,.1);border-radius:12px;padding:9px 11px;font-size:10px;font-weight:600;color:#1C2540;margin-top:7px;display:flex;justify-content:space-between;align-items:center}
  .rc .tread{background:#F1E6C4;color:#202C59;font-size:7.5px;font-weight:700;border-radius:999px;padding:2px 8px}
  /* support */
  .rc .tcta{background:#202C59;border-radius:14px;padding:13px;margin-top:10px}
  .rc .teb{font-size:8px;font-weight:700;letter-spacing:.8px;color:#C8A23C}
  .rc .tch{font-size:13.5px;font-weight:700;color:#fff;line-height:1.25;margin-top:4px}
  .rc .tinner{background:#fff;border-radius:11px;padding:9px 11px;margin-top:9px;display:flex;gap:9px;align-items:center}
  .rc .tav{width:34px;height:34px;border-radius:50%;background:#C8A23C;display:flex;align-items:center;justify-content:center;font-size:15px;flex:0 0 auto}
  .rc .tinner b{display:block;font-size:10.5px;color:#202C59} .rc .tinner span{display:block;font-size:8px;color:#586179;margin-top:1px}
  .rc .tghost{border:1.5px solid #fff;color:#fff;font-size:9.5px;font-weight:700;border-radius:11px;padding:8px;text-align:center;margin-top:9px}
  .rc .tfoot{font-size:8.5px;font-style:italic;color:#586179;text-align:center;margin-top:9px}
  /* doctor console */
  .rc .dbeta{border:2px solid #C8A23C;background:#F1E6C4;border-radius:10px;padding:5px 9px;font-size:8.5px;font-weight:700;color:#202C59}
  .rc .drow{display:flex;gap:9px;align-items:center;margin-top:10px}
  .rc .dav{width:32px;height:32px;border-radius:50%;background:#202C59;color:#fff;font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;flex:0 0 auto}
  .rc .drow b{display:block;font-size:12.5px;color:#202C59} .rc .drow span{display:block;font-size:8.5px;color:#586179}
  .rc .dearn{background:linear-gradient(135deg,#202C59,#172554);border-radius:14px;padding:12px 13px;margin-top:10px}
  .rc .de1{font-size:8.5px;color:rgba(255,255,255,.7)}
  .rc .de2{font-size:11px;color:rgba(255,255,255,.85);margin-top:4px} .rc .de2 b{font-size:19px;font-weight:700;color:#fff}
  .rc .de3{display:flex;gap:6px;margin-top:8px}
  .rc .dgold{background:rgba(255,255,255,.15);color:#fff;font-size:8px;font-weight:700;border-radius:999px;padding:3px 8px}
  .rc .dbet{background:#F1E6C4;color:#7A6015;font-size:8px;font-weight:700;border-radius:999px;padding:3px 8px}
  .rc .dq{background:#fff;border:1px solid rgba(32,44,89,.1);border-radius:12px;padding:9px 10px;margin-top:7px;display:flex;gap:8px;align-items:center}
  .rc .dd{width:8px;height:8px;border-radius:50%;flex:0 0 auto} .rc .dd.y{background:#C8A23C} .rc .dd.n{background:#202C59}
  .rc .dq div{flex:1;min-width:0} .rc .dq b{display:block;font-size:9.5px;color:#202C59;line-height:1.25} .rc .dq div span{display:block;font-size:8px;color:#586179;margin-top:2px}
  .rc .dt{border:1px solid rgba(32,44,89,.18);color:#586179;font-size:8px;font-weight:600;border-radius:999px;padding:2px 7px;white-space:nowrap}
  .rc .dp{background:rgba(46,125,70,.1);color:#2E7D46;font-size:8px;font-weight:700;border-radius:999px;padding:2px 8px}
  /* tour layout */
  .rc .tour{display:flex;flex-direction:column;gap:44px;margin-top:8px}
  .rc .fb{display:flex;gap:40px;align-items:center;flex-wrap:wrap}
  .rc .fb .fbphone{flex:0 0 auto;margin:0 auto}
  .rc .fb .fbcopy{flex:1;min-width:270px;max-width:520px}
  .rc .fb.rev{flex-direction:row-reverse}
  .rc .fbeb{font-size:10px;font-weight:700;letter-spacing:.9px;text-transform:uppercase;color:var(--teal-d)}
  .rc .fbcopy h3{font-size:20px;font-weight:700;color:var(--slate);letter-spacing:-.2px;margin-top:7px;line-height:1.25}
  .rc .fbcopy p{font-size:13.5px;color:var(--ink);line-height:1.65;margin-top:9px}
  .rc .fbchk{list-style:none;margin-top:12px;padding:0}
  .rc .fbchk li{position:relative;padding:6px 0 6px 26px;font-size:12.5px;color:var(--slate);font-weight:600;line-height:1.45}
  .rc .fbchk li:before{content:"✓";position:absolute;left:0;top:5px;width:17px;height:17px;border-radius:50%;background:var(--wash2);color:var(--teal-d);font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;border:1px solid #b7e3d3}
  @media (max-width:760px){.rc .fb,.rc .fb.rev{flex-direction:column}.rc .tour{gap:34px}}

  /* ===== App Launch v3: 6-section narrative ===== */
  /* 01 problem — channel decline */
  .rc .declrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:6px}
  .rc .declcard{background:#0b1120;color:#fff;border-radius:14px;padding:18px 20px;position:relative;overflow:hidden}
  .rc .dch{font-size:11px;font-weight:700;letter-spacing:.7px;text-transform:uppercase;color:#9fb3c8}
  .rc .declbars{display:flex;align-items:flex-end;gap:5px;height:44px;margin:12px 0 10px}
  .rc .declbars span{flex:1;background:#33445f;border-radius:3px 3px 0 0}
  .rc .declbars span.last{background:var(--rust)}
  .rc .decln{font-size:38px;font-weight:700;color:#f0a58c;letter-spacing:-1px;line-height:1;font-variant-numeric:tabular-nums}
  .rc .decll{font-size:12px;color:#c4d3e6;line-height:1.45;margin-top:8px}
  .rc .decls{font-size:9.5px;color:#7d92ab;margin-top:9px;letter-spacing:.3px;text-transform:uppercase;font-weight:700}
  .rc .accel{margin-top:16px;background:var(--wash2);border:1px solid #b7e3d3;border-radius:12px;padding:15px 18px;font-size:13.5px;color:#0f5c47;line-height:1.6}
  .rc .accel b{color:var(--teal-d)}
  /* 02 solution — two-sided */
  .rc .soltop{font-size:15px;color:var(--ink);line-height:1.65;max-width:820px}
  .rc .soltop b{color:var(--slate)}
  .rc .twoside{display:flex;gap:16px;align-items:stretch;flex-wrap:wrap;margin-top:16px}
  .rc .tscard{flex:1;min-width:250px;border-radius:14px;padding:18px 20px;border:1px solid var(--line)}
  .rc .tscard.pt{background:linear-gradient(160deg,#eef6f2,#fbfdfc);border-color:#b7e3d3}
  .rc .tscard.dr{background:linear-gradient(160deg,#eef4fb,#fbfcff);border-color:#cfe0f2}
  .rc .tsh{font-size:10.5px;font-weight:700;letter-spacing:.7px;text-transform:uppercase}
  .rc .tscard.pt .tsh{color:var(--teal-d)} .rc .tscard.dr .tsh{color:var(--blue)}
  .rc .tst{font-size:17px;font-weight:700;color:var(--slate);margin-top:6px}
  .rc .tsb{font-size:12.5px;color:var(--ink);line-height:1.55;margin-top:8px}
  .rc .tsplus{display:flex;align-items:center;font-size:26px;font-weight:300;color:var(--muted)}
  /* 03 call centerpiece */
  .rc .ccstage{display:flex;gap:26px;align-items:center;flex-wrap:wrap;background:#0b1120;border-radius:18px;padding:24px 28px;color:#fff}
  .rc .ccstage .ccphone{flex:0 1 auto;min-width:0;max-width:100%;margin:0 auto}
  .rc .cccopy{flex:1;min-width:280px}
  .rc .cceb{font-size:10.5px;font-weight:700;letter-spacing:1px;color:var(--accent,#C8A23C)}
  .rc .cccopy h3{font-size:20px;font-weight:700;color:#fff;line-height:1.28;margin-top:8px}
  .rc .cccopy .cchi{color:#8FD6A2}
  .rc .cccopy p{font-size:13.5px;color:#c4d3e6;line-height:1.6;margin-top:10px}
  .rc .ccbtn{display:inline-block;margin-top:16px;background:#C8A23C;color:#202C59;font-size:15px;font-weight:700;border-radius:14px;padding:14px 26px;box-shadow:0 10px 26px rgba(200,162,60,.28)}
  .rc .ccsub{font-size:10.5px;color:#8ea1ba;margin-top:9px;line-height:1.5}
  .rc .ccflow{display:flex;align-items:stretch;gap:0;flex-wrap:wrap;margin-top:16px}
  .rc .ccnode{flex:1;min-width:160px;background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:14px 15px}
  .rc .ccnode.last{border-color:var(--teal);box-shadow:0 0 0 1px var(--teal)}
  .rc .cci{width:24px;height:24px;border-radius:50%;background:var(--teal);color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center}
  .rc .cct{font-size:13.5px;font-weight:700;color:var(--slate);margin-top:8px}
  .rc .ccd{font-size:11.5px;color:var(--muted);line-height:1.45;margin-top:5px}
  .rc .ccd b{color:var(--slate)}
  .rc .ccar{display:flex;align-items:center;color:var(--teal);font-size:20px;font-weight:700;padding:0 7px}
  /* 04 how it works — section labels */
  .rc .howhalf{border-left:4px solid var(--teal);padding:2px 0 2px 14px;margin-bottom:10px}
  .rc .howlab{font-size:16px;font-weight:700;color:var(--slate);letter-spacing:-.2px}
  .rc .howsub{font-size:12px;color:var(--muted);margin-top:3px}
  /* 05 under the hood — record reader + clin gov */
  .rc .uhrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
  .rc .uhcol{background:var(--paper);border:1px solid var(--line);border-top:4px solid var(--cyan);border-radius:12px;padding:16px 18px}
  .rc .uhcol:nth-child(2){border-top-color:#6ba52f}
  .rc .uhh{font-size:15px;font-weight:700;color:var(--slate)}
  .rc .uhb{font-size:12.5px;color:var(--ink);line-height:1.6;margin-top:8px}
  .rc .uhtags{display:flex;flex-wrap:wrap;gap:6px;margin-top:11px}
  .rc .uhtags span{font-size:10px;font-weight:700;color:var(--slate);background:var(--wash);border:1px solid var(--line);border-radius:9px;padding:3px 9px}
  /* 06 compliance — dual model strip */
  .rc .mdlrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:16px}
  .rc .mdl{border-radius:12px;padding:14px 16px;border:1px solid var(--line);border-top:4px solid var(--slate);background:var(--paper)}
  .rc .mdl.det{border-top-color:var(--slate)} .rc .mdl.claude{border-top-color:#B74919} .rc .mdl.gemini{border-top-color:var(--blue)}
  .rc .mdl .mh{font-size:13px;font-weight:700;color:var(--slate)}
  .rc .mdl .mb{font-size:11.5px;color:var(--ink);line-height:1.5;margin-top:7px}

  /* app embed */
  .rc .appwrap{display:flex;gap:22px;flex-wrap:wrap;align-items:flex-start}
  .rc .phone{flex:0 0 auto;width:320px;max-width:100%;border:10px solid #0b1120;border-radius:34px;overflow:hidden;box-shadow:0 18px 44px rgba(5,7,15,.28);background:#0b1120}
  .rc .phone iframe{width:100%;height:620px;border:0;display:block;background:#F5EFE1}
  /* app-login WIREFRAME (replaces the live embed) */
  .rc .wirescreen{height:620px;background:#F4F4F4;display:flex;flex-direction:column;align-items:center;padding:44px 22px 22px;position:relative;overflow:hidden}
  .rc .wiretag{position:absolute;top:11px;left:0;right:0;text-align:center;font-size:8.5px;font-weight:700;letter-spacing:1.4px;color:#9aa0a6;text-transform:uppercase}
  .rc .wirebadge{margin-top:18px;opacity:.92}
  .rc .wiretitle{margin-top:14px}
  .rc .wiresub{font-size:12px;color:#666;margin-top:5px}
  .rc .wirerow{width:100%;margin-top:11px;border:1.5px dashed #ccd0d4;border-radius:10px;padding:12px 14px;font-size:13px;font-weight:500;color:#3F3F3F;display:flex;align-items:center;gap:11px;background:#fff}
  .rc .wirerow .wireic{width:18px;height:18px;border-radius:5px;background:#e4e6e9;flex:0 0 auto}
  .rc .wireor{width:100%;text-align:center;margin:16px 0 8px;position:relative;color:#9aa0a6;font-size:9.5px;text-transform:uppercase;letter-spacing:1.2px;font-weight:600}
  .rc .wireor:before{content:"";position:absolute;top:50%;left:0;right:0;height:1px;background:#e0e2e5}
  .rc .wireor span{background:#F4F4F4;padding:0 10px;position:relative}
  .rc .wirecta{width:100%;background:#2F7D4A;color:#fff;font-size:15px;font-weight:700;border-radius:12px;padding:15px;text-align:center;text-decoration:none;display:block;box-shadow:0 6px 16px rgba(47,125,74,.30);letter-spacing:.3px}
  .rc .wirecta:hover{background:#246d3f}
  .rc .wirenote{font-size:10.5px;color:#666;line-height:1.55;margin-top:auto;text-align:center;border-top:1px dashed #d5d8dc;padding-top:12px}
  .rc .wirenote b{color:#0A0A0A}
  .rc .phone .fallback{height:620px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;text-align:center;padding:24px;color:#c4d3e6;background:linear-gradient(160deg,#0e1526,var(--tile))}
  .rc .phone .fallback .em{font-size:34px} .rc .phone .fallback b{color:#fff;font-size:16px}
  .rc .applead{flex:1;min-width:280px}
  /* clickable screenshot holder */
  .rc .phone.shot{position:relative;cursor:pointer;transition:transform .18s,box-shadow .18s}
  .rc .phone.shot:hover{transform:translateY(-3px);box-shadow:0 24px 54px rgba(5,7,15,.36)}
  .rc .phone.shot:focus-visible{outline:3px solid var(--teal);outline-offset:3px}
  .rc .shotchrome{height:30px;background:#0b1120;color:#8ea1ba;font-size:10.5px;display:flex;align-items:center;gap:5px;padding:0 12px}
  .rc .dotr{width:8px;height:8px;border-radius:50%;background:#33445f;display:inline-block}
  .rc .shotbody{height:590px;background:#F5EFE1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:26px 22px;gap:6px}
  .rc .shotbody .em{font-size:40px}
  .rc .shotbody .wm{font-size:22px;font-weight:700;color:#172554;letter-spacing:.5px}
  .rc .shotbody b{font-family:Georgia,serif;font-size:23px;font-weight:600;color:#172554;line-height:1.15;margin-top:10px;max-width:250px}
  .rc .shotbody .sp{font-size:14px;color:#4b5563;line-height:1.5;margin-top:8px;max-width:250px}
  .rc .shotbody .mockcta{margin-top:16px;background:#172554;color:#F5EFE1;font-size:15px;font-weight:600;padding:13px 26px;border-radius:16px}
  .rc .shotbody .shotcap{position:absolute;bottom:8px;left:0;right:0;font-size:9.5px;color:#9aa6b8;letter-spacing:.5px;text-transform:uppercase}
  .rc .playoverlay{position:absolute;inset:30px 0 0 0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;background:rgba(5,7,15,.0);color:#fff;font-size:15px;font-weight:700;opacity:0;transition:opacity .18s}
  .rc .phone.shot:hover .playoverlay,.rc .phone.shot:focus-visible .playoverlay{opacity:1;background:rgba(5,7,15,.55)}
  .rc .playbtn{width:64px;height:64px;border-radius:50%;background:var(--teal);display:flex;align-items:center;justify-content:center;font-size:26px;box-shadow:0 8px 24px rgba(101,188,123,.5)}
  .rc .btn{display:inline-flex;align-items:center;gap:7px;background:var(--teal);color:#fff;font-size:13px;font-weight:700;padding:11px 18px;border-radius:12px;text-decoration:none;border:none;cursor:pointer}
  .rc .btn:hover{background:var(--teal-d)} .rc .btn.ghost{background:transparent;color:var(--teal-d);border:1px solid var(--teal)}
  .rc .featrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:14px}
  .rc .feat{background:var(--paper);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:10px;padding:13px 15px}
  .rc .feat .h{font-size:13px;font-weight:700;color:var(--slate)} .rc .feat .b{font-size:11.5px;color:var(--muted);margin-top:4px;line-height:1.4}

  /* protocol DB */
  .rc .dbbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px}
  .rc .dbsearch{flex:1;min-width:200px;padding:9px 12px;border:1px solid var(--line);border-radius:10px;font-size:13px;font-family:inherit;background:var(--paper)}
  .rc .meter{flex:1;min-width:200px} .rc .meter .lab{font-size:11px;color:var(--slate);font-weight:700;margin-bottom:5px} .rc .meter .lab b{color:var(--teal-d)}
  .rc .mtr{height:12px;background:var(--field);border-radius:8px;overflow:hidden;position:relative}
  .rc .mtr .fill{height:100%;background:linear-gradient(90deg,#65BC7B,#65BC7B);border-radius:8px}
  .rc .mtr .goal{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--slate)}
  .rc .dbscroll{max-height:340px;overflow-y:auto;border:1px solid var(--line);border-radius:12px}
  .rc table.db{border-collapse:collapse;width:100%;font-size:12.5px}
  .rc table.db th{position:sticky;top:0;background:var(--slate);color:#fff;font-weight:700;font-size:11px;text-align:left;padding:8px 12px;z-index:1}
  .rc table.db td{border-top:1px solid var(--line);padding:8px 12px;vertical-align:top}
  .rc table.db tr{cursor:pointer} .rc table.db tr:hover{background:var(--wash)}
  .rc table.db tr.open{background:var(--wash2)}
  .rc .lc{font-size:9.5px;font-weight:700;letter-spacing:.4px;padding:1px 7px;border-radius:9px;white-space:nowrap}
  .rc .lc.live{background:var(--wash2);color:var(--teal-d);border:1px solid #b7e3d3}
  .rc .lc.badge{background:#eef4fb;color:var(--blue);border:1px solid #cfe0f2}
  .rc .lc.draft{background:#f3f4f6;color:var(--muted);border:1px solid #e5e7eb}
  .rc .anatomy{background:var(--wash);border-top:1px solid var(--line)}
  .rc .anatomy td{padding:14px 16px !important}
  .rc .astep{display:flex;gap:9px;align-items:flex-start;padding:5px 0;font-size:12px;color:var(--ink);border-bottom:1px dashed #e5e9f0}
  .rc .astep:last-child{border-bottom:none} .rc .astep .n{flex:0 0 22px;height:22px;border-radius:6px;background:var(--teal);color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center}
  .rc .astep .t b{color:var(--slate)}

  /* safety equation */
  .rc .eqwrap{display:flex;gap:22px;flex-wrap:wrap;align-items:center}
  .rc .eq{flex:1;min-width:280px;background:#0b1120;color:#e8eef6;border-radius:12px;padding:22px 24px;font-family:'Times New Roman',Georgia,serif}
  .rc .eq .big{font-size:26px;font-weight:600;letter-spacing:.3px} .rc .eq .big .teal{color:#8FD6A2} .rc .eq .cond{font-size:13px;color:#9fb3c8;margin-top:12px;font-family:Arial,sans-serif;line-height:1.6}
  .rc .eq .cond code{background:#141d31;color:#ffd88a;padding:1px 6px;border-radius:5px;font-size:12px}
  .rc .gates{flex:1;min-width:280px}
  .rc .gaterow{display:flex;gap:6px;flex-wrap:wrap}
  .rc .glight{flex:1;min-width:64px;background:var(--wash);border:1px solid var(--line);border-radius:9px;padding:9px 6px;text-align:center}
  .rc .glight .g{width:12px;height:12px;border-radius:50%;background:var(--accent);margin:0 auto 5px;box-shadow:0 0 0 3px var(--accent)22}
  .rc .glight.fail .g{background:#e5484d;box-shadow:0 0 0 3px #e5484d22}
  .rc .glight .id{font-size:10px;font-weight:700;color:var(--slate)} .rc .glight .nm{font-size:8.5px;color:var(--muted);line-height:1.15;margin-top:2px}

  /* compliance domains + law */
  .rc .dgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
  .rc .dcard{background:var(--paper);border:1px solid var(--line);border-left:4px solid var(--slate);border-radius:10px;padding:12px 14px}
  .rc .dcard.att{border-left-color:#B74919} .rc .dcard.mds{border-left-color:var(--cyan)} .rc .dcard.cmo{border-left-color:var(--lime)}
  .rc .dcard .dh{display:flex;align-items:center;justify-content:space-between;gap:8px}
  .rc .dcard .did{font-size:11px;font-weight:700;color:var(--slate)} .rc .dcard .dn{font-size:13px;font-weight:700;color:var(--ink);margin-top:2px}
  .rc .dcard .own{font-size:9px;font-weight:700;letter-spacing:.4px;padding:1px 6px;border-radius:8px;color:#fff}
  .rc .own.att{background:#B74919} .rc .own.mds{background:var(--cyan)} .rc .own.cmo{background:#6ba52f}
  .rc .dcard .blk{font-size:10.5px;color:#e5484d;font-weight:700;margin-top:6px} .rc .dcard .blk.no{color:var(--muted)}
  .rc .lawgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
  .rc .lawcol h4{font-size:11.5px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;color:var(--teal-d);margin-bottom:7px}
  .rc .lawcol .chip{display:inline-block;background:var(--wash);border:1px solid var(--line);border-radius:8px;padding:5px 9px;font-size:11.5px;color:var(--ink);margin:0 5px 6px 0;font-weight:600}

  /* timeline */
  .rc .timeline{display:flex;gap:0;overflow-x:auto;padding-bottom:6px}
  .rc .mnode{flex:1;min-width:150px;position:relative;padding:22px 12px 6px}
  .rc .mnode:before{content:"";position:absolute;top:30px;left:0;right:0;height:3px;background:var(--line)}
  .rc .mnode .dotm{position:absolute;top:24px;left:50%;transform:translateX(-50%);width:15px;height:15px;border-radius:50%;background:#fff;border:3px solid var(--teal);z-index:2}
  .rc .mnode.done .dotm{background:var(--teal)} .rc .mnode.target .dotm{border-color:var(--amber);background:var(--amber)}
  .rc .mnode .mw{font-size:10px;font-weight:700;color:var(--muted);text-align:center}
  .rc .mnode .ml{font-size:12px;font-weight:700;color:var(--slate);text-align:center;margin-top:6px;line-height:1.3}
  .rc .mnode.target .ml{color:var(--rust)}

  /* chain diagram */
  .rc .chain{display:flex;gap:0;flex-wrap:wrap}
  .rc .cnode{flex:1;min-width:150px;text-align:center;position:relative;padding:0 6px}
  .rc .cnode .cbadge{width:52px;height:52px;border-radius:14px;background:var(--paper);border:2px solid var(--teal);color:var(--teal-d);display:flex;align-items:center;justify-content:center;font-size:22px;margin:0 auto}
  .rc .cnode .cname{font-size:13px;font-weight:700;color:var(--slate);margin-top:8px}
  .rc .cnode .ctile{background:var(--wash);border:1px solid var(--line);border-radius:10px;padding:10px;margin-top:8px}
  .rc .cnode .ctile .cn{font-size:20px;font-weight:700;color:var(--teal-d)} .rc .cnode .ctile .cl{font-size:10px;color:var(--muted);margin-top:3px;line-height:1.3}
  .rc .cnode .carw{position:absolute;top:20px;right:-8px;color:var(--teal);font-weight:700;font-size:18px;z-index:2}

  /* roadmap */
  .rc .rmgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
  .rc .rmcard{background:var(--paper);border:1px dashed #cfd8e3;border-radius:12px;padding:16px}
  .rc .rmcard .rt{font-size:14px;font-weight:700;color:var(--slate)} .rc .rmcard .rd{font-size:12px;color:var(--muted);margin-top:6px;line-height:1.45}
  .rc .rmcard .rw{display:inline-block;margin-top:9px;background:#eef4fb;color:var(--blue);border:1px solid #cfe0f2;font-size:9.5px;font-weight:700;letter-spacing:.4px;padding:1px 7px;border-radius:9px}

  /* email preview */
  .rc .emailprev{margin-top:14px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff;max-width:420px}
  .rc .emailprev .ehead{display:flex;justify-content:space-between;align-items:center;background:var(--slate);color:#fff;padding:7px 12px;font-size:11px;font-weight:700}
  .rc .emailprev .etag{background:var(--amber);color:#fff;font-size:9px;font-weight:700;letter-spacing:.4px;padding:1px 7px;border-radius:9px}
  .rc .emailprev .esubj{padding:8px 14px;font-size:12px;color:var(--slate);border-bottom:1px solid var(--line);background:var(--wash)}
  .rc .emailprev .ebody{padding:16px 16px 14px;text-align:center}
  .rc .emailprev .ebrand{font-size:16px;font-weight:700;color:var(--teal-d)} .rc .emailprev .ebrand span{font-size:10px;font-weight:600;color:var(--muted)}
  .rc .emailprev .ehl{font-size:16px;font-weight:700;color:var(--ink);margin-top:12px;line-height:1.25}
  .rc .emailprev .ep{font-size:12px;color:#33424f;margin-top:8px;line-height:1.5}
  .rc .emailprev .ekpi{font-size:12px;font-weight:700;color:var(--teal-d);background:var(--wash2);border-radius:8px;padding:8px;margin-top:12px}
  .rc .emailprev .ecta{display:inline-block;margin-top:14px;background:var(--teal);color:#fff;font-size:12px;font-weight:700;letter-spacing:.3px;padding:11px 18px;border-radius:8px}
  .rc .emailprev .eisi{font-size:9.5px;color:var(--muted);margin-top:12px;line-height:1.4;text-align:left}
  .rc .emailprev .efoot{font-size:9.5px;color:var(--muted);background:var(--wash);border-top:1px solid var(--line);padding:7px 12px}
  /* two-email planned row + accordion */
  .rc .emailrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
  .rc .eacc{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff;align-self:start}
  .rc .eacchd{display:flex;align-items:center;gap:10px;padding:10px 12px;cursor:pointer;background:var(--wash)}
  .rc .eacchd:hover{background:var(--wash2)}
  .rc .ethumb{width:56px;height:36px;object-fit:cover;border-radius:6px;border:1px solid var(--line);flex:0 0 auto;background:#eef1f5}
  .rc .eaccmeta{flex:1;min-width:0} .rc .eaccn{font-size:12.5px;font-weight:700;color:var(--slate);line-height:1.2} .rc .eaccsub{font-size:10.5px;color:var(--muted);margin-top:2px}
  .rc .estatus{font-size:9px;font-weight:700;letter-spacing:.3px;padding:2px 7px;border-radius:9px;white-space:nowrap}
  .rc .estatus.ok{background:var(--wash2);color:var(--teal-d);border:1px solid #b7e3d3} .rc .estatus.rev{background:#fff7ec;color:var(--rust);border:1px solid #f3d9b0}
  .rc .echev{color:var(--muted);font-size:12px;transition:transform .18s;flex:0 0 auto}
  .rc .eacchd.open .echev,.rc .evrow.open .echev{transform:rotate(180deg)}
  .rc .edrop{padding:0 12px 12px}
  .rc .evrow.evclick{cursor:pointer;border-radius:8px} .rc .evrow.evclick:hover{background:var(--wash)}
  .rc .sched .edrop{padding:0 4px 8px}
  /* advocate schedule meta */
  .rc .advmeta{display:flex;flex-direction:column;gap:1px;min-width:0}
  .rc .advsch{font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.1px}
  .rc .advchip.on .advsch{color:#3a9e82}
  /* inline expandable schedule of events (sched2) */
  .rc .sched2{display:flex;flex-direction:column;gap:8px}
  .rc .evitem{border:1px solid var(--line);border-radius:11px;overflow:hidden;background:var(--paper);transition:border-color .15s,box-shadow .15s}
  .rc .evitem:hover{border-color:#cdd8e4;box-shadow:0 3px 12px rgba(31,42,55,.06)}
  .rc .evrow2{display:grid;grid-template-columns:50px 46px 1fr auto 16px;gap:12px;align-items:center;padding:10px 12px;cursor:pointer}
  .rc .evrow2:hover{background:var(--wash)}
  .rc .evrow2.open{background:var(--wash2)}
  .rc .evrow2.open .echev{transform:rotate(180deg)}
  .rc .evdate2{font-size:11px;font-weight:700;color:var(--slate);line-height:1.15;text-align:center;letter-spacing:.2px}
  .rc .evthumb{width:46px;height:46px;object-fit:cover;border-radius:8px;border:1px solid var(--line);display:block}
  .rc .evicon{width:46px;height:46px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:18px;color:#fff;background:var(--teal)}
  .rc .evicon.t-webinar{background:var(--blue)} .rc .evicon.t-email{background:var(--teal)} .rc .evicon.t-mailer{background:var(--amber)}
  .rc .evinfo{min-width:0}
  .rc .evtitle{font-size:13.5px;font-weight:700;color:var(--ink);line-height:1.25}
  .rc .evsub{font-size:11px;color:var(--muted);margin-top:2px;font-weight:600}
  .rc .evbody2{border-top:1px solid var(--line);background:var(--wash)}
  .rc .evbody2>.emailfull{margin:14px auto}
  .rc .evexpand{padding:14px}
  .rc .evbig{width:100%;max-width:540px;border-radius:10px;border:1px solid var(--line);display:block;margin-bottom:10px}
  .rc .evdesc{font-size:12.5px;color:var(--ink);line-height:1.5}
  .rc .estatus.done{background:var(--wash2);color:var(--teal-d);border:1px solid #b7e3d3}
  .rc .estatus.code{background:#fff7ec;color:#b26a00;border:1px solid #f3d9b0}
  .rc .estatus.req{background:#eaf4fb;color:var(--blue);border:1px solid #bcdcf0}
  .rc .estatus.plan{background:#f1f3f7;color:var(--slate);border:1px solid #dde3ec}
  @media (max-width:600px){.rc .evrow2{grid-template-columns:44px 40px 1fr auto;gap:9px}.rc .evrow2 .echev{display:none}.rc .estatus{white-space:normal;text-align:center}.rc .evthumb,.rc .evicon{width:40px;height:40px}}
  /* schedule timeline state + legend (additive upgrade) */
  .rc .evitem.ev-past{opacity:.6}
  .rc .evitem.ev-next{border-color:var(--teal);box-shadow:0 0 0 1px var(--teal),0 4px 14px rgba(101,188,123,.14)}
  .rc .evitem.ev-next .evrow2{background:linear-gradient(#eafff6,#fff)}
  .rc .evstate{display:inline-block;font-size:9px;font-weight:700;letter-spacing:.3px;padding:1px 6px;border-radius:8px;margin-left:7px;vertical-align:middle}
  .rc .evstate.next{background:var(--teal);color:#fff}
  .rc .evstate.done{background:var(--wash2);color:var(--teal-d)}
  .rc .evleg{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-top:12px;font-size:10.5px;color:var(--muted);font-weight:600}
  .rc .evleg i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
  .rc .evleg .lg-email{background:var(--teal)} .rc .evleg .lg-webinar{background:var(--blue)} .rc .evleg .lg-mailer{background:var(--amber)}
  .rc .evleg b{color:var(--slate)} .rc .evleg-sep{color:var(--line)}
  /* HCP / NPI log table */
  .rc table.npilog td,.rc table.npilog th{white-space:nowrap}
  .rc table.npilog th{font-size:10px;letter-spacing:.2px}
  .rc .npicell{font-variant-numeric:tabular-nums;font-weight:700;color:var(--slate)}
  .rc .pend{color:var(--muted);font-style:italic;font-weight:600;font-size:11px}
  .rc .dpill{display:inline-block;font-size:9.5px;font-weight:700;padding:1px 8px;border-radius:9px}
  .rc .dpill.yes{background:var(--wash2);color:var(--teal-d);border:1px solid #b7e3d3}
  .rc .dpill.no{background:#f1f3f7;color:var(--slate);border:1px solid #dde3ec}
  /* Accountability & System Hardening list */
  .rc .hardgrid{display:flex;flex-direction:column;gap:2px}
  .rc .harditem{display:flex;gap:12px;align-items:flex-start;padding:11px 2px;border-bottom:1px solid var(--line)}
  .rc .harditem:last-child{border-bottom:none}
  .rc .hardico{flex:0 0 auto;width:34px;height:34px;border-radius:9px;display:flex;align-items:center;justify-content:center}
  .rc .hardico svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
  .rc .hardico.c-db,.rc .hardico.c-verify,.rc .hardico.c-clock{background:#eafff6;color:var(--teal-d)}
  .rc .hardico.c-crm,.rc .hardico.c-audit,.rc .hardico.c-chat{background:#eaf4fb;color:var(--blue)}
  .rc .hardico.c-contact,.rc .hardico.c-dash{background:#e9f7fb;color:#158aa5}
  .rc .hardico.c-npi{background:#fff5e8;color:#b26a00}
  .rc .hardico.c-zero{background:#f1f3f7;color:var(--slate)}
  .rc .hardtx{min-width:0;padding-top:1px}
  .rc .hardt{font-size:12.5px;font-weight:700;color:var(--slate);line-height:1.25;letter-spacing:.1px}
  .rc .hardd{font-size:11.5px;color:var(--muted);line-height:1.42;margin-top:2px}
  /* the email creative itself */
  .rc .emailfull{border:1px solid var(--line);border-radius:12px;overflow:hidden;max-width:460px;margin:6px auto 0;box-shadow:0 6px 20px rgba(31,42,55,.08);background:#fff}
  .rc .efbar{display:flex;justify-content:space-between;gap:8px;background:#0b1120;color:#8ea1ba;font-size:9.5px;padding:6px 12px}
  .rc .efhero{width:100%;display:block;border-bottom:1px solid var(--line)}
  .rc .efbody{padding:16px 18px;text-align:center}
  .rc .efhl{font-size:19px;font-weight:700;color:var(--teal-d);line-height:1.2}
  .rc .efp{font-size:13px;color:#33424f;margin-top:10px;line-height:1.5}
  .rc .efkpi{font-size:13px;font-weight:700;color:var(--slate);background:var(--wash2);border-radius:8px;padding:10px;margin-top:14px}
  .rc .efcta{display:inline-block;margin-top:16px;background:var(--teal);color:#fff;font-size:12.5px;font-weight:700;letter-spacing:.3px;padding:12px 22px;border-radius:8px}
  .rc .efisi{font-size:10px;color:#5b6b82;margin-top:16px;line-height:1.5;text-align:left}
  .rc .effoot{font-size:9.5px;color:var(--muted);background:var(--wash);border-top:1px solid var(--line);padding:8px 12px;text-align:center}

  @media (max-width:900px){.rc .phone{width:100%;max-width:340px;margin:0 auto} .rc .flow{flex-direction:column} .rc .farrow{transform:rotate(90deg);padding:2px 0}}

  /* ===== PROFESSIONAL DESIGN SYSTEM (Libre Franklin · one accent · cool neutrals · soft elevation) ===== */
  .rc{line-height:1.5}
  .rc b,.rc strong{font-weight:600}
  /* display numbers -> weight 600 */
  .rc .bignum{font-size:60px;font-weight:600;letter-spacing:-1.5px;color:var(--accent-ink)}
  .rc .kpi .n,.rc .scard .n,.rc .stat .n,.rc .scstat .n,.rc .thstat .n,.rc .decln,.rc .donut .ctr .p,.rc .hcpband .big{font-weight:600}
  .rc .kpi .n{font-size:29px;color:var(--accent-ink);letter-spacing:-.4px}
  .rc .kpi .l{font-size:12px;font-weight:600;color:var(--ink-2);margin-top:10px}
  .rc .kpi .s{font-size:11px;color:var(--muted)}
  /* one-accent number cards, single soft elevation */
  .rc .kpi{border-top:3px solid var(--accent);border-radius:var(--r-md);box-shadow:var(--sh-1);padding:18px}
  .rc .scard{border-top:3px solid var(--accent);border-radius:var(--r-md)}
  .rc .scard.today{background:var(--accent-wash)} .rc .scard.today .n{color:var(--accent-ink)}
  .rc .stat{border-top:3px solid var(--accent);border-radius:var(--r-md)}
  .rc .scstat{border-top-color:var(--accent)} .rc .scstat .n{color:var(--accent-ink)}
  /* section headers: hairline + accent tick */
  .rc .ph{border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:16px}
  .rc .ph h2{font-size:15px;font-weight:700;color:var(--heading);display:flex;align-items:center;letter-spacing:.1px}
  .rc .ph h2::before{content:"";display:inline-block;width:3px;height:14px;background:var(--accent);border-radius:2px;margin-right:9px}
  .rc .ph .sub{font-size:11px;font-weight:500;color:var(--muted)}
  /* panels + grid air */
  .rc .panel{border-radius:var(--r-lg);box-shadow:var(--sh-1);padding:20px 22px}
  .rc .grid{gap:16px}
  /* App Launch section rhythm + heads */
  .rc .psec{margin-top:52px}
  .rc .psec>.ph2 h2{font-size:22px;font-weight:700;letter-spacing:-.2px;color:var(--heading)}
  .rc .psec>.ph2 .k{font-size:11px;font-weight:700;letter-spacing:1.2px;color:var(--accent-ink)}
  .rc .psub{font-size:13px;color:var(--muted);line-height:1.55}
  /* mode switch + month tabs */
  .rc .modeswitch{border-radius:var(--r-md);box-shadow:var(--sh-1)}
  .rc .mbtn{font-size:13px;font-weight:600;color:var(--muted)}
  .rc .mbtn.on,.rc .mbtn.on:hover{background:var(--accent);color:#fff}
  .rc .mtab{border-radius:var(--r-md);box-shadow:var(--sh-1)}
  .rc .mtab.on{border-color:var(--accent);box-shadow:inset 0 0 0 1.5px var(--accent),var(--sh-2)}
  .rc .mtab .mo{color:var(--heading);font-weight:700}
  .rc .mtab .badge{background:var(--accent-wash);border-color:var(--accent-line);color:var(--accent-ink)}
  /* hero: softer tile, calmer type */
  .rc .hero{background:var(--tile);border-radius:var(--r-hero);padding:32px 36px 28px;box-shadow:var(--sh-3)}
  .rc .hero .veil{background:linear-gradient(105deg,rgba(14,27,42,.96) 40%,rgba(19,37,56,.82) 100%)}
  .rc .hero .eyebrow{font-size:11px;letter-spacing:1.4px;font-weight:600;color:#8FCDB9}
  .rc .hero h1{font-size:28px;font-weight:600;letter-spacing:-.2px;color:#F5F8FB;margin-top:12px}
  .rc .hero .accent{width:48px;height:3px;margin-top:16px}
  .rc .hero .period{color:#AEBECF} .rc .hero .period b{color:#fff;font-weight:600}
  /* tables: de-grid the "spreadsheet" look */
  .rc table.rep th,.rc table.rep td{border:none;border-bottom:1px solid var(--line-2);padding:9px 12px}
  .rc table.rep th{background:transparent;color:var(--heading);font-weight:700;font-size:11px;letter-spacing:.4px;text-transform:uppercase;border-bottom:1.5px solid var(--heading)}
  .rc table.rep td.lbl,.rc table.rep th.lbl{background:transparent;color:var(--heading);font-weight:600}
  .rc table.rep tr.tot td{background:var(--wash2);color:var(--accent-ink);font-weight:700;border-top:1.5px solid var(--line)}
  .rc table.rep .sel{background:var(--accent-wash)} .rc table.rep th.sel{background:var(--accent);color:#fff}
  .rc table.db th{background:var(--heading);font-size:11px;font-weight:600;letter-spacing:.3px;text-transform:uppercase;padding:9px 14px}
  .rc table.db td{border-top:1px solid var(--line-2);padding:10px 14px} .rc table.db tr:hover{background:var(--wash)} .rc table.db tr.open{background:var(--accent-wash)}
  .rc table.npilog th{font-size:10.5px;letter-spacing:.3px;text-transform:uppercase;color:var(--heading)}
  /* buttons */
  .rc .btn{background:var(--accent);border-radius:var(--r-md);font-size:13px;font-weight:600;box-shadow:var(--sh-1)}
  .rc .btn:hover{background:var(--accent-ink)} .rc .btn.ghost{border:1px solid var(--accent-line);color:var(--accent-ink);box-shadow:none}
  /* charts: flat brand fills, hairline baseline */
  .rc .pfill,.rc .hfill,.rc .mtr .fill{background:var(--accent)} .rc .qfill{background:var(--blue)}
  .rc .barI,.rc .dbar .si,.rc .bi{background:var(--accent)}
  .rc .barP,.rc .dbar .sp,.rc .bp{background:#3FA588}
  .rc .barO,.rc .dbar .so,.rc .bo{background:var(--blue)}
  .rc .grp.cur{background:var(--accent-wash)} .rc .bars,.rc .daychart{border-bottom:1px solid var(--line)}
  .rc .bar{border-radius:4px 4px 0 0} .rc .dbar{border-radius:4px 4px 0 0}
  .rc .leg{font-size:11px;font-weight:500;color:var(--ink)}
  /* dark report tiles unified to --tile */
  .rc .thstat{background:var(--tile);border-radius:var(--r-lg)} .rc .thstat .n{color:var(--tile-accent)} .rc .thstat .l{color:var(--tile-ink)}
  .rc .hcpband{background:var(--tile);border-radius:var(--r-lg)} .rc .hcpband .big{color:var(--tile-accent)} .rc .hcpband .t{color:var(--tile-ink)}
  .rc .declcard,.rc .ccstage,.rc .eq{background:var(--tile)}
  /* flatten saturated glows + colour rings */
  .rc .playbtn{box-shadow:var(--sh-2)} .rc .ccbtn{box-shadow:var(--sh-2)}
  .rc .advchip.on{box-shadow:0 0 0 1px var(--accent-line),var(--sh-1)}
  /* dashed placeholders -> solid hairline */
  .rc .accum,.rc .rvdom,.rc .astep,.rc .awycdt,.rc .rmcard{border-style:solid}
  .rc .accum{border-color:var(--line)}
  /* calm the uppercase letter-spacing */
  .rc .thsub,.rc .fbeb,.rc .dch,.rc .decls,.rc .tsh,.rc .lawcol h4,.rc .cceb,.rc .teb,.rc .howlab,.rc .uhh{letter-spacing:.6px}
  .rc .note{font-size:11px}

  /* QA fixes: header baseline, timeline target, orphan accents, table spine */
  .rc .ph{align-items:center}
  .rc .mnode.target .dotm{border-color:var(--accent);background:var(--accent)}
  .rc .mnode.target .ml{color:var(--accent-ink)}
  .rc .quote.b2,.rc .quote.b3{border-left-color:var(--accent)}
  .rc .qitem{border-left-color:var(--accent)}
  .rc table.rep td.lbl,.rc table.rep th.lbl{border-right:1px solid var(--line-2)}

  /* ===== AVADA PORTFOLIO THEME (Inter Tight · warm off-white · flat cards · soft green) ===== */
  .rc{line-height:1.55}
  /* flat white cards on off-white: 10px, hairline, no shadow */
  .rc .panel{box-shadow:none;border:1px solid var(--line);border-radius:10px}
  .rc .kpi{box-shadow:none;border:1px solid var(--line);border-top:3px solid var(--accent);border-radius:10px}
  .rc .scard,.rc .stat,.rc .scstat{box-shadow:none;border:1px solid var(--line);border-top:1px solid var(--line);border-radius:10px;background:var(--paper)}
  .rc .scard.today{background:var(--accent-wash)}
  .rc .modeswitch,.rc .mtab{box-shadow:none;border-radius:10px}
  .rc .etile,.rc .accum,.rc .feat,.rc .uhcol,.rc .rulecard,.rc .tri,.rc .mdl,.rc .rmcard,.rc .advchip{box-shadow:none;border-radius:10px}
  /* editorial near-black numbers + refined heading weights */
  .rc .bignum{color:var(--heading);font-weight:600;letter-spacing:-1px}
  .rc .kpi .n,.rc .scard .n,.rc .stat .n,.rc .scstat .n,.rc .donut .ctr .p,.rc .decln{color:var(--heading);font-weight:600}
  .rc .hero h1{font-weight:500;letter-spacing:.2px}
  .rc .psec>.ph2 h2{font-weight:600;letter-spacing:.2px;color:var(--heading)}
  .rc .ph h2{color:var(--heading);font-weight:600}
  /* Avada uppercase micro-labels: near-black, +.6px */
  .rc .psec>.ph2 .k{color:var(--heading);font-weight:600;letter-spacing:.6px}
  .rc .hero .eyebrow{color:var(--tile-accent);letter-spacing:.8px;font-weight:600}
  /* buttons: readable green primary + subtle ghost */
  .rc .btn{background:var(--accent-ink);border-radius:10px}
  .rc .btn:hover{background:#246d3f}
  .rc .btn.ghost{background:transparent;border:1px solid var(--line);color:var(--heading)}
  /* mode toggle + month tab active states (readable green) */
  .rc .mbtn.on,.rc .mbtn.on:hover{background:var(--accent-ink);color:#fff}
  .rc .mtab.on{border-color:var(--accent);box-shadow:inset 0 0 0 1.5px var(--accent)}
  /* charts: Avada palette — green / slate / medium-gray */
  .rc .barI,.rc .dbar .si,.rc .bi,.rc .pfill,.rc .hfill,.rc .mtr .fill{background:var(--accent)}
  .rc .barP,.rc .dbar .sp,.rc .bp{background:var(--blue)}
  .rc .barO,.rc .dbar .so,.rc .bo{background:#8A96A0}
  /* monochromatic green bars — Initial (light) · Pre-HCP (mid) · Post-HCP (dark) */
  .rc .barI,.rc .dbar .si,.rc .bi{background:#9FD4B4}
  .rc .barP,.rc .dbar .sp,.rc .bp{background:#65BC7B}
  .rc .barO,.rc .dbar .so,.rc .bo{background:#2F7D4A}
  .rc .qfill{background:#2F7D4A}
  /* dark tiles -> Avada slate */
  .rc .hero,.rc .thstat,.rc .hcpband,.rc .declcard,.rc .ccstage,.rc .eq{background:var(--tile)}
  .rc .thstat .n{color:var(--tile-accent)}
  .rc .dbscroll{border-radius:10px}

  /* ===== AVADA QA FIXES (legibility + fidelity) ===== */
  .rc .decln{color:#F0A58C}                                   /* decline stat on DARK card */
  .rc .scard.today .n,.rc .thstat.t2 .n{color:var(--heading)} /* two-class number selectors -> near-black */
  .rc .own.mds{background:var(--blue)} .rc .own.cmo{background:var(--accent-ink)} /* owner pills legible on white */
  .rc .fbcopy h3{font-weight:600;color:var(--heading)}        /* tour subhead -> Avada weight/near-black */
  .rc .betachip,.rc .rmchip{background:rgba(10,10,10,.06);color:var(--heading);border:none} /* calm subtle-tint chips */
  .rc .evreq{color:var(--heading)} .rc .estatus.rev{color:#8a3b12}
  .rc .hero{box-shadow:none}                                  /* Avada flat dark sections */
  .rc .ccar,.rc .cnode .carw{color:var(--accent-ink)}         /* readable connector arrows */
  .rc .kpi{border-top-width:2px}                              /* restrained KPI edge */
</style>

<canvas id="confettiC" aria-hidden="true"></canvas>
<div class="rc">
  <header class="hero" id="hero"></header>
  <div class="modeswitch" id="modeswitch"></div>
  <div id="view"></div>
  <div class="foot">
    <div><b>Research Catalyst</b> · ONAPGO® Patient Education Program · <b>Confidential</b></div>
    <div>Live figures stream from the Patient Advocacy Center CRM · crm.parkinsons.community</div>
  </div>
</div>

<script>
(function(){
  var MON=['','January','February','March','April','May','June','July','August','September','October','November','December'];
  var LOGO='/onapgo/asset/onapgo_logo.png', NEURON='/onapgo/asset/neuron_bg.jpg';

  var METRICS_FALLBACK={"months":[{"ym":"2026-06","label":"June","year":"2026","live":false},{"ym":"2026-07","label":"July","year":"2026","live":true}],
    "stages":{"initial":{"2026-06":108,"2026-07":21},"pre_hcp":{"2026-06":211,"2026-07":5},"post_hcp":{"2026-06":183,"2026-07":19}},"as_of":"July 11, 2026 · 4:57 PM","live_month":"July"};
  var LIVE_FALLBACK={"month":"July 2026","ym":"2026-07","as_of":"July 11, 2026 · 5:10 PM","stages":{"initial":21,"pre_hcp":5,"post_hcp":19},"total":45,
    "today":{"initial":3,"pre_hcp":1,"post_hcp":3,"total":7},"target":500,"projected":127,"day_of_month":11,"days_in_month":31,
    "days":[{"date":"2026-07-01","initial":2,"pre_hcp":0,"post_hcp":1,"total":3},{"date":"2026-07-02","initial":3,"pre_hcp":1,"post_hcp":2,"total":6},{"date":"2026-07-03","initial":1,"pre_hcp":0,"post_hcp":2,"total":3},{"date":"2026-07-04","initial":0,"pre_hcp":0,"post_hcp":1,"total":1},{"date":"2026-07-07","initial":3,"pre_hcp":1,"post_hcp":2,"total":6},{"date":"2026-07-08","initial":2,"pre_hcp":1,"post_hcp":3,"total":6},{"date":"2026-07-09","initial":3,"pre_hcp":0,"post_hcp":2,"total":5},{"date":"2026-07-10","initial":4,"pre_hcp":1,"post_hcp":3,"total":8},{"date":"2026-07-11","initial":3,"pre_hcp":1,"post_hcp":3,"total":7}]};

  var QUAL_FALLBACK={"ym":"2026-07","discussed":{"yes":3,"no":16},"barriers":[["Other concerns discussed instead",6],["Doctor didn't raise it",4],["Not interested in ONAPGO",4],["Didn't express OFF time",3],["Doctor running behind",1],["Discussed a different treatment",1]],"treatment":[["Prescribed another treatment",7],["No changes (revisit next appt)",6],["Changed dose / timing (C/L)",5],["Changed dose / timing (not C/L)",2],["Suggested PT / OT / exercise",1]],"questions":[["Have any other patients reported allergic reactions to Onapgo?",1],["Is Onapgo the same as the other pump?",1],["Is Onapgo the same as Vyalev?",1],["Is the pump heavy?",1],["Is this similar as Crexont?",1],["Is this the same as Vyalev?",1]],"questions_total":6,"hcp_appts":237,"appts_scheduled":16,"posthcp":[{"q":"Are you still experiencing OFF time?","a":[["OFF disruptive & bothersome",11],["OFF present, not bothersome",7],["No longer experiencing OFF",1]]},{"q":"Requested ONAPGO® patient information?","a":[["No",10],["Yes",9]]},{"q":"Preferred delivery method","a":[["Email",9]]},{"q":"Open to resources / earlier appointment?","a":[["No",11]]}]};
  var QUAL={};
  var ADV_FALLBACK={"on_now":2,"total":6,"advocates":[{"name":"Jen","clocked_in":true,"since":"2026-07-11T14:04:00+00:00"},{"name":"Giselle","clocked_in":true,"since":"2026-07-11T15:10:00+00:00"},{"name":"Claire","clocked_in":false,"since":null},{"name":"Duane","clocked_in":false,"since":"2026-07-10T21:01:00+00:00"},{"name":"Marvin","clocked_in":false,"since":null},{"name":"Support","clocked_in":false,"since":null}]};
  var ADV=null;
  // HCP appointment / NPI log — one row per post-HCP "discussed ONAPGO" response (the data behind
  // the Discussed-ONAPGO figure). NPI is blank until CRM capture is enabled; doctor + dates are live.
  var HCPLOG_FALLBACK={"ym":"2026-07","total":6,"yes":1,"no":5,"npi_captured":0,"npi_column":false,"rows":[
    {"npi":"","doctor":"Dr. A. Bhattacharya","appt_month":"2026-06","appt_date":"2026-06-22","logged":"2026-07-02","discussed":"No"},
    {"npi":"","doctor":"Dr. L. Romero","appt_month":"2026-06","appt_date":"2026-06-27","logged":"2026-07-03","discussed":"No"},
    {"npi":"","doctor":"Dr. S. Okafor","appt_month":"2026-06","appt_date":"2026-06-30","logged":"2026-07-06","discussed":"Yes"},
    {"npi":"","doctor":"Dr. M. Feldman","appt_month":"2026-07","appt_date":"2026-07-06","logged":"2026-07-09","discussed":"No"},
    {"npi":"","doctor":"Dr. J. Park","appt_month":"2026-07","appt_date":"2026-07-08","logged":"2026-07-10","discussed":"No"},
    {"npi":"","doctor":"","appt_month":"2026-07","appt_date":"2026-07-09","logged":"2026-07-11","discussed":"No"}
  ]};
  var HCPLOG={};

  // Program event calendar (email blasts, webinars, mailers). Status computed vs the CRM's current date.
  var EVENTS=[
    {d:'2026-06-19',t:'webinar',title:'Educational Webinar — Dr. Sagari Bette',status:'Delivered',sc:'done',desc:'“More GOOD ON Time Each Day.” Movement-disorder specialist presenter · 266 registered.'},
    {d:'2026-06-26',t:'email',title:'Branded ONAPGO® email',qty:'17,346 sent',status:'Delivered',sc:'done',desc:'June branded educational send — 906 opens (5.2%), 23 clicks.'},
    {d:'2026-07-31',t:'email',title:'More Predictable Days',code:'ONA.2026-0064',qty:'7,500',status:'Coding',sc:'code',img:'/onapgo/asset/em1_hero.jpg',full:0,desc:'Branded DTC email introducing ONAPGO — a wearable infusion device for more predictable days. CTA: “Learn How ONAPGO Can Help.” Currently in coding (not yet MLR-approved).'},
    {d:'2026-09-18',t:'webinar',title:'Q3 Educational Webinar',status:'Scheduled · 1 PM ET',sc:'plan',link:MDS_URL,desc:'Movement-disorder specialist webinar — Friday, September 18, 2026 at 1:00 PM ET.'},
    {d:'2026-08-15',t:'mailer',title:'Patient Education Mailer',qty:'2,000',status:'Materials Requested',sc:'req',desc:'Printed ONAPGO patient education packet mailed to eligible community members.'},
    {d:'2026-09-11',t:'email',title:'Branded ONAPGO® email',qty:'7,500',status:'Planned',sc:'plan',desc:'September branded educational send.'},
    {d:'2026-10-01',t:'webinar',title:'Educational Webinar',status:'Planned',sc:'plan',approx:true,desc:'Early-October movement-disorder specialist webinar.'},
    {d:'2026-10-30',t:'email',title:'Branded ONAPGO® email',qty:'7,500',status:'Planned',sc:'plan',desc:'October branded educational send.'},
    {d:'2026-11-13',t:'email',title:'Branded ONAPGO® email',qty:'7,500',status:'Planned',sc:'plan',desc:'November branded educational send.'},
    {d:'2026-12-11',t:'email',title:'Branded ONAPGO® email',qty:'7,500',status:'Planned',sc:'plan',desc:'December branded educational send.'}
  ];

  var SHOW=['2026-07'];
  var Q6=[["How much does it cost / is it covered?",73],["Same as Vyalev, or different?",43],["Similar to my current medication?",32],["Can I use it if I'm on DBS?",28],["Do I sleep with the pump?",25],["First week getting used to it?",25],["What if my neurologist isn't familiar with it?",23],["Does the needle stay under my skin?",21],["Will I still need carbidopa/levodopa?",21],["Can emotional stress affect how it works?",19]];
  var BAR6=[["Different treatment discussed",13],["Other concerns instead",9],["Doctor running behind",9],["Not interested",5],["Doctor didn't raise it",4],["Concerned about cost",2],["Didn't express OFF",2],["Side-effect worry",1]];
  var TRT6=[["No changes (revisit next appt)",46],["Changed dose / timing (not C/L)",32],["Suggested DBS",25],["Changed dose / timing (C/L)",25],["Prescribed another treatment",24],["Suggested PT or exercise",21],["OFF ‘not bad enough’",9],["Suggested another subq infusion",5]];
  var QUOTES=["What I appreciated most was not feeling pressured to make any decisions right away. It was helpful to learn about Onapgo so I can discuss it with my doctor.","I’ve spent years planning my days around symptoms. Learning about Onapgo made me feel hopeful that there may be another way to manage those ups and downs.","Hearing about ONAPGO gives me hope. It’s encouraging to know new therapies are becoming available, and I’m looking forward to asking my doctor."];
  var DETAIL={
    '2026-06':{complete:true,questionsTotal:488,questions:Q6,hcp:{initial:91,pre:185,post:163,confirmed:439},discussed:{yes:121,no:44,barriers:BAR6},treatment:TRT6,quotes:QUOTES,email:{sent:'17,346',opens:'906',open:'5.2%',clicks:'23',click:'0.13%'},webinar:'Jun 19, 2026 · 266 registered · Dr. Sagari Bette',delivery:{planned:500,delivered:502,emails:'17,346',webinar:'Jun 19 · 266 reg'}},
    '2026-07':{live:true,delivery:{planned:500,delivered:'In progress',emails:'Scheduled',webinar:'—'}}
  };

  var META=null, LIVE=null, MODE='july', CUR='2026-07', timer=null, PREV_TODAY=null, CELEBRATED=false, confettiRunning=false, PERF=null;
  var PERF_FALLBACK={"advocates":[]};
  function esc(s){return String(s==null?'':s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
  function confetti(){
    var cv=document.getElementById('confettiC'); if(!cv||confettiRunning)return; confettiRunning=true;
    if(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches){confettiRunning=false;return;}
    var ctx=cv.getContext('2d'),W=cv.width=window.innerWidth,H=cv.height=window.innerHeight;
    var cols=['#65BC7B','#2F7D4A','#33475B','#FF5D29','#8FD6A2'],P=[];
    for(var i=0;i<160;i++){P.push({x:W*(0.15+Math.random()*0.7),y:-20-Math.random()*H*0.3,vx:(Math.random()-0.5)*7,vy:Math.random()*5+3,g:0.22,r:Math.random()*6+3,c:cols[i%cols.length],a:1,rot:Math.random()*6.28,vr:(Math.random()-0.5)*0.4});}
    var t0=null,dur=2600;
    function frame(ts){ if(t0===null)t0=ts; var el=ts-t0; ctx.clearRect(0,0,W,H);
      for(var i=0;i<P.length;i++){var p=P[i];p.vy+=p.g;p.x+=p.vx;p.y+=p.vy;p.rot+=p.vr;p.a=Math.max(0,1-el/dur);
        ctx.save();ctx.globalAlpha=p.a;ctx.translate(p.x,p.y);ctx.rotate(p.rot);ctx.fillStyle=p.c;ctx.fillRect(-p.r,-p.r*0.6,p.r*2,p.r*1.3);ctx.restore();}
      if(el<dur){requestAnimationFrame(frame);}else{ctx.clearRect(0,0,W,H);confettiRunning=false;}
    }
    requestAnimationFrame(frame);
  }
  function tot(ym){var s=META.stages;return (s.initial[ym]||0)+(s.pre_hcp[ym]||0)+(s.post_hcp[ym]||0);}
  function isLive(ym){var m=(META.months||[]).find(function(x){return x.ym===ym;});return m&&m.live;}

  function renderHero(){
    var h=document.getElementById('hero'),eb,h1,meta;
    if(MODE==='july'){
      eb='Research Catalyst · Patient Advocacy Center · ONAPGO® Patient Education';
      h1='ONAPGO® Patient Education — '+(LIVE&&LIVE.month||'July 2026')+' Program Report';
      meta='<div class="period"><span class="dot"></span>Live — updated <b>'+esc(LIVE&&LIVE.as_of||'')+'</b></div><div class="period">Real-time metrics · auto-refreshing every 25s</div>';
    }else if(MODE==='platform'){
      eb='Research Catalyst · Six-Month Development Report';
      h1='AI vs PD — The App Launch';
      meta='<div class="period"><span class="betachip">BETA</span> Live at <b>ai.vers.us/PD</b></div><div class="period">The owned patient platform built for the ONAPGO® program</div>';
    }else{
      var mo=MON[+CUR.slice(5,7)],live=isLive(CUR);
      eb='Research Catalyst · Patient Advocacy Center';
      h1='ONAPGO® Patient Education — '+mo+' 2026 '+(live?'Live Report':'Program Report');
      meta=live?('<div class="period"><span class="dot"></span>Live — updated <b>'+esc(META.as_of||'')+'</b></div>'):('<div class="period">Reporting period <b>'+mo+' 2026</b></div>');
    }
    h.innerHTML='<div class="bg" style="background-image:url(\''+NEURON+'\')"></div><div class="veil"></div>'+
      '<div class="row"><div><div class="eyebrow">'+eb+'</div><h1>'+h1+'</h1><div class="accent"></div></div>'+
      '<div class="meta"><img class="logo" src="'+LOGO+'" alt="ONAPGO">'+meta+'</div></div>';
  }
  function renderModeSwitch(){
    document.getElementById('modeswitch').innerHTML=
      '<button class="mbtn'+(MODE==='july'?' on':'')+'" data-m="july"><span class="ld"></span>July — Live Report</button>';
    [].forEach.call(document.querySelectorAll('.mbtn'),function(b){b.onclick=function(){switchMode(b.getAttribute('data-m'));};});
  }
  function switchMode(m){if(m===MODE)return;MODE=m;renderShell();window.scrollTo({top:0,behavior:'smooth'});}
  function renderShell(){try{window.__celebrate=confetti;}catch(e){}renderHero();renderModeSwitch();if(MODE==='platform')renderPlatform();else renderJuly();setupTimer();}

  /* ---------- LIVE (July real-time) ---------- */
  function fullDays(d){
    var byd={};(d.days||[]).forEach(function(x){byd[+x.date.slice(8,10)]=x;});
    var out=[];for(var i=1;i<=(d.day_of_month||1);i++){var k=('0'+i).slice(-2);out.push(byd[i]||{date:(d.ym||'2026-07')+'-'+k,initial:0,pre_hcp:0,post_hcp:0,total:0});}
    return out;
  }
  function dayChart(days){
    var maxT=1;days.forEach(function(d){maxT=Math.max(maxT,d.total);});
    var cols=days.map(function(d){
      var h=Math.round(d.total/maxT*100);
      var segs=d.total>0?('<div class="seg si" style="flex:'+d.initial+'"></div><div class="seg sp" style="flex:'+d.pre_hcp+'"></div><div class="seg so" style="flex:'+d.post_hcp+'"></div>'):'';
      var lab=d.total>0?('<div class="dt">'+d.total+'</div>'):'';
      return '<div class="dcol" title="'+d.date+': '+d.total+' ('+d.initial+' / '+d.pre_hcp+' / '+d.post_hcp+')">'+lab+'<div class="dbar" style="height:'+h+'%">'+segs+'</div></div>';
    }).join('');
    var lab=days.map(function(d){var dn=+d.date.slice(8,10);return '<div>'+(dn%2===1?dn:'')+'</div>';}).join('');
    return '<div class="daychart">'+cols+'</div><div class="dxlab">'+lab+'</div>'+
      '<div class="leg"><span><i class="bi"></i>Initial</span><span><i class="bp"></i>Pre-HCP</span><span><i class="bo"></i>Post-HCP</span></div>';
  }
  function scheduleHTML(){
    // "today" from the live feed so the timeline state (past / NEXT / upcoming) is real-time.
    var today=(LIVE&&LIVE.as_of_iso)?String(LIVE.as_of_iso).slice(0,10):((LIVE&&LIVE.ym&&LIVE.day_of_month)?LIVE.ym+'-'+('0'+LIVE.day_of_month).slice(-2):'2026-07-13');
    var evs=EVENTS.slice().sort(function(a,b){return a.d<b.d?-1:(a.d>b.d?1:0);});
    var nextDone=false;
    var rows=evs.map(function(e){
      var past=e.d<today, isNext=(!past && !e.requested && e.sc!=='req' && !nextDone); if(isNext)nextDone=true;
      var md=e.dstr?e.dstr:(MON[+e.d.slice(5,7)].slice(0,3)+' '+(+e.d.slice(8,10)));
      var thumb=e.img?'<img class="evthumb" src="'+e.img+'" alt="">':'<span class="evicon t-'+e.t+'">'+(e.t==='webinar'?'▶':'✉')+'</span>';
      var sub=[e.code,e.qty].filter(Boolean).join(' · ');
      var flag=isNext?'<span class="evstate next">NEXT</span>':(past?'<span class="evstate done">✓</span>':'');
      var body=(e.full!=null)?emailVisualHTML(e.full):('<div class="evexpand">'+(e.img?'<img class="evbig" src="'+e.img+'" alt="">':'')+'<div class="evdesc">'+esc(e.desc||'')+'</div>'+(e.link?'<div style="margin-top:10px"><a class="btn ghost" href="'+e.link+'" target="_blank" rel="noopener">More info ↗</a></div>':'')+'</div>');
      return '<div class="evitem'+(past?' ev-past':'')+(isNext?' ev-next':'')+'"><div class="evrow2" onclick="var d=this.nextElementSibling;var o=d.style.display===\'block\';d.style.display=o?\'none\':\'block\';this.classList.toggle(\'open\',!o)">'+
        '<div class="evdate2">'+md+(e.approx?'*':'')+'</div>'+thumb+
        '<div class="evinfo"><div class="evtitle">'+esc(e.title)+flag+'</div>'+(sub?'<div class="evsub">'+esc(sub)+'</div>':'')+'</div>'+
        '<span class="estatus '+e.sc+'">'+esc(e.status)+'</span><span class="echev">▾</span></div>'+
        '<div class="evbody2" style="display:none">'+body+'</div></div>';
    }).join('');
    return '<div class="sched2">'+rows+'</div>'+
      '<div class="evleg"><span><i class="lg-email"></i>Email</span><span><i class="lg-webinar"></i>Webinar</span><span><i class="lg-mailer"></i>Mailer</span><span class="evleg-sep">|</span><span><b>NEXT</b> up next</span><span><b>✓</b> delivered</span></div>'+
      '<div class="note">Click any event to open its creative or details. * date approximate.</div>';
  }
  var EMAILS=[
    {n:1,code:'ONA.2026-0064',subj:'More Predictable Days',date:'July 31, 2026',status:'Coding — not MLR-approved',cls:'code',hero:'/onapgo/asset/em1_hero.jpg',
     hl:'Do Parkinson’s symptoms disrupt your day?',
     body:'ONAPGO® is a wearable infusion device that delivers medication continuously to help make days with Parkinson’s more predictable — about the size and weight of a smartphone.',
     kpi:'ONAPGO® reduces OFF time and increases daily GOOD ON time.',cta:'LEARN HOW ONAPGO CAN HELP',url:'onapgo.com/continuous-treatment'},
  ];
  function emailVisualHTML(i){var e=EMAILS[i];
    return '<div class="emailfull"><div class="efbar"><span>ONAPGO® (apomorphine hydrochloride) injection</span><span>Important Safety Information ↓</span></div>'+
      (e.hero?'<img class="efhero" src="'+e.hero+'" alt="ONAPGO email hero">':'')+
      '<div class="efbody"><div class="efhl">'+esc(e.hl)+'</div><div class="efp">'+esc(e.body)+'</div>'+
      '<div class="efkpi">'+esc(e.kpi)+'</div><div style="text-align:center"><a class="efcta">'+esc(e.cta)+' →</a></div>'+
      '<div class="efisi"><b>Important Safety Information.</b> Do not take ONAPGO if you take certain anti-nausea medicines (ondansetron, granisetron, dolasetron, palonosetron) or alosetron — the combination can cause very low blood pressure and loss of consciousness. Do not use if allergic to apomorphine or to sulfites. ONAPGO can cause dizziness or fainting, sudden sleepiness, nausea, and falls. See the Patient Information and Instructions for Use.</div></div>'+
      '<div class="effoot">'+esc(e.code)+' · Email '+e.n+' · CTA → '+esc(e.url)+' · ~7,500 planned recipients</div></div>';
  }
  function postHcpHTML(q){
    if(!q||!q.posthcp||!q.posthcp.length)return '';
    var blocks=q.posthcp.map(function(b){return '<div class="phq"><div class="qh">'+esc(b.q)+'</div>'+hbars(b.a,'')+'</div>';}).join('');
    return '<section class="panel col-6"><div class="ph"><h2>Post-HCP Guide Responses</h2><div class="sub">July · live · member-reported</div></div>'+blocks+
      (q.appts_scheduled?'<div class="note"><b>'+q.appts_scheduled+'</b> next appointments scheduled this month — driving the follow-up Pre-HCP calls.</div>':'')+'</section>';
  }
  function hcplogHTML(ym){
    var h=HCPLOG[ym];
    if(!h)return '<section class="panel col-12"><div class="ph"><h2>HCP Appointment &amp; NPI Log</h2><div class="sub">real-time · sorted by appointment month</div></div><div class="accum">Loading HCP appointment records from the CRM…</div></section>';
    var rows=h.rows||[];
    var body=rows.length?rows.map(function(r){
      var mo=r.appt_month?(MON[+r.appt_month.slice(5,7)]+' '+r.appt_month.slice(0,4)):'—';
      var disc=r.discussed==='Yes'?'<span class="dpill yes">Yes</span>':(r.discussed==='No'?'<span class="dpill no">No</span>':'—');
      return '<tr><td class="npicell">'+(r.npi?esc(r.npi):'<span class="pend">pending</span>')+'</td>'+
        '<td>'+(r.doctor?esc(r.doctor):'<span class="pend">—</span>')+'</td>'+
        '<td>'+esc(mo)+'</td><td>'+(r.appt_date?esc(r.appt_date):'—')+'</td><td>'+(r.logged?esc(r.logged):'—')+'</td>'+
        '<td style="text-align:center">'+disc+'</td></tr>';
    }).join(''):'<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:18px">No post-HCP appointment records logged yet this month.</td></tr>';
    var npiNote=h.npi_captured?('<b>'+h.npi_captured+'</b> of '+h.total+' records have an NPI on file — numbers merge in live as they are captured.'):
      'The <b>NPI Number</b> column is <b>live-merge</b>: each neurologist’s NPI fills in automatically the moment the CRM captures it — no manual step. <b>'+(h.total||0)+'</b> neurologist names are already live; NPI numbers land with the next advocate-guide update.';
    return '<section class="panel col-12"><div class="ph"><h2>HCP Appointment &amp; NPI Log</h2><div class="sub">real-time · '+rows.length+' post-HCP records · sorted by scheduled appointment month</div></div>'+
      '<div style="overflow-x:auto"><table class="rep npilog"><tr><th class="lbl">NPI Number</th><th>Neurologist</th><th>Scheduled Appt Month</th><th>Appt Date</th><th>Date Logged</th><th style="text-align:center">Discussed ONAPGO?</th></tr>'+body+'</table></div>'+
      '<div class="note">'+npiNote+' <b>Date Logged</b> is when each post-HCP response was captured; the appointment shown is the member’s scheduled visit on file (the CRM keeps one rolling appointment date, so for a post-HCP responder this is typically their next visit). These are the <b>'+(h.total||0)+'</b> post-HCP responses behind the <b>Discussed ONAPGO</b> figure ('+(h.yes||0)+' yes · '+(h.no||0)+' no).</div></section>';
  }
  // Corporate line-icon set (inline SVG, CSP-safe). 20x20, currentColor stroke.
  var ICONS={
    db:'<svg viewBox="0 0 20 20"><ellipse cx="10" cy="5" rx="6" ry="2.3"/><path d="M4 5v10c0 1.3 2.7 2.3 6 2.3s6-1 6-2.3V5"/><path d="M4 10c0 1.3 2.7 2.3 6 2.3s6-1 6-2.3"/></svg>',
    crm:'<svg viewBox="0 0 20 20"><rect x="2.5" y="4" width="15" height="10" rx="1.5"/><path d="M7 17h6M10 14v3M6 9.2l2 2 2-3 2 3.6 2-2.8"/></svg>',
    contact:'<svg viewBox="0 0 20 20"><path d="M6 2.5h5l3 3V16a1.5 1.5 0 0 1-1.5 1.5H6A1.5 1.5 0 0 1 4.5 16V4A1.5 1.5 0 0 1 6 2.5z"/><path d="M11 2.5V6h3.5M7.5 10h5M7.5 13h3"/></svg>',
    verify:'<svg viewBox="0 0 20 20"><rect x="2.5" y="5" width="15" height="10" rx="1.5"/><path d="M3 6.4l7 4.6 7-4.6"/><path d="M12.4 14.2l1.6 1.6 3-3.3"/></svg>',
    audit:'<svg viewBox="0 0 20 20"><path d="M10 2.5l6 2.2v4.6c0 4-2.6 6.6-6 8-3.4-1.4-6-4-6-8V4.7z"/><path d="M7.3 10l1.9 1.9 3.6-3.9"/></svg>',
    dash:'<svg viewBox="0 0 20 20"><path d="M3.2 14a6.8 6.8 0 0 1 13.6 0"/><path d="M10 14l3.2-3.2"/><circle cx="10" cy="14" r="1.1"/><path d="M5.5 11.2l.9.6M14.5 11.2l-.9.6M10 8.4v1"/></svg>',
    npi:'<svg viewBox="0 0 20 20"><rect x="3.3" y="3.5" width="13.4" height="13" rx="1.6"/><circle cx="8" cy="8.4" r="1.7"/><path d="M5.4 13.8c.4-1.5 1.4-2.3 2.6-2.3s2.2.8 2.6 2.3"/><path d="M12.3 7.6h2.6M12.3 10.2h2.6M12.3 12.8h1.8"/></svg>',
    chat:'<svg viewBox="0 0 20 20"><path d="M4 4.5h12A1.5 1.5 0 0 1 17.5 6v6A1.5 1.5 0 0 1 16 13.5H8.2L4.5 16.8V13.5H4A1.5 1.5 0 0 1 2.5 12V6A1.5 1.5 0 0 1 4 4.5z"/><path d="M8.4 8a1.7 1.7 0 1 1 2.3 1.6c-.5.3-.7.6-.7 1.2"/><path d="M10 12.6h.01"/></svg>',
    clock:'<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="6.4"/><path d="M10 6.4V10l2.6 1.6"/></svg>',
    zero:'<svg viewBox="0 0 20 20"><rect x="4.8" y="9" width="10.4" height="7.4" rx="1.4"/><path d="M7 9V7a3 3 0 0 1 6 0v2"/><path d="M10 11.8v2.2"/></svg>'
  };
  function hardHTML(){
    var ITEMS=[
      ['db','Unified Postgres Database','One SQL Postgres system of record — a shared source of truth across advocate, director, and sponsor.'],
      ['crm','Custom CRM · Live Monitoring','A purpose-built advocacy CRM with real-time director oversight of every active call and queue.'],
      ['contact','Contact Capture in the Guide','Contact details are captured inside the discussion guide itself, with metadata tracking on each interaction.'],
      ['verify','Post-Call Verification Emails','Patients receive a verification email at call close confirming their contact details and captured form data.'],
      ['audit','Call-Audit Reconciliation','Automated audits reconcile logged call duration and timing against the carrier phone reports.'],
      ['dash','Live Client Dashboard','Sponsors see program performance in real time on this live dashboard — no waiting for month-end.'],
      ['npi','Real-Time HCP / NPI Log','Neurologist engagement is tracked live and time-stamped by appointment date.'],
      ['chat','Direct Real-Time Patient Questions','Verbatim member questions surface directly and in real time — the community’s actual voice.'],
      ['clock','Punch-Clock Duty Signaling','Advocate on-duty status is driven directly by signed punch-clock clock-ins, not manual entry.'],
      ['zero','Zero-Trust, Hardcoded Controls','A zero-trust posture: guardrails are hardcoded into the system, not left to policy — enforced by construction.']
    ];
    var rows=ITEMS.map(function(it){
      return '<div class="harditem"><span class="hardico c-'+it[0]+'">'+ICONS[it[0]]+'</span>'+
        '<div class="hardtx"><div class="hardt">'+esc(it[1])+'</div><div class="hardd">'+esc(it[2])+'</div></div></div>';
    }).join('');
    return '<section class="panel col-6"><div class="ph"><h2>Accountability &amp; System Hardening</h2><div class="sub">how the program is engineered for transparency</div></div><div class="hardgrid">'+rows+'</div></section>';
  }
  var ADV_HIDE={giselle:1,jen:1,jennifer:1,support:1};
  // Matched as a substring of the (lowercased) display name so it works with formal names
  // like "Mr. Taylor". Duane Taylor works 7–3; everyone else defaults to 8–12 · 1–5.
  var ADV_SCHED={taylor:'7:00 AM – 3:00 PM'};
  function raceHTML(){
    if(!PERF||!PERF.advocates)return '<div class="accum">Loading advocate performance…</div>';
    var W=20,A=10,MED=['🥇','🥈','🥉'],rows=[];
    PERF.advocates.forEach(function(v){
      if(ADV_HIDE[String(v.name||'').toLowerCase().split(' ')[0]])return;
      var r={name:v.name,calls:v.calls||0,assists:v.assists||0,forms:v.forms||0};
      if(r.calls>0||r.assists>0||r.forms>0)rows.push(r);
    });
    if(!rows.length)return '<div class="accum">No advocate activity logged yet today.</div>';
    rows.sort(function(a,b){return (b.forms*W+b.assists*A+b.calls)-(a.forms*W+a.assists*A+a.calls);});
    var maxLen=1;rows.forEach(function(v){maxLen=Math.max(maxLen,v.calls,v.assists*A,v.forms*W);});
    function pct(n){return Math.max(0,Math.min(100,n/maxLen*100)).toFixed(1)+'%';}
    var lanes=rows.map(function(v,i){
      return '<div class="rlane"><div class="rname">'+(MED[i]||'')+' '+esc(v.name)+'</div><div class="rbars">'
        +'<div class="rrow"><span class="rn">'+v.calls+'</span><div class="rtrack"><div class="rfill c" style="width:'+pct(v.calls)+'"></div></div></div>'
        +'<div class="rrow"><span class="rn">'+v.assists+'</span><div class="rtrack"><div class="rfill a" style="width:'+pct(v.assists*A)+'"></div></div></div>'
        +'<div class="rrow"><span class="rn">'+v.forms+'</span><div class="rtrack"><div class="rfill f" style="width:'+pct(v.forms*W)+'"></div></div></div>'
        +'</div></div>';
    }).join('');
    return '<div class="rleg"><span><i class="rsw c"></i>Calls</span><span><i class="rsw a"></i>Assist</span><span><i class="rsw f"></i>Forms</span></div><div class="race">'+lanes+'</div>';
  }
  function advocatesHTML(){
    var a=ADV; if(!a||!a.advocates)return '<div class="accum">Loading advocate clock-in status…</div>';
    var list=a.advocates.filter(function(x){return !ADV_HIDE[String(x.name||'').toLowerCase().split(' ')[0]];});
    var onNow=list.filter(function(x){return x.clocked_in;}).length;
    var chips=list.map(function(x){
      var dn=String(x.name||'').toLowerCase(),sch='8–12 · 1–5';
      for(var key in ADV_SCHED){if(dn.indexOf(key)>=0){sch=ADV_SCHED[key];break;}}
      return '<div class="advchip'+(x.clocked_in?' on':'')+'"><span class="advdot"></span><div class="advmeta"><div class="advn">'+esc(x.name)+'</div><div class="advsch">'+sch+'</div></div><div class="advs">'+(x.clocked_in?'On shift':'Off')+'</div></div>';
    }).join('');
    var onb='<div class="advchip onb"><span class="advdot"></span><div class="advmeta"><div class="advn">New Advocate</div><div class="advsch">Onboarding · joining soon</div></div><div class="advs">Onboarding</div></div>';
    return '<div class="advhead"><span class="dot"></span><b>'+onNow+'</b> of '+list.length+' advocates on shift right now &nbsp;·&nbsp; <b>2</b> onboarding</div><div class="advgrid">'+chips+onb+onb+'</div>';
  }
  function renderLive(){
    var d=LIVE,s=d.stages,pct=Math.min(100,Math.round(d.total/d.target*100));
    var html='<div class="grid">';
    html+='<section class="panel col-4"><div class="livehead"><span class="dot"></span>MONTH-TO-DATE · LIVE</div>'+
      '<div class="bignum" id="mtdNum">'+d.total+'</div><div class="biglbl">Branded Patient Discussions</div>'+
      '<div class="bigsub">Day '+d.day_of_month+' of '+d.days_in_month+' · target '+d.target+'/month</div>'+
      '<div class="pbar"><div class="pfill" style="width:'+pct+'%"></div></div>'+
      '<div class="pacegrid"><span>'+pct+'% of goal</span><span>Monthly goal: <b>'+d.target+'</b> discussions</span></div>'+
      '<div class="note">Progress toward the '+d.target+'-discussion monthly goal — updates live as advocates complete guides.</div></section>';
    html+='<section class="panel col-8"><div class="ph"><h2>Live Discussion Mix</h2><div class="sub">'+esc(d.month)+' · updated '+esc(d.as_of)+'</div></div>'+
      '<div class="scards"><div class="scard"><div class="n">'+s.initial+'</div><div class="l">Initial Discussions</div><div class="tdy">+'+d.today.initial+' today</div></div>'+
      '<div class="scard s2"><div class="n">'+s.pre_hcp+'</div><div class="l">Pre-HCP Discussions</div><div class="tdy">+'+d.today.pre_hcp+' today</div></div>'+
      '<div class="scard s3"><div class="n">'+s.post_hcp+'</div><div class="l">Post-HCP Discussions</div><div class="tdy">+'+d.today.post_hcp+' today</div></div>'+
      '<div class="scard today" style="cursor:pointer" title="Tap to celebrate" onclick="window.__celebrate&&window.__celebrate()"><div class="n" id="todayNum">'+d.today.total+'</div><div class="l">Completed Today 🎉</div><div class="tdy">live — celebrates each new one</div></div></div>'+
      '<div style="margin-top:16px"><div class="ph" style="border:none;margin:0 0 2px;padding:0"><h2 style="font-size:14px">Daily Activity — '+esc(d.month)+'</h2></div>'+dayChart(fullDays(d))+'</div></section>';
    html+='<section class="panel col-12"><div class="ph"><h2>Advocates On Shift</h2><div class="sub">live clock-in status from the CRM</div></div>'+advocatesHTML()+'</section>';
    html+='<section class="panel col-6"><div class="ph"><h2>Schedule of Events</h2><div class="sub">Upcoming program calendar</div></div>'+scheduleHTML()+'</section>';
    html+='<section class="panel col-6"><div class="ph"><h2>How this month is tracking</h2><div class="sub">live from crm.parkinsons.community</div></div>'+
      '<div class="note" style="font-size:12.5px;color:var(--ink)">The Patient Advocacy Center has logged <b>'+d.total+'</b> branded discussions so far in '+esc(d.month)+' ('+s.initial+' Initial · '+s.pre_hcp+' Pre-HCP · '+s.post_hcp+' Post-HCP). Full qualitative capture — discussed-ONAPGO, treatment outcomes, post-HCP responses and member questions — is on the <b>Monthly Reports → July</b> tab, updating live through the month.</div></section>';
    html+='</div>';
    document.getElementById('view').innerHTML=html;
    if(PREV_TODAY===null)PREV_TODAY=(d.today?d.today.total:0);
    if(!CELEBRATED&&d.today&&d.today.total>0){CELEBRATED=true;setTimeout(confetti,350);}
  }

  /* ---------- JULY (merged: live ops + full monthly report) ---------- */
  function renderJuly(){
    var d=LIVE||{},s=d.stages||{initial:0,pre_hcp:0,post_hcp:0},td=d.today||{initial:0,pre_hcp:0,post_hcp:0,total:0};
    var tgt=d.target||500,pct=Math.min(100,Math.round((d.total||0)/tgt*100));
    var html=kpiRow('2026-07')+'<div class="grid">';
    html+='<section class="panel col-4"><div class="livehead"><span class="dot"></span>MONTH-TO-DATE · LIVE</div>'+
      '<div class="bignum" id="mtdNum">'+(d.total||0)+'</div><div class="biglbl">Branded Patient Discussions</div>'+
      '<div class="bigsub">Day '+(d.day_of_month||'—')+' of '+(d.days_in_month||31)+' · target '+tgt+'/month</div>'+
      '<div class="pbar"><div class="pfill" style="width:'+pct+'%"></div></div>'+
      '<div class="pacegrid"><span>'+pct+'% of goal</span><span>Monthly goal: <b>'+tgt+'</b> discussions</span></div>'+
      '<div class="note">Progress toward the '+tgt+'-discussion monthly goal — updates live as advocates complete guides.</div></section>';
    html+='<section class="panel col-8"><div class="ph"><h2>Live Discussion Mix</h2><div class="sub">'+esc(d.month||'July 2026')+' · updated '+esc(d.as_of||'')+'</div></div>'+
      '<div class="scards"><div class="scard"><div class="n" id="cI">'+s.initial+'</div><div class="l">Initial Discussions</div><div class="tdy">+'+td.initial+' today</div></div>'+
      '<div class="scard s2"><div class="n" id="cP">'+s.pre_hcp+'</div><div class="l">Pre-HCP Discussions</div><div class="tdy">+'+td.pre_hcp+' today</div></div>'+
      '<div class="scard s3"><div class="n" id="cO">'+s.post_hcp+'</div><div class="l">Post-HCP Discussions</div><div class="tdy">+'+td.post_hcp+' today</div></div>'+
      '<div class="scard today" style="cursor:pointer" title="Tap to celebrate" onclick="window.__celebrate&&window.__celebrate()"><div class="n" id="todayNum">'+td.total+'</div><div class="l">Completed Today 🎉</div><div class="tdy">live — celebrates each new one</div></div></div>'+
      '<div style="margin-top:16px"><div class="ph" style="border:none;margin:0 0 2px;padding:0"><h2 style="font-size:14px">Daily Activity — '+esc(d.month||'July 2026')+'</h2></div>'+dayChart(fullDays(d))+'</div></section>';
    html+='<section class="panel col-12"><div class="ph"><h2>Advocates On Shift</h2><div class="sub">live clock-in status from the CRM · scheduled hours shown per advocate</div></div>'+advocatesHTML()+'</section>';
    html+='<section class="panel col-12"><div class="ph"><h2>Daily Advocate Performance</h2><div class="sub">today · Calls / Assist / Forms · live from the CRM</div></div>'+raceHTML()+'</section>';
    html+=metricsPanel();
    html+=detailPanels('2026-07');
    html+='<section class="panel col-12"><div class="ph"><h2>The AI vs PD App — Try the Beta</h2><div class="sub">The owned, AI-native platform behind the program · tap Trial Beta to open the live app in a new window</div></div>'+appPromoHTML()+'</section>';
    html+='</div>';
    document.getElementById('view').innerHTML=html;
    if(isLive('2026-07')&&!QUAL['2026-07']){fetchQual('2026-07').then(function(qd){QUAL['2026-07']=qd;if(MODE==='july')renderJuly();});}
    if(isLive('2026-07')&&!HCPLOG['2026-07']){fetchHcplog('2026-07').then(function(hd){HCPLOG['2026-07']=hd;if(MODE==='july')renderJuly();});}
    if(isLive('2026-07')&&!(PERF&&PERF.advocates&&PERF.advocates.length)){fetchPerf().then(function(pd){PERF=pd;if(MODE==='july')renderJuly();});}
    if(PREV_TODAY===null)PREV_TODAY=td.total;
    if(!CELEBRATED&&td.total>0){CELEBRATED=true;setTimeout(confetti,350);}
  }

  /* ---------- REPORTS (historic monthly) ---------- */
  function buildNav(){
    return '<nav class="nav">'+SHOW.map(function(ym){var mo=MON[+ym.slice(5,7)],live=isLive(ym),t=tot(ym);
      var st=live?('Month-to-date · '+t+' discussions'):(t+' discussions delivered');
      var badge=live?'<span class="badge"><span class="d"></span>LIVE</span>':'';
      return '<button class="mtab'+(ym===CUR?' on':'')+'" data-ym="'+ym+'"><div class="mo">'+mo+' 2026'+badge+'</div><div class="st">'+st+'</div></button>';
    }).join('')+'</nav>';
  }
  function hbars(list,cls){var max=Math.max.apply(null,list.map(function(x){return x[1];}));
    return '<div class="hbars">'+list.map(function(x){return '<div class="hrow'+(cls==='q'?' q':'')+'"><div class="lab">'+esc(x[0])+'</div><div class="val">'+x[1]+'</div><div class="htrack"><div class="'+(cls==='q'?'hfill qfill':'hfill')+'" style="width:'+Math.max(3,x[1]/max*100)+'%"></div></div></div>';}).join('')+'</div>';}
  function metricsPanel(){
    var s=META.stages,maxv=1;SHOW.forEach(function(ym){['initial','pre_hcp','post_hcp'].forEach(function(k){maxv=Math.max(maxv,s[k][ym]||0);});});
    var groups=SHOW.map(function(ym){var mo=MON[+ym.slice(5,7)];
      function bar(k,cls){var v=s[k][ym]||0;return '<div class="bar '+cls+'" style="height:'+Math.max(2,v/maxv*100)+'%" title="'+mo+' '+k+': '+v+'"><span>'+v+'</span></div>';}
      return '<div class="grp'+(ym===CUR?' cur':'')+'">'+bar('initial','barI')+bar('pre_hcp','barP')+bar('post_hcp','barO')+'</div>';
    }).join('');
    var xlab=SHOW.map(function(ym){var mo=MON[+ym.slice(5,7)];return '<div class="'+(ym===CUR?'cur':'')+'">'+mo+(isLive(ym)?' ▸ live':'')+'</div>';}).join('');
    var head='<tr><th class="lbl">Deliverable</th>'+SHOW.map(function(ym){return '<th class="'+(ym===CUR?'sel':'')+'">'+MON[+ym.slice(5,7)].slice(0,3)+(isLive(ym)?' ▸':'')+'</th>';}).join('')+'</tr>';
    function row(k,lbl){return '<tr><td class="lbl">'+lbl+'</td>'+SHOW.map(function(ym){return '<td class="'+(ym===CUR?'sel':'')+'">'+(s[k][ym]||0)+'</td>';}).join('')+'</tr>';}
    var totrow='<tr class="tot"><td class="lbl">Monthly Totals</td>'+SHOW.map(function(ym){return '<td class="'+(ym===CUR?'sel':'')+'">'+tot(ym)+'</td>';}).join('')+'</tr>';
    return '<section class="panel col-4"><div class="ph"><h2>Patient Advocacy Center Metrics</h2><div class="sub">Branded discussions · Initial / Pre-HCP / Post-HCP</div></div>'+
      '<div class="chartwrap"><div class="chart"><div class="bars">'+groups+'</div><div class="xlab">'+xlab+'</div>'+
      '<div class="leg"><span><i class="bi"></i>Initial</span><span><i class="bp"></i>Pre-HCP</span><span><i class="bo"></i>Post-HCP</span></div></div>'+
      '<div style="overflow-x:auto"><table class="rep">'+head+row('initial','Initial Discussions')+row('pre_hcp','Pre-HCP Discussions')+row('post_hcp','Post-HCP Discussions')+totrow+'</table></div></div></section>';
  }
  function kpiRow(ym){var d=DETAIL[ym]||{},live=isLive(ym),t=tot(ym),s=META.stages,mo=MON[+ym.slice(5,7)];
    function k(cls,n,l,sub,sm){return '<div class="kpi '+cls+'"><div class="n'+(sm?' sm':'')+'">'+n+'</div><div class="l">'+l+'</div><div class="s">'+sub+'</div></div>';}
    if(live){var q=QUAL[ym]||{};return '<section class="kpis">'+k('',t,'Branded Patient Discussions','July · live from CRM')+k('b2',(q.questions_total!=null?q.questions_total:'—'),'Member Questions Captured','month-to-date')+k('b3',(q.hcp_appts!=null?q.hcp_appts:'—'),'HCP Appointments Logged','month-to-date')+k('b4','Jul 31','Educational Emails','scheduled send',true)+k('b5','Sep 18','Educational Webinar','1:00 PM ET',true)+'</section>';}
    return '<section class="kpis">'+k('',t,'Branded Patient Discussions',mo+' · 100% delivered')+k('b2',d.questionsTotal||'—','Member Questions Captured',mo)+k('b3',(d.hcp&&d.hcp.confirmed)||'—','Confirmed Neurologist NPIs',mo)+k('b4',(d.email&&d.email.sent)||'—','Educational Emails Sent',mo,true)+k('b5',mo==='June'?'Jun 19':'—','Educational Webinar',(d.webinar?'266 registered':'—'),true)+'</section>';
  }
  function deliveryPanel(span){
    function r(ymx){var dd=DETAIL[ymx]||{},dl=dd.delivery||{},mo=MON[+ymx.slice(5,7)].slice(0,3),cls=(ymx===CUR?'sel':'');
      return '<tr'+(ymx===CUR?' class="tot"':'')+'><td class="lbl '+cls+'">'+mo+'-26</td><td class="'+cls+'">'+(dl.planned||'—')+'</td><td class="'+cls+'">'+(dl.delivered!=null?dl.delivered:'—')+'</td><td class="'+cls+'">'+(dl.emails||'—')+'</td><td class="'+cls+'">'+(dl.webinar||'—')+'</td></tr>';}
    return '<section class="panel col-'+span+'"><div class="ph"><h2>Delivery Schedule</h2><div class="sub">Calls · Emails · Webinars</div></div><div style="overflow-x:auto"><table class="rep"><tr><th class="lbl">Month</th><th>Calls Planned</th><th>Calls Delivered</th><th>Emails</th><th>Webinar</th></tr>'+SHOW.map(r).join('')+'</table></div><div class="note">Expanded cadence: 500 branded calls / 7,500-email plan per month.</div></section>';
  }
  function detailPanels(ym){var d=DETAIL[ym]||{},out='',live=isLive(ym);
    if(live){
      var q=QUAL[ym];
      if(!q){return out+'<section class="panel col-12"><div class="ph"><h2>Loading live figures…</h2><div class="sub">July · crm.parkinsons.community</div></div><div class="accum">Pulling July captures from the CRM…</div></section>';}
      var yes=q.discussed.yes||0,no=q.discussed.no||0,total=yes+no,pct=total?Math.round(yes/total*100):0,C=2*Math.PI*52,yesArc=(total?yes/total*C:0).toFixed(1);
      out+='<section class="panel col-4"><div class="ph"><h2>Discussed ONAPGO® with HCP</h2><div class="sub">July · live</div></div><div class="donutwrap"><div class="donut"><svg viewBox="0 0 120 120" width="150" height="150" style="transform:rotate(-90deg)"><circle cx="60" cy="60" r="52" fill="none" stroke="#8A96A0" stroke-width="16"></circle><circle cx="60" cy="60" r="52" fill="none" stroke="#65BC7B" stroke-width="16" stroke-dasharray="'+yesArc+' '+C.toFixed(1)+'"></circle></svg><div class="ctr"><div class="p">'+pct+'%</div><div class="t">DISCUSSED</div></div></div><div class="dleg"><div class="r"><i style="background:#65BC7B"></i>Yes — discussed <b>&nbsp;'+yes+'</b></div><div class="r"><i style="background:#8A96A0"></i>No — not yet <b>&nbsp;'+no+'</b></div><div class="r" style="color:var(--muted)">'+total+' post-HCP responses so far</div></div></div></section>';
      if(q.barriers&&q.barriers.length)out+='<section class="panel col-4"><div class="ph"><h2>Why ONAPGO® Not Discussed</h2><div class="sub">July · live</div></div>'+hbars(q.barriers,'')+'</section>';
      if(q.treatment&&q.treatment.length)out+='<section class="panel col-4"><div class="ph"><h2>Treatment Plan Changes</h2><div class="sub">July · post-HCP · live</div></div>'+hbars(q.treatment,'q')+'</section>';
      out+=hcplogHTML(ym);
      if(q.questions&&q.questions.length)out+='<section class="panel col-6"><div class="ph"><h2>Member Questions — Verbatim</h2><div class="sub">July · captured on calls</div></div><div class="qlist">'+q.questions.map(function(x){return '<div class="qitem">“'+esc(x[0])+'”'+(x[1]>1?' <span class="qn">×'+x[1]+'</span>':'')+'</div>';}).join('')+'</div></section>';
      out+=postHcpHTML(q);
      out+='<section class="panel col-6"><div class="ph"><h2>Schedule of Events</h2><div class="sub">Upcoming program calendar</div></div>'+scheduleHTML()+'</section>';
      out+=hardHTML();
      return out;
    }
    if(d.discussed){var yes=d.discussed.yes,no=d.discussed.no,total=yes+no,pct=Math.round(yes/total*100),C=2*Math.PI*52,yesArc=(yes/total*C).toFixed(1);
      out+='<section class="panel col-4"><div class="ph"><h2>Discussed ONAPGO® with HCP</h2><div class="sub">Post-HCP capture</div></div><div class="donutwrap"><div class="donut"><svg viewBox="0 0 120 120" width="150" height="150" style="transform:rotate(-90deg)"><circle cx="60" cy="60" r="52" fill="none" stroke="#8A96A0" stroke-width="16"></circle><circle cx="60" cy="60" r="52" fill="none" stroke="#65BC7B" stroke-width="16" stroke-dasharray="'+yesArc+' '+C.toFixed(1)+'"></circle></svg><div class="ctr"><div class="p">'+pct+'%</div><div class="t">DISCUSSED</div></div></div><div class="dleg"><div class="r"><i style="background:#65BC7B"></i>Yes — discussed <b>&nbsp;'+yes+'</b></div><div class="r"><i style="background:#8A96A0"></i>No — no chance <b>&nbsp;'+no+'</b></div><div class="r" style="color:var(--muted)">'+total+' total responses</div></div></div><div class="note"><b>If not, why?</b> '+d.discussed.barriers.map(function(b){return esc(b[0])+' '+b[1];}).join(' · ')+'.</div></section>';}
    if(d.questions)out+='<section class="panel col-6"><div class="ph"><h2>Top Member Questions</h2><div class="sub">June · '+d.questionsTotal+' captured</div></div>'+hbars(d.questions,'')+'</section>';
    if(d.hcp)out+='<section class="panel col-6"><div class="ph"><h2>HCP Engagement</h2><div class="sub">June · neurologist NPIs captured</div></div><div class="hcp"><div class="stat"><div class="n">'+d.hcp.initial+'</div><div class="l">Initial-form neurologists</div></div><div class="stat s2"><div class="n">'+d.hcp.pre+'</div><div class="l">Pre-HCP-form neurologists</div></div><div class="stat s3"><div class="n">'+d.hcp.post+'</div><div class="l">Post-HCP-form neurologists</div></div></div><div class="hcpband"><div class="big">'+d.hcp.confirmed+'</div><div class="t">confirmed neurologist NPIs across '+tot(ym)+' June discussions — a verified prescriber map for the program.</div></div></section>';
    if(d.treatment)out+='<section class="panel col-7"><div class="ph"><h2>Treatment Plan Changes After HCP Visit</h2><div class="sub">Member-reported · 187 responses</div></div>'+hbars(d.treatment,'q')+'</section>';
    if(d.quotes)out+='<section class="panel col-5"><div class="ph"><h2>Community Voices</h2><div class="sub">Parkinson’s community members</div></div><div style="display:flex;flex-direction:column;gap:10px">'+d.quotes.map(function(q,i){return '<div class="quote'+(i===1?' b2':i===2?' b3':'')+'">“'+esc(q)+'”</div>';}).join('')+'</div></section>';
    out+=deliveryPanel(7);
    if(d.email)out+='<section class="panel col-5"><div class="ph"><h2>Email Program</h2><div class="sub">June send</div></div><div class="etiles"><div class="etile"><div class="n">'+d.email.sent+'</div><div class="l">Emails Sent</div></div><div class="etile"><div class="n">'+d.email.opens+'</div><div class="l">Opens</div></div><div class="etile"><div class="n">'+d.email.open+'</div><div class="l">Open Rate</div></div><div class="etile"><div class="n">'+d.email.clicks+'</div><div class="l">Clicks</div></div><div class="etile"><div class="n">'+d.email.click+'</div><div class="l">Click Rate</div></div></div><div class="note">The June branded educational email deployed June 26, 2026.</div></section>';
    return out;
  }
  function renderReports(){
    document.getElementById('view').innerHTML=buildNav()+kpiRow(CUR)+'<div class="grid">'+metricsPanel()+detailPanels(CUR)+'</div>';
    [].forEach.call(document.querySelectorAll('.mtab'),function(b){b.onclick=function(){CUR=b.getAttribute('data-ym');renderReports();renderHero();};});
    if(isLive(CUR)&&!QUAL[CUR]){fetchQual(CUR).then(function(qd){QUAL[CUR]=qd;if(MODE==='reports'&&isLive(CUR))renderReports();});}
  }

  /* ---------- APP LAUNCH (the six-month development report) ---------- */
  var APP_URL='https://ai.vers.us/PD';
  var MDS_URL='https://www.mdscongress.org/';
  function openDemo(u){window.open(u||APP_URL,'aivspd','popup=yes,width=440,height=880,scrollbars=yes,resizable=yes');}
  // The production brand mark, reproduced from the live app: blue-gradient badge, gold-stroked
  // shield with the double-strand mark, and the AI·VS|PD wordmark (gold dot + slash, PD muted).
  function vpBadge(s){return '<svg viewBox="0 0 100 100" width="'+s+'" height="'+s+'" style="display:block" aria-hidden="true"><defs><linearGradient id="vpg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2e62b4"/><stop offset="1" stop-color="#0e2652"/></linearGradient></defs><rect width="100" height="100" rx="24" fill="url(#vpg)"/><rect x="3.5" y="3.5" width="93" height="93" rx="21" fill="none" stroke="rgba(255,255,255,.3)" stroke-width="1.5"/><path d="M50 20 L76 29 L76 51 C76 69 64 80 50 85 C36 80 24 69 24 51 L24 29 Z" fill="#0e2652" stroke="#c8a23c" stroke-width="4.5" stroke-linejoin="round"/><circle cx="50" cy="31" r="3.4" fill="#c8a23c"/><path d="M50 33.5 V76" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/><path d="M46 37 C44 41.5 44 46.5 50 49.5 C57 53 57 58.5 50 61.5 C44 64.5 45 69 49 72" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M54 37 C56 41.5 56 46.5 50 49.5 C43 53 43 58.5 50 61.5 C56 64.5 55 69 51 72" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="46" cy="36.5" r="1.7" fill="#fff"/><circle cx="54" cy="36.5" r="1.7" fill="#fff"/></svg>';}
  function vpWord(px){return '<span class="vpword" style="font-size:'+px+'px" aria-label="AI versus PD">AI<i class="d"></i>VS<i class="b"></i><b>PD</b></span>';}
  function vpLogo(s,px){return '<span class="vplogo">'+vpBadge(s)+vpWord(px)+'</span>';}
  // Neuro-facing protocol titles — the clinical entity carried on every record, verbatim from the
  // manifests / live library ("Consult a Movement Disorders Specialist for evaluation of {entity}").
  var PROTOCOLS=[
    ["Freezing of Gait at Visual Thresholds (Doorways, Elevators)","Freezing & Falling"],
    ["Freezing of Gait in Open Spaces and Crowds (Sensory Overload Freezing)","Freezing & Falling"],
    ["Freezing of Gait and Rhythmic Auditory Stimulation (RAS)","Exercise & Rehab"],
    ["Retropulsion (Backward Balance Loss)","Freezing & Falling"],
    ["Pivot Falls (Turning-Related Balance Failure)","Freezing & Falling"],
    ["Stair Descending Failure (Festination and Forward Momentum Crisis)","Freezing & Falling"],
    ["Camptocormia (Severe Forward Trunk Flexion)","Freezing & Falling"],
    ["Bed Mobility Crisis (Axial Rigidity)","Freezing & Falling"],
    ["Visuospatial Misjudgments (Clipping Doorframes, Depth Perception Failure)","Freezing & Falling"],
    ["Motor-Cognitive Interference (Dual-Task Failure)","Freezing & Falling"],
    ["Morning Akinesia (Delayed Levodopa Onset / Gastroparesis)","Medication"],
    ["Early Morning Toe and Foot Dystonia (OFF-State Dopamine Crash)","Pain & Stiffness"],
    ["Sudden OFF Episodes Unresponsive to Oral Medication (Rescue Therapy Candidates)","Medication"],
    ["Subcutaneous Apomorphine Injection for Severe OFF Episodes","Medication"],
    ["Levodopa Absorption Failure from Bulk-Forming Fiber (Psyllium Gel Matrix Trapping)","Medication"],
    ["Iron and B6 Supplement Interference with Levodopa Absorption","Medication"],
    ["Small Intestinal Bacterial Overgrowth Disrupting Levodopa Absorption","Medication"],
    ["H. Pylori Infection Disrupting Levodopa Dissolution and Absorption","Medication"],
    ["Anticholinergic OTC Medication Dangers (Diphenhydramine)","Sleep"],
    ["OTC Decongestant Interaction with MAO-B Inhibitors (Hypertensive Crisis Risk)","Reactions"],
    ["Epinephrine–MAO-B Inhibitor Interaction Risk During Dental Procedures","Drug Interactions"],
    ["Dopamine Agonist Withdrawal Syndrome (DAWS) — Psychiatric Emergency from Rapid Taper","Reactions"],
    ["Impulse Control Disorder — Hypersexuality (Dopamine Agonist-Induced ICD)","Reactions"],
    ["Sudden-Onset Sleep Attacks (Dopamine Agonist Side Effect)","Sleep"],
    ["Alpha-Blocker and Parkinson's Dysautonomia Interaction","Drug Interactions"],
    ["Beta-Blocker Worsening Parkinson's Bradykinesia","Drug Interactions"],
    ["Drug-Induced Parkinsonism (DIP)","Drug Interactions"],
    ["Postprandial Hypotension (Post-Meal Blood Pressure Crash)","Blood Pressure"],
    ["Supine Hypertension with Orthostatic Hypotension (Autonomic BP Paradox)","Blood Pressure"],
    ["Defecation Syncope (Valsalva-Induced Bathroom Falls)","Blood Pressure"],
    ["Shower Syncope (Thermoregulatory Dysautonomia Falls)","Blood Pressure"],
    ["Capgras Delusion (Imposter Psychosis in Advanced PD)","Hallucinations"],
    ["Othello Syndrome (Dopamine-Induced Delusional Jealousy and Psychosis)","Hallucinations"],
    ["Pseudobulbar Affect — Involuntary Emotional Expression","Neuropsychiatry"],
    ["Anosognosia — Loss of Capacity for Self-Appraisal","Neuropsychiatry"],
    ["Formication — Tactile Hallucinations (Dopaminergic Toxicity / Lewy Body Pathology)","Neuropsychiatry"],
    ["Silent Aspiration (Blunted Cough Reflex, Wet Vocal Quality After Swallowing)","Eating & Swallowing"],
    ["Nocturnal Saliva Aspiration (Bradykinesia-Suppressed Swallowing Reflex During Sleep)","Eating & Swallowing"],
    ["Hospital Safety Failure (Contraindicated Medications, Missing PD Drugs in ER)","Hospital & ER"],
    ["UTI-Induced Acute Delirium Mimicking Parkinson's Progression","Hospital & ER"],
    ["Deprescribing Levodopa","Palliative & Comfort"],
    ["Progressive Supranuclear Palsy (PSP) — Differential Diagnosis","Diagnostics"]
  ];
  var CLUSTERS=[["Freezing & Falling",32],["Medication",18],["Hospital & ER",17],["Something Else?",14],["Eating & Swallowing",14],["Personality",12],["Late Stage",12],["Reactions",11],["Blood Pressure",6],["Hallucinations",6],["Caregiver",5],["Pain & Stiffness",4],["Sleep",3]];
  var PROTO_LIVE=154, PROTO_TARGET=250;
  // The thesis — every stat sourced (footnotes rendered under the section).
  var THESIS=[
    ["−61%","organic click-through on informational searches when an AI answer appears","Seer Interactive, 2025"],
    ["60%","of searches now end without a single click to any website","Bain & Co., 2025"],
    ["80%","of phone calls from unrecognized numbers go unanswered","Hiya State of the Call, 2025"],
    ["73%","of pharma leaders run or will launch a direct-to-patient program within the year","ixlayer / DHC survey, 2025"]
  ];
  var THESIS2=[
    ["1.1M","Americans living with Parkinson's — 90,000 newly diagnosed each year","Parkinson's Foundation"],
    ["64%","of PD patients used telehealth during the pandemic — up from 10% before","Frontiers in Neurology, 2022"],
    ["100K+","members in a single online PD community","MyParkinsonsTeam, 2025"],
    ["~1%","of top-ranked PD pages were judged readable by the average patient in a 2024 review","PD info scoping review (PMC), 2024"]
  ];
  var DOMAINS=[
    ["D1","Attribution Firewall","att",false],["D2","Brand Compliance","att",true],
    ["D3","Structural Completeness","cmo",false],["D4","CTA Compliance","cmo",false],
    ["D5","Medication Safety & Pharmacovigilance","mds",true],["D6","Legal, Regulatory & Privacy","att",true],
    ["D7","False-Assurance, Hallucination & EBM","mds",true],["D8","BLUF / Zero-Click Answer","cmo",false],
    ["D9","PD Accessibility","cmo",false],["D10","911 Emergency & Crisis Overrides","mds",true],
    ["D11","Citation Integrity","mds",false],["D12","Semantic Quality (CMO Persona)","cmo",true]
  ];
  var OWN={att:"Attorney",mds:"MDS",cmo:"CMO"};
  // Real rules, verbatim IDs, from mlr_scoring_engine.py / mlr_semantic_analyzer.py
  var MLR_RULES=[
    ["2.1","HARD FAIL","Any sponsor or competitor brand name in community content — auto-resolved to the generic term. The attribution firewall that keeps the library independent and the sponsor safe."],
    ["10.4","HARD FAIL","Akinetic-crisis topic detected with no 911 language in the article body — the piece cannot publish."],
    ["6.4","HARD FAIL","Any 'HIPAA compliant / your data is protected' representation — we are not a HIPAA entity and the engine refuses the claim."],
    ["6.10","HARD FAIL","CPOM violation — any language implying we are a healthcare provider ('our clinical team', 'we diagnose') is blocked."],
    ["12.4","HARD FAIL","Platitude density: more than five bare 'consult your doctor' lines with no specific prep action — the article is 'sanitized to uselessness' and fails."],
    ["5.13","ADVISORY","SSRI + MAO-B inhibitor both mentioned without a serotonin-syndrome warning — routed to human review."]
  ];
  var LAW=[
    ["FDA & Promotion",["FDA SIUU Guidance","21 CFR 202.1 — Fair Balance","CDER anti-conflation"]],
    ["FTC & Claims",["FTC-DSHEA truth-in-advertising","Absolute-claim ban","False-urgency ban"]],
    ["Privacy",["HIPAA","WA My Health My Data","CO SB 26-189 (ADMT)","CA AB 3030 (GenAI)"]],
    ["Practice of Medicine",["Corporate Practice of Medicine","ADA accommodation hedge","Medicare / insurance hedge"]],
    ["Evidence — EBM Tier-1",["AAN","MDS","NINDS","RCT / guideline hierarchy"]],
    ["Quality & Access",["Google E-E-A-T / YMYL","CDC Clear Communication Index","WCAG 2.2 AAA","AMCP Patient Voice"]],
    ["Bioethics",["Belmont Report","Declaration of Helsinki 2024"]]
  ];
  var TIMELINE=[
    ["M1 · wk 3","Reviewer app live — ready for doctor onboarding","done"],
    ["M2 · wk 5–6","All review software ready","done"],
    ["M3 · wk 8","100 protocols doctor-approved","plain"],
    ["M4 · wk 8–9","Sign-off + legal certification — launch gate","plain"],
    ["M5 · wk 8–10","First patients go live","plain"],
    ["MDS Congress · Korea","Onboard movement-disorder specialists","target"]
  ];
  var ROADMAP=[
    ["250 reviewed protocols by launch","Scaling the library from 154 live protocols today to a 250-protocol, doctor-verified launch corpus.","Launch target"],
    ["Clinical-trial enablement","The first-party demand + physician-validation data asset a ClinicalTrials.gov cross-reference and patient-qualification model will run on.","Roadmap"],
    ["Advanced-therapy escalation","Advanced-therapy education with a compliant, patient-initiated path to live support — the member chooses the handoff.","Roadmap"],
    ["Durable owned patient channel","An installable app patients choose to put on their phone — a persistent, first-party channel that reaches them when spam-filtered cold calls can't.","Roadmap"]
  ];
  // Scale facts — measured from the repository itself.
  var SCALE=[
    ["736","commits in six months","git history, patient app repo"],
    ["20 + 8","patient/clinician screens + API routes","Next.js app tree"],
    ["~15,000","lines of TypeScript — a third of it tests — plus the Python content pipeline","app + test code"],
    ["360","automated test cases across 52 suites","vitest"],
    ["73","compliance checks · 12 domains · 63 deterministic rules + 10 semantic","MLR engine v5.0"],
    ["154","clinically structured protocols live today","library matrix"]
  ];
  var CLUSTER_PILLS=["Freezing & Falling","Medication","Reactions","Hallucinations","Personality","Sleep","Eating & Swallowing","Blood Pressure","Pain & Stiffness","Hospital & ER","Caregiver","Something Else?","Late Stage"];

  function sec(k,title,sub,body,extra){return '<section class="psec">'+'<div class="ph2"><span class="k">'+k+'</span><h2>'+title+'</h2>'+(extra||'')+'</div>'+(sub?'<div class="psub">'+sub+'</div>':'')+body+'</section>';}
  function protoRows(q){q=(q||'').toLowerCase();
    return PROTOCOLS.filter(function(p){return !q||p[0].toLowerCase().indexOf(q)>=0||p[1].toLowerCase().indexOf(q)>=0;}).map(function(p,i){
      return '<tr data-i="'+i+'"><td><b>'+esc(p[0])+'</b></td><td style="color:var(--muted);white-space:nowrap">'+esc(p[1])+'</td></tr>';
    }).join('');
  }
  function anatomyRowHTML(){
    var A=[["JSON-LD schema","MedicalWebPage + FAQPage structured data — built to be machine-cited"],
      ["Clinical accuracy badge","cross-referenced against current MDS, AAN and NINDS guidelines, dated"],
      ["BLUF + Quick Answer","a 45–55-word answer formula: symptom + mechanism + intervention + reason"],
      ["Sourced stat block","one hard number, one named authority"],
      ["Lived vignette","60–90 words of the real scenario, in the caregiver's voice"],
      ["3 strategy cards","each ends in 'What You Can Do Today' — free, immediate, specific"],
      ["Comparison table + next-steps checklist","options priced side-by-side, then concrete actions"],
      ["PubMed-verified citations","HTTP-validated at render time — a dead or hallucinated link cannot ship"],
      ["Disclaimer + 911 block","one canonical crisis footer the pipeline cannot duplicate or drop"]];
    return '<tr class="anatomy"><td colspan="2"><div style="font-size:11px;font-weight:700;letter-spacing:.5px;color:var(--teal-d);text-transform:uppercase;margin-bottom:8px">Anatomy of a protocol · Template v4.1.0 — 18 elements in a fixed render order; the LLM never writes the HTML</div>'+
      A.map(function(a,i){return '<div class="astep"><div class="n">'+(i+1)+'</div><div class="t"><b>'+esc(a[0])+'</b> — '+esc(a[1])+'</div></div>';}).join('')+'</div></td></tr>';}

  /* ----- the real protocol, rendered in the article template's own design tokens ----- */
  function protoDemoHTML(){
    return '<div class="artwrap"><div class="artdemo" id="artDemo">'+
      '<div class="abadge">✚ Reviewed for Clinical Accuracy — cross-referenced against current MDS, AAN, and NINDS clinical guidelines · April 2026</div>'+
      '<h3 class="atitle">Stuck in the Doorway: How to Break Parkinson’s Threshold Freezing</h3>'+
      '<div class="ameta"><b>Clinical entity:</b> Freezing of Gait at Visual Thresholds (Doorways, Elevators) · Cluster: Freezing &amp; Falling · 1,531 words · live at parkinsons.community</div>'+
      '<div class="abluf"><div class="ah">QUICK ANSWER</div>Freezing of gait at doorways occurs because the brain’s automatic walking program fails at perceived visual boundaries. The most effective intervention is a visual cue, like a line on the floor, which works by engaging the conscious motor system to bypass the block. Place a strip of brightly colored tape across the threshold and practice stepping over it.</div>'+
      '<div class="astat"><div class="al">A FRUSTRATING MOTOR BLOCK</div><div class="an">60%</div><div class="at">Up to 60% of people with Parkinson’s experience Freezing of Gait (FOG), with thresholds being a primary trigger. <i>(Source: The Michael J. Fox Foundation)</i></div></div>'+
      '<div class="artmore" id="artMore" style="display:none">'+
      '<div class="avig">“He walks down the hall just fine, but the moment he reaches the kitchen doorway, it’s like he’s hit an invisible wall. His feet are glued to the floor, his upper body pitches forward, and he just trembles there, stuck. I want to reach out, to pull him through, but I know that will just make him fall. All I can do is watch from the other side of the room, feeling utterly helpless as the doorway holds him hostage. It’s not just a doorway; it’s a cage.”</div>'+
      strat('01','How Can a Roll of Tape Unlock a Doorway?','Tonight, place a 2-inch wide strip of brightly colored painter’s tape across the floor of the most problematic doorway in your home. Practice the verbal cue: “Big step OVER the line.” This costs almost nothing and can be tested in minutes.')+
      strat('02','Can Rhythmic Sound Break a Physical Freeze?','Download a free metronome app on a smartphone. Set it to 110 BPM. Before approaching a doorway, start the metronome and try to match your steps to the beat. No phone? Simply count “one, two, one, two” aloud.')+
      strat('03','When Do You Need a Portable Cueing Device?','Use your smartphone to record a short video of a freezing episode (if it can be done safely). This objective evidence is invaluable when you discuss the need for an assistive device with a neurologist or physical therapist at the next appointment.')+
      '<div style="overflow-x:auto"><table class="atable"><tr><th>Approach</th><th>Cost</th><th>Time to Start</th></tr>'+
      '<tr><td>Painter’s tape (visual cue)</td><td>Under $10</td><td>Immediately</td></tr>'+
      '<tr><td>Auditory rhythm (metronome app)</td><td>Free</td><td>Immediately</td></tr>'+
      '<tr><td>Laser cane / walker</td><td>$200–$700+</td><td>2–4 Weeks (after PT/OT consult)</td></tr></table></div>'+
      '<div class="acite"><b>Clinical references (PubMed-verified):</b><br>Miller KJ, Suárez-Iglesias D, et al. Physiotherapy for freezing of gait in Parkinson’s disease: a systematic review and meta-analysis. Rev Neurol. 2020. PMID 32100276.<br>Ginis P, Nackaerts E, et al. Cueing for people with Parkinson’s disease with freezing of gait. Ann Phys Rehabil Med. 2018. PMID 28890341.</div>'+
      '<div class="a911"><b>When to Call 911:</b> If you or your loved one is experiencing a medical emergency — including difficulty breathing, loss of consciousness, a fall with injury, chest pain, or sudden confusion — call 911 immediately. This page is educational and does not replace emergency medical services.</div>'+
      '<div class="acta"><b>The Right Tools Can Unlock Every Doorway</b><span>Speak with a Care Navigator — Free</span><i>Educational support only. Never medical triage.</i></div>'+
      '</div>'+
      '<button class="artbtn" id="artBtn">Read the full protocol ▾</button>'+
      '</div><div class="artside">'+
      '<div class="feat"><div class="h">This is the depth — 154 times over</div><div class="b">Every protocol in the library carries this same structure: a 45–55-word answer a machine can cite, a sourced statistic, a caregiver-voiced vignette, three strategies that each end in a free action the reader can take <b>today</b>, priced options, PubMed-verified citations, and one canonical 911 footer.</div></div>'+
      '<div class="feat"><div class="h">The LLM never writes HTML</div><div class="b">The model produces structured JSON only; a 4.1.0 template owns every element, color and CTA position. Design cannot drift, disclaimers cannot be dropped, a dead link cannot ship — and references are drawn from verified PubMed records, never generated by the model.</div></div>'+
      '<div class="feat"><div class="h">Built to be the cited answer</div><div class="b">MedicalWebPage + FAQPage structured data on every page. Brands cited inside Google’s AI Overviews earn 35% more organic clicks than uncited competitors (Seer, 2025) — this library is engineered to be what gets cited when a caregiver asks at 2 a.m.</div></div>'+
      '</div></div>';
  }
  function strat(n,t,a){return '<div class="astrat"><div class="asn">'+n+'</div><div><div class="ast">'+esc(t)+'</div><div class="awycdt"><b>WHAT YOU CAN DO TODAY</b> '+esc(a)+'</div></div></div>';}

  /* ----- the reviewer console, faithfully mocked and interactive ----- */
  function reviewMockHTML(){
    return '<div class="revwrap"><div class="revmock" id="revMock">'+
      '<div class="rvbeta">BETA — sample data</div>'+
      '<div class="rvcrumb">Queue / Review</div>'+
      '<div class="rvtitle">Managing Freezing of Gait at Home</div>'+
      '<div class="rvmeta">v1 · 7–11 min · <b>$75 on approval</b></div>'+
      '<div class="rvcard"><div class="rvch">Compliance review</div><div class="rvpass">✓ 47 of 47 checks passed — all clear</div>'+
      '<div class="rvdom">Regulatory — FDA/FTC <span>8/8</span></div><div class="rvdom">Privacy — HIPAA <span>6/6</span></div><div class="rvdom">Medical accuracy <span>12/12</span></div><div class="rvdom">Evidence &amp; citation <span>7/7</span></div></div>'+
      '<div class="rvcard"><div class="rvch">Article under review (v1) <em>Tap any sentence to comment</em></div>'+
      '<div class="rvsec">NEED TO KNOW</div>'+
      '<div class="rvsent" data-s="0">Freezing of gait at doorways occurs because the brain’s automatic walking program fails at perceived visual boundaries.</div>'+
      '<div class="rvsec">STRATEGY 1: THE VISUAL CUE</div>'+
      '<div class="rvsent" data-s="1">Place a strip of brightly colored tape across the threshold and practice stepping over it.</div></div>'+
      '<div class="rvsheet" id="rvSheet" style="display:none"><div class="rvq" id="rvQuote"></div>'+
      '<div class="rvradio"><span class="on">Flag issue</span><span>Suggested edit</span></div>'+
      '<div class="rvlab">Your comment</div><div class="rvbox">What is the concern?</div>'+
      '<div class="rvbtns"><span class="ghostb" id="rvCancel">Cancel</span><span class="solidb" id="rvSubmit">Submit &amp; continue</span></div></div>'+
      '<div class="rvchanges" id="rvChanges" style="display:none"><div class="rvch">Your changes (1)</div><div class="rvchg"><span class="flagchip">Flag issue</span> re-checked → <b style="color:#2E7D46">PASS</b> <em>MLR re-verified the change automatically</em></div></div>'+
      '<div class="rvbar"><span class="rvappr" id="rvApprove">✓ Approve</span><span class="rvedit">✎ Approve w/ edits</span><span class="rvrev">⟳ Review</span></div>'+
      '<div class="rvdone" id="rvDone" style="display:none">'+
      '<div class="rvattr"><div class="rvah">ATTRIBUTION PREVIEW</div>✓ Reviewed &amp; approved by <b>Dr. [Name], MD</b><br>[Clinic, City] · 🔗 clinic-website.com — <i>live backlink to your practice</i></div>'+
      '<div class="rvsucc">Nicely done, Dr. [Name]. <b>+ $75</b><br><span>🏅 Gold reviewer standing · Review another (+$75) →</span></div>'+
      '<div class="rvreset" id="rvReset">↺ Reset the demo</div></div>'+
      '</div><div class="revside">'+
      '<div class="feat"><div class="h">Doctors polish — they don’t rewrite</div><div class="b">A review takes 7–11 minutes. The reviewer taps any sentence to flag an issue or propose wording; the MLR engine re-checks the change in the background and the doctor sees <b>re-checked → PASS</b> before approving.</div></div>'+
      '<div class="feat"><div class="h">Every approval builds the network</div><div class="b">$75 per review, a $50 photo bonus, and — the real draw — a public <b>MD-Verified</b> badge with the doctor’s name and a live backlink to their practice on every protocol they approve. Reviewers will earn standing (“Gold reviewer”), see monthly earnings, and be offered the next review the moment one closes: an engaged, credentialed physician network designed to compound.</div></div>'+
      '<div class="feat"><div class="h">Every correction becomes training data</div><div class="b">Each edit, comment and decision is designed to become labeled training data for the automated first-pass reviewer — the review loop gets cheaper and sharper with every doctor who joins.</div></div>'+
      '<div class="feat"><div class="h">Status — honest</div><div class="b">The entire review surface is <b>built end-to-end</b> and running in fixture beta. Credential verification, the public badge flip and payouts are gated behind final legal clearance — by design, not by accident.</div></div>'+
      '</div></div>';
  }
  function wireReviewMock(){
    var sheet=document.getElementById('rvSheet'),quote=document.getElementById('rvQuote'),chg=document.getElementById('rvChanges'),done=document.getElementById('rvDone');
    [].forEach.call(document.querySelectorAll('.rvsent'),function(s){s.onclick=function(){quote.textContent='“'+s.textContent+'”';sheet.style.display='block';s.classList.add('sel');};});
    var c=document.getElementById('rvCancel');if(c)c.onclick=function(){sheet.style.display='none';[].forEach.call(document.querySelectorAll('.rvsent.sel'),function(s){s.classList.remove('sel');});};
    var sub=document.getElementById('rvSubmit');if(sub)sub.onclick=function(){sheet.style.display='none';chg.style.display='block';[].forEach.call(document.querySelectorAll('.rvsent.sel'),function(s){s.classList.remove('sel');s.classList.add('flag');});};
    var ap=document.getElementById('rvApprove');if(ap)ap.onclick=function(){done.style.display='block';done.scrollIntoView({block:'nearest',behavior:'smooth'});};
    var rs=document.getElementById('rvReset');if(rs)rs.onclick=function(){done.style.display='none';chg.style.display='none';sheet.style.display='none';[].forEach.call(document.querySelectorAll('.rvsent'),function(s){s.classList.remove('sel','flag');});};
  }

  /* ----- the one compliance section: real code, live gates, real rules, the triumvirate ----- */
  var MLR_CODE="def compute_overall(self):\n    '''Apply multi-gate logic. ANY fail → OVERALL FAIL (score 0).'''\n    has_fail = any(g.status == GateStatus.FAIL\n                   for g in self.domain_gates.values())\n    has_warn = any(g.status == GateStatus.WARN\n                   for g in self.domain_gates.values())\n    if has_fail:\n        self.overall = GateStatus.FAIL\n        self.score = 0   # Binary. Commander: \"Complete Failure.\"\n        ...              # (violation aggregation trimmed for display)\n    elif has_warn:\n        self.overall = GateStatus.WARN\n        self.score = 100\n    else:\n        self.overall = GateStatus.PASS\n        self.score = 100";
  function mlrHTML(){
    var body='<div class="mdlrow">'+
      '<div class="mdl det"><div class="mh">Stage 1 · 63 deterministic rules</div><div class="mb">Pure-Python regex &amp; structural checks across domains D1–D11 — plus 10 semantic points in D12 scored by Gemini 2.5 Flash. No model can argue with a gate.</div></div>'+
      '<div class="mdl claude"><div class="mh">Claude Opus · “The Lawyer”</div><div class="mb">A grumpy, encyclopedic, maximally-strict prosecutor that authors the legal &amp; medical findings and drafts the compliant fix. This is the Claude-powered legal review.</div></div>'+
      '<div class="mdl gemini"><div class="mh">Gemini · “The CMO”</div><div class="mb">Adversarially challenges the Lawyer so risk-aversion never guts the patient’s lifeline — it can rewrite the fix or rubber-stamp it. Dual-model, on the record.</div></div></div>'+
      '<div class="eqwrap"><div class="eq"><div style="font-size:10.5px;letter-spacing:.6px;color:#7d92ab;font-family:Arial,sans-serif;font-weight:700;margin-bottom:10px">THE ACTUAL SHIPPING CODE, ABRIDGED — mlr_scoring_engine.py (1,651 lines)</div><pre class="codeblk">'+esc(MLR_CODE)+'</pre>'+
      '<div class="cond" style="margin-top:14px">In notation: <code>score = 100 · ∏ᵢ₌₁¹² 𝟙[Gᵢ ≠ FAIL] ∈ {0, 100}</code> — twelve independent gates, and one hard failure in any of them zeroes the entire article. There is no weighted average to argue with and no partial credit to hide behind.</div></div>'+
      '<div class="gates"><div style="font-size:11.5px;font-weight:700;color:var(--slate);margin-bottom:8px">The 12 gates — click any gate to fail it and watch the verdict</div><div class="gaterow" id="gateRow">'+
      DOMAINS.map(function(d,i){return '<div class="glight" data-g="'+i+'" title="'+esc(d[1])+'"><div class="g"></div><div class="id">'+d[0]+'</div><div class="nm">'+esc(d[1].split(' ')[0])+'</div></div>';}).join('')+
      '</div><div class="gateread pass" id="gateRead">12 / 12 gates green → score 100 · <b>PUBLISH</b></div>'+
      '<div class="conout"><div class="coh">what a failing audit actually prints</div>D5_medication: Medication Safety&nbsp;&nbsp;&nbsp;<span class="cofail">[FAIL]</span><br>&nbsp;&nbsp;[5.9]&nbsp;&nbsp;Specific dosing “25 mg” without physician hedge<br>&nbsp;&nbsp;[5.13] DDI: Serotonin Syndrome — both drug classes mentioned without safety warning</div></div></div>';
    body+='<div class="rulegrid">'+MLR_RULES.map(function(r){return '<div class="rulecard"><span class="rid">'+r[0]+'</span><span class="rsev'+(r[1]==='ADVISORY'?' adv':'')+'">'+r[1]+'</span><div class="rtx">'+esc(r[2])+'</div></div>';}).join('')+'</div>';
    body+='<div class="trirow">'+
      '<div class="tri att"><div class="th"><i style="background:#B74919"></i>Compliance Attorney</div><div class="tb">“Binding veto over any language that creates institutional liability, promises a medical guarantee, or crosses into the unauthorized practice of medicine.” Owns the attribution firewall, brand compliance, and privacy law (HIPAA, WA MHMDA, CO ADMT, CA GenAI disclosure).</div></div>'+
      '<div class="tri mds"><div class="th"><i style="background:var(--cyan)"></i>Movement Disorders Specialist</div><div class="tb">“Binding veto over clinical inaccuracies, low-tier evidence masquerading as fact, and advice that endangers vulnerable subgroups.” Knows that SSRIs + MAO-Bs mean serotonin syndrome, and that an akinetic crisis is a 911 event — the engine enforces both.</div></div>'+
      '<div class="tri cmo"><div class="th"><i style="background:#6ba52f"></i>Chief Marketing Officer</div><div class="tb">Holds the <b>Anti-Sanitization Veto</b>: “deletion is a failure of editing.” If legal and medical caution gut a page to useless platitudes, the CMO blocks the deletion and forces a Compliant Compromise — every section must keep a specific, free, 24-hour action the patient can take.</div></div></div>';
    body+='<div style="margin-top:16px"><div style="font-size:12px;font-weight:700;color:var(--slate);margin-bottom:10px">The areas of law the engine answers to</div><div class="lawgrid">'+
      LAW.map(function(l){return '<div class="lawcol"><h4>'+esc(l[0])+'</h4>'+l[1].map(function(x){return '<span class="chip">'+esc(x)+'</span>';}).join('')+'</div>';}).join('')+'</div></div>';
    body+='<div class="note">The interactive review console runs on Cloud Run: per-finding approve / modify / dispute, a dual-model re-audit (Claude ⇄ Gemini, ~5–8 minutes), a worst-first remediation queue, and a compliance trend chart over the whole library. This is one engine, applied everywhere — the same 73 checks re-verify every doctor edit in the review loop above.</div>';
    return body;
  }
  function wireGates(){
    var row=document.getElementById('gateRow'),read=document.getElementById('gateRead');
    if(!row)return;
    row.onclick=function(e){var g=e.target.closest('.glight');if(!g)return;g.classList.toggle('fail');
      var fails=[].map.call(row.querySelectorAll('.glight.fail'),function(x){return DOMAINS[+x.getAttribute('data-g')][0];});
      if(fails.length){read.className='gateread fail';read.innerHTML=fails.join(', ')+' failed → score 0 · <b>COMPLETE FAILURE</b> — no partial credit';}
      else{read.className='gateread pass';read.innerHTML='12 / 12 gates green → score 100 · <b>PUBLISH</b>';}};
  }

  /* ----- the product tour: faithful screen replicas, alternating big-tech layout ----- */
  function pph(){return '<div class="pph"><span class="pham"><i></i><i></i><i></i></span>'+vpLogo(20,12.5)+'<span class="ppsr"><i></i></span></div>';}
  function pshell(inner,noHdr){return '<div class="pshell">'+(noHdr?'':pph())+'<div class="pbody">'+inner+'</div></div>';}
  function scrLanding(){
    return pshell('<div class="scr-land"><span class="mbpill">MEDICALLY BASED</span>'+
      '<div class="lh">You’re not taking on Parkinson’s alone.</div>'+
      '<div class="ls">Clear answers built around <i>your</i> Parkinson’s — and a real care team one tap away. Free during the beta.</div>'+
      '<div class="goldbtn">Get started — it’s free</div>'+
      '<div class="lbeta">AI vs PD is an early beta. It is not medical advice or an emergency service — in an emergency, call 911.</div></div>');
  }
  function scrTriage(){
    return pshell('<div class="scr-strip">154 care protocols · Clinician verification in progress</div>'+
      '<div class="scr-pad"><div class="th1">What are you dealing with today?</div>'+
      '<div class="tsearch"><span class="tmag">⌕</span><span class="tph">Describe what’s happening...</span><span class="tmic">🎙</span></div>'+
      '<div class="tpills"><span>🛑 Freezing &amp; Falling</span><span>💊 Medication</span><span>⚠️ Reactions</span><span>🌀 Hallucin…</span></div>'+
      '<div class="tfilter"><b>154 protocols</b><span>Filter ▾</span></div>'+
      '<div class="tcard"><div class="tbrow"><span class="tmds">🛡 Reviewed by MDS</span><span class="thelp">★ Found helpful</span></div>'+
      '<div class="tct">Freezing of Gait at Visual Thresholds (Doorways, Elevators)</div>'+
      '<div class="tcs">Why the walking program fails at perceived boundaries — and the visual cue that bypasses the block.</div>'+
      '<div class="tcb"><span class="tclu">🛑 Freezing &amp; Falling</span><span class="tchev">›</span></div></div></div>');
  }
  function scrAsk(){
    return pshell('<div class="scr-pad"><div class="th1">Ask</div>'+
      '<div class="tintro">Ask about your own records and our reviewed Parkinson’s library. Answers come only from those — always with a source.</div>'+
      '<div class="tnote">Not medical advice. In an emergency, call 911. Follow the instructions of your health care provider.</div>'+
      '<div class="bub u">Dad freezes in every doorway. What can we do right now?</div>'+
      '<div class="bub a">A visual cue works best for threshold freezing: place a strip of brightly colored tape across the doorway floor and practice “Big step OVER the line.”<span class="cite">Source: /guide/freezing-of-gait-at-visual-thresholds</span></div>'+
      '<div class="tinput"><span>Ask a question…</span><b>Ask</b></div></div>');
  }
  function scrRecords(){
    return pshell('<div class="scr-pad"><div class="th1">My Records</div>'+
      '<div class="tintro">Your health records are your private ground truth — only you and your care team can see them. The assistant answers from these records and our reviewed library.</div>'+
      '<div class="tdash"><b>Add a record</b><span>Take a photo or choose a file (image or PDF)</span></div>'+
      '<div class="th2">Your records</div>'+
      '<div class="trec">neurology-visit-notes.pdf <span class="tread">text read</span></div>'+
      '<div class="trec">medication-list-2026.jpg <span class="tread">text read</span></div></div>');
  }
  function scrSupport(){
    return pshell('<div class="scr-pad"><div class="th1">Get Support</div>'+
      '<div class="tintro">Talk with a real person — a Care Advocate who understands Parkinson’s. Not a chatbot, not a recording.</div>'+
      '<div class="tcta"><div class="teb">FREE MEMBER BENEFIT</div><div class="tch">You don’t have to figure this out alone.</div>'+
      '<div class="tinner"><span class="tav">CA</span><div><b>Care Advocate</b><span>Free · Educational support only</span><span>Available Mon–Fri 9am–5pm ET</span></div></div>'+
      '<div class="tghost">Speak with a Care Advocate — Free</div></div>'+
      '<div class="tfoot">Educational support only. Never medical triage.</div></div>');
  }
  function scrDoctor(){
    return pshell('<div class="scr-pad"><div class="dbeta">BETA — sample data</div>'+
      '<div class="drow"><span class="dav">DR</span><div><b>Reviewer console</b><span>Dr. [Name] — [Clinic, City]</span></div></div>'+
      '<div class="dearn"><span class="de1">This month</span><div class="de2"><b>14</b> reviews &nbsp;·&nbsp; <b>$1,050</b> earned</div>'+
      '<div class="de3"><span class="dgold">🏅 Gold reviewer</span><span class="dbet">beta — no real payout</span></div></div>'+
      '<div class="th2" style="margin-top:10px">Your queue</div>'+
      '<div class="dq"><span class="dd y"></span><div><b>Managing Freezing of Gait at Home</b><span>Pending review · v1</span></div><span class="dt">7–11 min</span><span class="dp">$75</span></div>'+
      '<div class="dq"><span class="dd n"></span><div><b>Levodopa &amp; Protein Timing</b><span>Revised · 2 changes · v2</span></div><span class="dt">3–5 min</span><span class="dp">$75</span></div></div>',true);
  }
  var TOUR=[
    {scr:scrLanding, eb:'Screen · The Front Door', h:'A destination, not an ad',
     p:'Every rented impression disappears the moment the budget stops. This page doesn’t. It converts community attention into identified, signed-in members — an audience the program owns.',
     b:['A first-party front door with zero marginal media cost','Free during beta — no acquisition friction','Honest from the first screen: beta status and 911 guidance up front']},
    {scr:scrTriage, eb:'Screen · Triage', h:'Organized by the crisis, not the keyword',
     p:'The home screen asks one question and answers it in two taps. The library is arranged into 13 crisis clusters — the situations families actually face — and every card carries its clinical provenance.',
     b:['13 crisis clusters, from Freezing &amp; Falling to Late Stage','154 protocols indexed under clinical entities','“Reviewed by MDS” provenance on every card']},
    {scr:scrAsk, eb:'Screen · Ask', h:'Answers with receipts',
     p:'The assistant is grounded, not creative: it may answer only from the member’s own records and the reviewed library — and it must cite which, inline, every time. Crisis language never reaches the model at all.',
     b:['Two grounding sources — nothing else','A source citation on every answer','911/988 crisis intercept fires before the model']},
    {scr:scrRecords, eb:'Screen · My Records', h:'The member’s own ground truth',
     p:'Members photograph their records into a private folder only they and their care team can see. The assistant reads from it — so answers are about <i>their</i> Parkinson’s, not Parkinson’s in general.',
     b:['Owner-scoped records, server-verified on every request','Documents read via in-BAA OCR — switches on after compliance sign-off (see Under the Hood)','Record data stays inside the Google BAA boundary by architecture']}
  ];
  function tourHTML(){
    return '<div class="tour">'+TOUR.map(function(t,i){
      return '<div class="fb'+(i%2?' rev':'')+'"><div class="fbphone">'+t.scr()+'</div>'+
        '<div class="fbcopy"><div class="fbeb">'+esc(t.eb)+'</div><h3>'+esc(t.h)+'</h3><p>'+t.p+'</p>'+
        '<ul class="fbchk">'+t.b.map(function(x){return '<li>'+x+'</li>';}).join('')+'</ul></div></div>';
    }).join('')+'</div>';
  }

  /* ===== 01 · THE PROBLEM (visual) ===== */
  var DECLINE=[
    ['Search','−61%','organic click-through when an AI answer appears — 60% of searches now end with no click at all','Seer 2025 · Bain 2025',[72,60,45,31,18]],
    ['Advertising','33%','of the audience blocks display ads before a single impression is even measured','Backlinko / Statista 2025',[66,54,42,32,22]],
    ['The Phone','80%','of calls from an unrecognized number now go unanswered','Hiya · State of the Call 2025',[62,48,36,25,14]]
  ];
  function declBars(a){return '<div class="declbars">'+a.map(function(h,i){return '<span class="'+(i===a.length-1?'last':'')+'" style="height:'+h+'%"></span>';}).join('')+'</div>';}
  function problemHTML(){
    var cards=DECLINE.map(function(d){return '<div class="declcard"><div class="dch">'+esc(d[0])+'</div>'+declBars(d[4])+'<div class="decln">'+d[1]+'</div><div class="decll">'+esc(d[2])+'</div><div class="decls">'+esc(d[3])+'</div></div>';}).join('');
    return '<div class="thlead"><p>Every channel this industry rents is getting worse at once — and it is not a dip. Search answers the question before it refers the visitor. A third of the audience blocks display before anyone measures attention. And the phone, the backbone of patient outreach, goes unanswered the moment the number is unfamiliar.</p></div>'+
      '<div class="declrow">'+cards+'</div>'+
      '<div class="accel"><b>AI didn’t start this decline — it is finishing it.</b> As assistants answer more questions directly, rented reach keeps shrinking. The one move this shift <i>rewards</i> is being the authoritative, first-party source the AI cites and the patient returns to.</div>';
  }

  /* ===== 02 · THE SOLUTION ===== */
  /* Wireframe of the app login screen (replaces the live iframe embed) */
  function wireLogin(){
    return '<div class="wirescreen">'+
      '<div class="wiretag">WIREFRAME · APP LOGIN</div>'+
      '<div class="wirebadge">'+vpBadge(46)+'</div>'+
      '<div class="wiretitle">'+vpWord(15)+'</div>'+
      '<div class="wiresub">Sign in to try the beta</div>'+
      '<div class="wirerow"><span class="wireic"></span>Continue with Apple</div>'+
      '<div class="wirerow"><span class="wireic"></span>Continue with Google</div>'+
      '<div class="wirerow"><span class="wireic"></span>Continue with email</div>'+
      '<div class="wireor"><span>then tap to enter</span></div>'+
      '<a class="wirecta" href="'+APP_URL+'" target="_blank" rel="noopener">▶&nbsp;&nbsp;Trial Beta</a>'+
      '<div class="wirenote"><b>Note:</b> Beta trial. Any <b>@Supernus</b> handle can sign in — Apple, Google, or email — and land straight in.</div>'+
      '</div>';
  }
  function appPromoHTML(){
    var chatfacts='<div class="featrow">'+
      '<div class="feat"><div class="h">Grounded, or it won’t answer</div><div class="b">The assistant answers <b>only</b> from two sources — the member’s own records and the reviewed library — and must cite which, inline, every time. No grounding, no answer.</div></div>'+
      '<div class="feat"><div class="h">Crisis is intercepted before the AI</div><div class="b">Eleven crisis patterns short-circuit <b>before the model is called</b> and return a fixed 911/988 response written by humans. Fail-safe by design.</div></div>'+
      '<div class="feat"><div class="h">Inside the health-data walls</div><div class="b">Claude runs on Google Vertex — patient data stays inside the BAA boundary by architecture. Passwordless sign-in, server-verified at every boundary.</div></div>'+
      '<div class="feat"><div class="h">Built to be the cited answer</div><div class="b">Structured MedicalWebPage data on every page. Brands cited in Google’s AI Overviews earn 35% more organic clicks than the uncited (Seer, 2025).</div></div></div>';
    return '<div class="appwrap"><div class="phone"><div class="appchrome">'+vpLogo(24,15)+'<span class="awlive">BETA</span></div>'+
      wireLogin()+'</div>'+
      '<div class="applead"><div style="font-size:13.5px;color:var(--ink);line-height:1.6">This is the app’s <b>login screen</b> — tap <b>Trial Beta</b> to open the live beta in a new window. Any <b>@Supernus</b> handle can sign in with Apple, Google, or email and land straight in to explore the member experience. &nbsp;<a class="btn ghost" style="padding:7px 12px;font-size:12px" href="'+APP_URL+'" target="_blank" rel="noopener">Open the beta ↗</a></div>'+chatfacts+'</div></div>';
  }
  function solutionHTML(){
    var twoside='<div class="twoside">'+
      '<div class="tscard pt"><div class="tsh">For Patients</div><div class="tst">An AI companion for Parkinson’s</div><div class="tsb">A plain-language app that answers a caregiver’s 2 a.m. question — grounded only in reviewed protocols and the member’s own records, always with a source, with a real person one tap away.</div></div>'+
      '<div class="tsplus">+</div>'+
      '<div class="tscard dr"><div class="tsh">For Doctors</div><div class="tst">A protocol-review network</div><div class="tsb">A reviewer console that turns movement-disorder neurologists into named, compensated, returning contributors — deepening the clinical authority behind every answer.</div></div></div>';
    var chatfacts='<div class="featrow">'+
      '<div class="feat"><div class="h">Grounded, or it won’t answer</div><div class="b">The assistant answers <b>only</b> from two sources — the member’s own records and the reviewed library — and must cite which, inline, every time. No grounding, no answer.</div></div>'+
      '<div class="feat"><div class="h">Crisis is intercepted before the AI</div><div class="b">Eleven crisis patterns short-circuit <b>before the model is called</b> and return a fixed 911/988 response written by humans. Fail-safe by design.</div></div>'+
      '<div class="feat"><div class="h">Inside the health-data walls</div><div class="b">Claude runs on Google Vertex — patient data stays inside the BAA boundary by architecture. Passwordless sign-in, server-verified at every boundary.</div></div>'+
      '<div class="feat"><div class="h">Built to be the cited answer</div><div class="b">Structured MedicalWebPage data on every page. Brands cited in Google’s AI Overviews earn 35% more organic clicks than the uncited (Seer, 2025).</div></div></div>';
    var embed='<div class="appwrap"><div class="phone"><div class="appchrome">'+vpLogo(24,15)+'<span class="awlive">BETA</span></div>'+
      wireLogin()+'</div>'+
      '<div class="applead"><div style="font-size:13.5px;color:var(--ink);line-height:1.6">This is the app’s <b>login screen</b> — tap <b>Trial Beta</b> to open the live beta in a new window. Any <b>@Supernus</b> handle can sign in with Apple, Google, or email and land straight in to explore the member experience. &nbsp;<a class="btn ghost" style="padding:7px 12px;font-size:12px" href="'+APP_URL+'" target="_blank" rel="noopener">Open the beta ↗</a></div>'+chatfacts+'</div></div>';
    return '<p class="soltop">The answer is not another campaign — it is an <b>owned, AI-native platform</b> for the Parkinson’s community: one destination that engages the two audiences that matter, and that the AI wave carries instead of buries.</p>'+
      twoside+
      '<div class="thsub">Try it — open the beta from the login below</div>'+embed+
      '<div class="thsub">The audience it serves — large, digital, and badly served</div>'+
      '<div class="thgrid">'+THESIS2.map(function(t){return '<div class="thstat t2"><div class="n">'+t[0]+'</div><div class="l">'+esc(t[1])+'</div><div class="s">'+esc(t[2])+'</div></div>';}).join('')+'</div>';
  }

  /* ===== 03 · THE CALL BUTTON (centerpiece → live advocates) ===== */
  function callCenterHTML(){
    var flow='<div class="ccflow">'+
      '<div class="ccnode"><div class="cci">1</div><div class="cct">In-app tap</div><div class="ccd">A member taps <b>Speak with a Care Advocate</b> — patient-initiated, never a cold call.</div></div>'+
      '<div class="ccar">→</div>'+
      '<div class="ccnode"><div class="cci">2</div><div class="cct">Verified call</div><div class="ccd">The CRM click-to-dial logs a <b>server-authoritative</b> call event the instant it happens.</div></div>'+
      '<div class="ccar">→</div>'+
      '<div class="ccnode"><div class="cci">3</div><div class="cct">Guided discussion</div><div class="ccd">The clinical guide runs; a form <b>cannot be saved without that verified call</b> — “no call, no form.”</div></div>'+
      '<div class="ccar">→</div>'+
      '<div class="ccnode last"><div class="cci">4</div><div class="cct">Reported discussion</div><div class="ccd">A <b>Connected — Guide completed</b> disposition — the branded ONAPGO® discussion Supernus is reported on.</div></div>'+
      '</div>';
    var center='<div class="ccstage"><div class="ccphone">'+scrSupport()+'</div>'+
      '<div class="cccopy"><div class="cceb">THE CENTERPIECE</div>'+
      '<h3>The app doesn’t replace the advocates — it <span class="cchi">feeds</span> them.</h3>'+
      '<p>The whole platform points at one button. When an engaged member is ready for a person, one tap hands them to a live Care Advocate — and every connection is <b>verified before it can ever count</b>. The app is the top of the funnel; the advocate call is the deliverable this program is measured on.</p>'+
      '<div class="ccbtn"><svg viewBox="0 0 24 24" width="15" height="15" fill="#202C59" style="vertical-align:-2px;margin-right:8px"><path d="M6.6 10.8a15.5 15.5 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.4c.6 0 1 .4 1 1 0 1.2.2 2.5.6 3.6.1.4 0 .8-.3 1z"/></svg>Speak with a Care Advocate — Free</div>'+
      '<div class="ccsub">Real person · educational support only · never medical triage · honest-degrades to “Request a call” when no line is live</div></div></div>';
    return center+flow+
      '<div class="gate"><b>Every connection is verified.</b> The discussion form gates on a server-logged call event — the anti-fabrication source of truth — so a form can’t exist without a real call. Suspicious speed trips fabrication flags (handle &lt; <b>20s</b>, connected &lt; <b>60s</b> after dial), and only <i>Connected — Guide completed</i> dispositions are tallied as the Initial / Pre-HCP / Post-HCP discussions in the July report.</div>';
  }

  /* ===== 05 · under-the-hood extras: record reader + clinical governance ===== */
  function recordReaderHTML(){
    return '<div class="uhcol"><div class="uhh">Medical Record Reader</div>'+
      '<div class="uhb">Members photograph or upload a record — a photo or a PDF — and the app <b>reads the text with OCR</b> (Google Cloud Vision, inside the Google BAA) so the assistant can answer grounded in <i>that member’s</i> own records, not Parkinson’s in the abstract. Built and unit-tested; it switches on after the compliance/legal sign-off (gated dark today, by design). Fail-closed: if extraction can’t run, the record still saves and the assistant simply doesn’t use it.</div>'+
      '<div class="uhtags"><span>Google Cloud Vision OCR</span><span>in-BAA</span><span>owner-scoped</span><span>gated — pending legal</span></div></div>';
  }
  function clinGovHTML(){
    return '<div class="uhcol"><div class="uhh">Clinical Governance</div>'+
      '<div class="uhb">Guidance is organized into <b>13 clinical crisis clusters</b>, every claim is cited to the field’s top authorities — <b>MDS, AAN, NINDS, MJFF, APTA</b> — and content is vetted by an AI review board modeled on a <b>movement-disorder specialist, a compliance attorney, and a CMO</b> before a patient sees it. On top of that sits the real physician-review network (Section 04), where named neurologists sign off on protocols. The assistant itself <b>never diagnoses, doses, or triages — by design and by rule.</b></div>'+
      '<div class="uhtags"><span>13 crisis clusters</span><span>MDS · AAN · NINDS · MJFF · APTA</span><span>MDS-persona review</span><span>physician sign-off network</span></div></div>';
  }

  function renderPlatform(){
    var html='';
    // 01 · The Problem
    html+=sec('01 · The Problem','The Channels You Rent Are Failing — All at Once','Paid reach isn’t dipping; it’s structurally declining on every front — and AI is the accelerant.',problemHTML());
    // 02 · The Solution
    html+=sec('02 · The Solution','An AI Platform That Engages Both Patients and Doctors','Not a campaign — a destination. Owned, first-party, and built for the one thing the AI shift rewards.',solutionHTML(),'<span class="betachip">LIVE BETA</span>');
    // 03 · The Call Button — centerpiece
    html+=sec('03 · The Connection','One Tap From the App to a Live Advocate','The centerpiece — the button that turns an engaged member into a verified, reported ONAPGO® discussion.',callCenterHTML(),'<span class="liveflag"><span class="d"></span>VERIFIED</span>');
    // 04 · How it works
    var how='<div class="howhalf"><div class="howlab">AI UI for Patients</div><div class="howsub">the product a caregiver actually touches — four production screens</div></div>'+tourHTML()+
      '<div class="howhalf" style="margin-top:38px"><div class="howlab">Protocol Review for MDS Neuros</div><div class="howsub">the working console a movement-disorder neurologist uses — try it: tap a sentence, flag it, approve</div></div>'+reviewMockHTML();
    html+=sec('04 · How It Works','Two Products, One Platform','A quick pass through both sides — the AI interface patients use, and the protocol-review console neurologists use.',how,'<span class="betachip">FIXTURE BETA</span>');
    // 05 · Under the hood
    var dbbody='<div class="clusrow">'+CLUSTERS.map(function(c){return '<span class="clchip">'+esc(c[0])+' <b>'+c[1]+'</b></span>';}).join('')+'</div>'+
      '<div class="dbbar"><input class="dbsearch" id="dbSearch" placeholder="Search the clinical library — try DAWS, camptocormia, Capgras, silent aspiration…">'+
      '<div class="meter"><div class="lab"><b>'+PROTO_LIVE+'</b> reviewed protocols live today · building to <b>'+PROTO_TARGET+'+</b> for launch</div><div class="mtr"><div class="fill" style="width:'+Math.round(PROTO_LIVE/PROTO_TARGET*100)+'%"></div><div class="goal" style="left:100%"></div></div></div></div>'+
      '<div class="dbscroll"><table class="db"><thead><tr><th>Clinical Protocol</th><th>Cluster</th></tr></thead><tbody id="dbBody">'+protoRows('')+'</tbody></table></div>'+
      '<div class="note">A sample of the library’s clinical index — each protocol is titled the way a neurologist reads it (verbatim from the record’s clinical-entity field), and each publishes with a plain-language patient page on top. Click any row to open the protocol framework. Clinically indexed for physicians and AI, plain-spoken for families.</div>';
    var build='<div class="scalegrid">'+SCALE.map(function(s){return '<div class="scstat"><div class="n">'+esc(s[0])+'</div><div class="l">'+esc(s[1])+'</div><div class="s">'+esc(s[2])+'</div></div>';}).join('')+'</div>';
    var uh='<div class="thsub">The clinical library</div>'+dbbody+
      '<div class="thsub">One protocol, all the way down</div>'+protoDemoHTML()+
      '<div class="thsub">Reading the member’s own records · governing the medicine</div>'+
      '<div class="uhrow">'+recordReaderHTML()+clinGovHTML()+'</div>'+
      '<div class="thsub">Measured from the repository</div>'+build;
    html+=sec('05 · Under the Hood','250+ Protocols, a Record Reader, and Clinical Governance','The depth behind the screens — the library, how a single protocol is built, how a member’s records are read, and how the medicine is governed.',uh);
    // 06 · Compliance
    html+=sec('06 · Compliance','Claude-Powered Legal Review — a 12-Gate MLR Process','Every protocol, every AI answer, every doctor edit clears the same automated MLR gate before a patient sees it: 12 binary gates with no gray zone, 73 checks, and a Claude ⇄ Gemini legal review on top.',mlrHTML());
    // Runway closer
    var tl='<div class="timeline">'+TIMELINE.map(function(m){return '<div class="mnode '+m[2]+'"><div class="dotm"></div><div class="mw">'+esc(m[0])+'</div><div class="ml">'+(m[2]==='target'?'<a href="'+MDS_URL+'" target="_blank" rel="noopener" style="color:var(--accent-ink);text-decoration:underline">'+esc(m[1])+' ↗</a>':esc(m[1]))+'</div></div>';}).join('')+'</div>';
    var rm='<div class="rmgrid">'+ROADMAP.map(function(r){return '<div class="rmcard"><div class="rt">'+esc(r[0])+'</div><div class="rd">'+esc(r[1])+'</div><span class="rw">'+esc(r[2])+'</span></div>';}).join('')+'</div>';
    html+=sec('Next · The Runway','From Beta to Launch','What is built is live above. What remains is sequencing — doctors, legal clearance, launch.',tl+rm);
    html+='<div class="srcline">Sources: Seer Interactive (Sep 2025) · Bain &amp; Company (2025) · Hiya State of the Call (2025) · ixlayer / Digital Health Coalition via Fierce Pharma (2025) · Backlinko / Statista ad-block usage (2025) · Parkinson’s Foundation (2024) · Frontiers in Neurology telehealth survey (2022) · MyHealthTeam (2025) · PD information scoping review (PMC, 2024) · Sample protocol content cites The Michael J. Fox Foundation and PubMed IDs 32100276, 28890341.</div>';

    document.getElementById('view').innerHTML='<div style="margin-top:6px"></div>'+html;
    var s=document.getElementById('dbSearch');
    if(s)s.oninput=function(){document.getElementById('dbBody').innerHTML=protoRows(s.value);};
    var body=document.getElementById('dbBody');
    if(body)body.onclick=function(e){var tr=e.target.closest('tr[data-i]');if(!tr)return;
      var nx=tr.nextElementSibling;
      if(nx&&nx.classList.contains('anatomy')){nx.remove();tr.classList.remove('open');return;}
      [].forEach.call(body.querySelectorAll('.anatomy'),function(a){a.remove();});
      [].forEach.call(body.querySelectorAll('tr.open'),function(t){t.classList.remove('open');});
      tr.classList.add('open');tr.insertAdjacentHTML('afterend',anatomyRowHTML());
    };
    var ab=document.getElementById('artBtn');
    if(ab)ab.onclick=function(){var m=document.getElementById('artMore');var open=m.style.display==='block';m.style.display=open?'none':'block';ab.textContent=open?'Read the full protocol ▾':'Collapse the protocol ▴';};
    wireReviewMock();
    wireGates();
    // Restrained scroll-reveal on the tour blocks + sections (skipped under prefers-reduced-motion).
    try{
      if(!window.matchMedia('(prefers-reduced-motion: reduce)').matches && 'IntersectionObserver' in window){
        var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('vis');io.unobserve(e.target);}});},{threshold:.12});
        [].forEach.call(document.querySelectorAll('.fb'),function(el){el.classList.add('rvl');io.observe(el);});
      }
    }catch(e){}
    window.scrollTo({top:0,behavior:'smooth'});
  }


  /* ---------- data + polling ---------- */
  function fetchMetrics(){return fetch('/api/onapgo/metrics'+(location.search||'')).then(function(r){if(!r.ok)throw 0;return r.json();}).catch(function(){return METRICS_FALLBACK;});}
  function fetchLive(){return fetch('/api/onapgo/live'+(location.search||'')).then(function(r){if(!r.ok)throw 0;return r.json();}).catch(function(){return LIVE_FALLBACK;});}
  function fetchQual(ym){var q=(location.search?location.search+'&':'?')+'ym='+ym;return fetch('/api/onapgo/qual'+q).then(function(r){if(!r.ok)throw 0;return r.json();}).catch(function(){return QUAL_FALLBACK;});}
  function fetchAdv(){return fetch('/api/onapgo/advocates'+(location.search||'')).then(function(r){if(!r.ok)throw 0;return r.json();}).catch(function(){return ADV_FALLBACK;});}
  function fetchHcplog(ym){var q=(location.search?location.search+'&':'?')+'ym='+ym;return fetch('/api/onapgo/hcplog'+q).then(function(r){if(!r.ok)throw 0;return r.json();}).catch(function(){return HCPLOG_FALLBACK;});}
  function fetchPerf(){return fetch('/api/onapgo/perf'+(location.search||'')).then(function(r){if(!r.ok)throw 0;return r.json();}).catch(function(){return PERF_FALLBACK;});}
  function setupTimer(){if(timer)clearInterval(timer);timer=setInterval(function(){
    if(MODE==='july'){Promise.all([fetchLive(),fetchAdv(),fetchMetrics()]).then(function(res){var d=res[0];ADV=res[1];META=res[2];var changed=!LIVE||d.total!==LIVE.total;var upToday=(PREV_TODAY!=null&&d.today&&d.today.total>PREV_TODAY);LIVE=d;PREV_TODAY=(d.today?d.today.total:PREV_TODAY);if(MODE!=='july')return;
      var open=document.querySelector('.evbody2[style*="block"]');
      if(open){var f={mtdNum:d.total,cI:d.stages.initial,cP:d.stages.pre_hcp,cO:d.stages.post_hcp,todayNum:(d.today&&d.today.total)||0};for(var k in f){var el=document.getElementById(k);if(el)el.textContent=f[k];}}
      else{renderJuly();}
      renderHero();
      if(changed){var e=document.getElementById('mtdNum');if(e)e.classList.add('flash');}
      if(upToday){var t=document.getElementById('todayNum');if(t)t.classList.add('flash');confetti();}
    });}
  },25000);}

  Promise.all([fetchMetrics(),fetchLive(),fetchAdv()]).then(function(res){META=res[0];LIVE=res[1];ADV=res[2];MODE='july';renderShell();});
})();
</script>
"""


def _serve_report_or_gate(req: Request):
    try:
        _gate(req)
        return HTMLResponse(DASHBOARD_HTML)
    except HTTPException:
        return HTMLResponse(PW_HTML.replace('<!--ERR-->', ''))


@router.get('/go', response_class=HTMLResponse)
def report_go(req: Request):
    return _serve_report_or_gate(req)


@router.post('/login')
async def report_login(req: Request):
    from urllib.parse import parse_qs
    body = (await req.body()).decode('utf-8', 'ignore')
    pw = (parse_qs(body).get('password') or [''])[0]
    if pw == REPORT_PW:
        r = RedirectResponse('/go', status_code=303)
        r.set_cookie(COOKIE_NAME, _cookie_val(), max_age=2592000, httponly=True, secure=(not DEV), samesite='lax', path='/')
        return r
    return HTMLResponse(PW_HTML.replace('<!--ERR-->', '<div class="err">Incorrect password — please try again.</div>'), status_code=401)


# When this container runs as the PUBLIC report service, refuse every path that isn't the report so the
# unauthenticated surface can never touch a CRM endpoint (defence-in-depth; who() would 401 them anyway).
if PUBLIC_REPORT:
    from main import app as _app
    _ALLOW = ('/go', '/login', '/api/onapgo/', '/onapgo/asset', '/onapgo', '/healthz')

    @_app.middleware('http')
    async def _public_report_only(request: Request, call_next):
        p = request.url.path
        if p == '/':
            return RedirectResponse('/go', status_code=307)   # entry lives at /go; nothing identifying in the URL
        if any(p == a or p.startswith(a) for a in _ALLOW):
            return await call_next(request)
        return PlainTextResponse('Not available on this host.', status_code=404)


PW_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Catalyst — Secure Report</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,Helvetica,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#05070f;color:#e8eef6}
.wrap{position:relative;z-index:2;width:92%;max-width:400px;background:#0e1526;border:1px solid #24324a;border-radius:16px;padding:34px 32px;box-shadow:0 20px 60px #0009;text-align:center}
.lg{height:44px;margin-bottom:18px;filter:brightness(0) invert(1);opacity:.95}
h1{font-size:20px;font-weight:800;color:#fff;letter-spacing:.3px}
p{font-size:13px;color:#8ea1ba;margin:8px 0 22px}
input{width:100%;padding:12px 14px;border-radius:10px;border:1px solid #33445f;background:#0b1120;color:#fff;font-size:15px}
input:focus{outline:none;border-color:#1D9A78}
button{width:100%;margin-top:14px;padding:12px;border:none;border-radius:10px;background:#1D9A78;color:#fff;font-size:15px;font-weight:700;cursor:pointer}
button:hover{background:#178a6b}
.err{color:#ff9b9b;font-size:13px;margin-top:12px}
.wm{font-size:22px;font-weight:800;color:#fff;letter-spacing:.4px;margin-bottom:16px}
.ft{margin-top:20px;font-size:11px;color:#5b6b82}
.bg{position:fixed;inset:0;background:radial-gradient(1200px 600px at 70% 20%,#123 0,#05070f 70%);z-index:1}
</style></head><body>
<div class="bg"></div>
<form class="wrap" method="post" action="/login">
 <div class="wm">Research Catalyst</div>
 <h1>Secure Program Report</h1>
 <p>Enter the access password to continue.</p>
 <input type="password" name="password" placeholder="Password" autofocus autocomplete="current-password">
 <button type="submit">View report →</button>
 <!--ERR-->
 <div class="ft">Confidential</div>
</form></body></html>"""


# ---------------------------------------------------------------------------------------------------
ONAPGO_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ONAPGO® Patient Education — Live Report</title>
<style>
:root{--teal:#1D9A78;--lime:#8BC145;--cyan:#36AFCE;--blue:#1D6FA9;--amber:#F19D19;--rust:#B74919;--slate:#44546A;--ink:#1f2a37;--line:#e5e9f0;--paper:#ffffff}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{font-family:Arial,Helvetica,sans-serif;color:var(--ink);background:#0e1526;overflow:hidden}
/* ---- chrome ---- */
#bar{position:fixed;top:0;left:0;right:0;height:46px;display:flex;align-items:center;gap:10px;padding:0 14px;background:#0b1120;color:#cdd7e6;z-index:50;border-bottom:1px solid #1e293b}
#bar b{color:#fff;font-size:14px}
#bar .sp{flex:1}
#bar button{background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:8px;padding:6px 12px;font-size:12.5px;font-weight:600;cursor:pointer}
#bar button:hover{background:#334155}
#bar .dl{background:var(--teal);border-color:var(--teal);color:#fff}
#bar .me{font-size:11px;color:#7b8aa0}
#stage{position:fixed;inset:46px 0 0 0;display:flex;align-items:center;justify-content:center;overflow:auto}
#counter{position:fixed;bottom:12px;left:50%;transform:translateX(-50%);z-index:40;background:#0b1120cc;color:#cbd5e1;border:1px solid #334155;border-radius:20px;padding:5px 14px;font-size:12px;backdrop-filter:blur(4px)}
#counter .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#475569;margin:0 3px;cursor:pointer;vertical-align:middle}
#counter .dot.on{background:var(--teal);width:9px;height:9px}
.nav{position:fixed;top:50%;transform:translateY(-50%);z-index:45;width:44px;height:44px;border-radius:50%;background:#0b1120cc;color:#fff;border:1px solid #334155;font-size:20px;cursor:pointer;display:flex;align-items:center;justify-content:center}
.nav:hover{background:var(--teal);border-color:var(--teal)} .nav.prev{left:14px} .nav.next{right:14px}
/* ---- the fixed 1280x720 slide, scaled to fit ---- */
#scaler{width:1280px;height:720px;flex:0 0 auto}
.slide{width:1280px;height:720px;background:var(--paper);position:absolute;top:0;left:0;display:none;overflow:hidden;box-shadow:0 10px 50px #0008}
.slide.active{display:block}
.hd{position:absolute;top:38px;left:56px;right:56px;display:flex;align-items:flex-end;justify-content:space-between;border-bottom:3px solid var(--teal);padding-bottom:10px}
.hd h2{font-size:30px;color:var(--slate);font-weight:800;letter-spacing:.2px}
.hd .sub{font-size:14px;color:#8592a6;margin-top:3px;font-weight:600}
.hd img{height:34px;opacity:.9}
.foot{position:absolute;bottom:20px;left:56px;right:56px;display:flex;justify-content:space-between;font-size:11px;color:#9aa6b8}
.body{position:absolute;top:132px;left:56px;right:56px;bottom:52px}
.badge{display:inline-flex;align-items:center;gap:6px;background:#e8f7f1;color:#0f7a5a;border:1px solid #9fe0c9;border-radius:20px;padding:3px 11px;font-size:12px;font-weight:700}
.badge.live::before{content:"";width:8px;height:8px;border-radius:50%;background:#12b886;box-shadow:0 0 0 0 #12b88688;animation:pulse 1.6s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 #12b88688}70%{box-shadow:0 0 0 7px #12b88600}100%{box-shadow:0 0 0 0 #12b88600}}
/* tables */
table.rep{border-collapse:collapse;width:100%;font-size:15px}
table.rep th,table.rep td{border:1px solid var(--line);padding:8px 12px;text-align:center}
table.rep th{background:var(--slate);color:#fff;font-weight:700}
table.rep td.lbl{text-align:left;font-weight:700;color:var(--slate);background:#f6f8fb}
table.rep tr.tot td{background:#eef6f2;font-weight:800;color:#0f7a5a}
table.rep td.live{background:#e8f7f1}
table.rep th.live{background:var(--teal)}
.small{font-size:12.5px} .muted{color:#8592a6}
/* stat cards */
.cards{display:flex;gap:22px;flex-wrap:wrap}
.card{flex:1;min-width:190px;background:#f7fafc;border:1px solid var(--line);border-top:5px solid var(--teal);border-radius:12px;padding:20px 22px}
.card .n{font-size:44px;font-weight:800;color:var(--teal);line-height:1}
.card.b2{border-top-color:var(--cyan)} .card.b2 .n{color:var(--cyan)}
.card.b3{border-top-color:var(--amber)} .card.b3 .n{color:var(--amber)}
.card.b4{border-top-color:var(--blue)} .card.b4 .n{color:var(--blue)}
.card .l{font-size:14px;color:var(--slate);margin-top:8px;font-weight:600}
/* bar chart */
.chart{display:flex;align-items:flex-end;gap:20px;height:230px;padding:0 6px;border-bottom:2px solid var(--line)}
.grp{flex:1;display:flex;align-items:flex-end;justify-content:center;gap:7px;height:100%}
.bar{width:26px;border-radius:5px 5px 0 0;position:relative;transition:height .5s}
.bar span{position:absolute;top:-19px;left:50%;transform:translateX(-50%);font-size:11px;font-weight:700;color:var(--slate)}
.bi{background:linear-gradient(#2bbd93,#1D9A78)} .bp{background:linear-gradient(#57c6e6,#36AFCE)} .bo{background:linear-gradient(#f7b13f,#F19D19)}
.xlab{display:flex;gap:20px;margin-top:8px}.xlab>div{flex:1;text-align:center;font-size:13px;font-weight:700;color:var(--slate)}
.leg{display:flex;gap:20px;margin-top:14px;font-size:13px;font-weight:600;color:var(--slate)}
.leg i{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:5px}
/* quotes */
.quote{background:#f7fafc;border-left:5px solid var(--teal);border-radius:0 12px 12px 0;padding:20px 24px;font-size:17px;font-style:italic;color:#33424f;line-height:1.5}
.quote.b2{border-left-color:var(--cyan)} .quote.b3{border-left-color:var(--amber)}
/* title slide */
#s-title{background:#05070f}
#s-title .bg{position:absolute;inset:0;background-size:cover;background-position:center;opacity:.85}
#s-title .veil{position:absolute;inset:0;background:linear-gradient(105deg,#05070fe6 30%,#05070f55 70%)}
#s-title .tw{position:absolute;left:80px;top:210px;color:#fff}
#s-title .rc{font-size:52px;font-weight:800;letter-spacing:.5px}
#s-title .pe{font-size:34px;font-weight:600;color:#cfe9ff;margin-top:8px}
#s-title .rp{font-size:20px;color:#8bd7bf;margin-top:26px;font-weight:700;letter-spacing:2px;text-transform:uppercase}
#s-title .lg{position:absolute;right:70px;top:70px;height:56px;filter:brightness(0) invert(1);opacity:.92}
#s-title .asof{position:absolute;left:80px;bottom:70px;color:#9fb3c8;font-size:14px}
.klist{columns:2;column-gap:34px;font-size:14.5px}
.klist div{break-inside:avoid;padding:5px 0;border-bottom:1px solid var(--line)}
.klist b{color:var(--teal)}
@media print{
 @page{size:1280px 720px;margin:0}
 body{background:#fff;overflow:visible}
 #bar,#counter,.nav{display:none!important}
 #stage{position:static;inset:auto;display:block}
 #scaler{transform:none!important;width:1280px;height:auto}
 .slide{display:block!important;position:relative;page-break-after:always;box-shadow:none;margin:0}
}
</style></head><body>
<div id="bar">
 <b>ONAPGO® Patient Education — Live Report</b>
 <span class="badge live" id="livebadge" style="display:none">Live · updated <span id="asof">—</span></span>
 <span class="sp"></span>
 <span class="me">__ME__</span>
 <button onclick="fs()">⛶ Present</button>
 <button class="dl" onclick="window.print()">⤓ Download PDF</button>
</div>
<button class="nav prev" onclick="go(-1)">‹</button>
<button class="nav next" onclick="go(1)">›</button>
<div id="stage"><div id="scaler"><div id="deck"></div></div></div>
<div id="counter"></div>
<script>
const A=(p)=>'/onapgo/asset/'+p;
const MET={loaded:false,data:null};
async function loadMetrics(){try{const r=await fetch('/api/onapgo/metrics'+(location.search||''));if(!r.ok)return;MET.data=await r.json();MET.loaded=true;
  if(MET.data.as_of){document.getElementById('asof').textContent=MET.data.as_of;document.getElementById('livebadge').style.display='';}
  renderMetrics();}catch(e){}}
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}

// ---------- slide definitions ----------
function hd(title,sub){return `<div class="hd"><div><h2>${title}</h2>${sub?`<div class="sub">${sub}</div>`:''}</div><img src="${A('onapgo_logo.png')}" alt="ONAPGO"></div>`}
function foot(n){return `<div class="foot"><span>Research Catalyst · ONAPGO® Patient Education Program · Confidential</span><span>${n}</span></div>`}

const SLIDES=[
// 1 — TITLE
()=>`<section class="slide" id="s-title">
  <div class="bg" style="background-image:url('${A('neuron_bg.jpg')}')"></div><div class="veil"></div>
  <img class="lg" src="${A('onapgo_logo.png')}">
  <div class="tw"><div class="rc">Research Catalyst</div><div class="pe">ONAPGO® Patient Education</div>
   <div class="rp">Live Program Report · 2026</div></div>
  <div class="asof" id="titleasof">Real-time figures — updated continuously</div>
 </section>`,
// 2 — PATIENT ADVOCACY CENTER METRICS (LIVE)
()=>`<section class="slide">${hd('Patient Advocacy Center Metrics','Branded patient discussions delivered · Initial / Pre-HCP / Post-HCP')}
  <div class="body"><div id="metricsWrap"><div class="muted">Loading live figures…</div></div></div>${foot('2')}</section>`,
// 3 — DELIVERY SCHEDULE
()=>`<section class="slide">${hd('Delivery Schedule 2026','Calls · Emails · Webinars')}
  <div class="body"><table class="rep small"><tr><th>Schedule</th><th>Calls Planned</th><th>Calls Delivered</th><th>Emails Planned</th><th>Emails Delivered</th><th>Webinar</th></tr>
  ${[['Jan-26','150','154','4,000','17,923',''],['Feb-26','175','184','4,000','35,854','Feb 27 · 273 reg / 113 att'],['Mar-26','175','175','4,000','11,049',''],['Apr-26','175','176','4,000','5,796',''],['May-26','500','508','7,500','13,889',''],['Jun-26','500','502','7,500','—','Jun 19'],['Jul-26','500','<b style="color:#1D9A78">Live ▸</b>','7,500','—','Late July']].map(r=>`<tr><td class="lbl">${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td><td>${r[4]}</td><td>${r[5]}</td></tr>`).join('')}
  </table><div class="muted small" style="margin-top:12px">May 2026: resumed full marketing budget (500 calls / 7,500 emails per month).</div></div>${foot('3')}</section>`,
// 4 — PRINT & DIGITAL
()=>`<section class="slide">${hd('Delivering Print and Digital Materials','May 2026')}
  <div class="body"><div class="cards">
   <div class="card"><div class="n">508</div><div class="l">Branded Patient Calls Delivered</div></div>
   <div class="card b2"><div class="n">13,889</div><div class="l">Branded ONAPGO Patient Educational Emails Sent</div></div>
   <div class="card b3"><div class="n">111</div><div class="l">Webinar Marketing — Registered</div></div>
  </div>
  <div class="cards" style="margin-top:22px">
   <div class="card b4"><div class="n">84,551</div><div class="l">Total Emails Sent (program-to-date)</div></div>
   <div class="card"><div class="n">1,699</div><div class="l">Total Branded Discussions (Jan–Jun) + July live</div></div>
   <div class="card b2"><div class="n">Multi</div><div class="l">Channel: Phone · Calendar · Email · Mail</div></div>
  </div></div>${foot('4')}</section>`,
// 5 — QUALITATIVE QUOTES
()=>`<section class="slide">${hd('Call Center Qualitative Reports','From Parkinson’s Community Members')}
  <div class="body" style="display:flex;flex-direction:column;gap:18px;justify-content:center">
   <div class="quote">“What I appreciated most was not feeling pressured to make any decisions right away. It was helpful to learn about Onapgo and gain a better understanding of it, so I can discuss it with my doctor.”</div>
   <div class="quote b2">“I’ve spent years adjusting medication schedules and planning my days around symptoms. Learning about Onapgo made me feel hopeful that there may be another way to manage those ups and downs.”</div>
   <div class="quote b3">“Hearing about ONAPGO gives me hope. It’s encouraging to know that new therapies are becoming available, and I’m looking forward to asking my doctor for more information.”</div>
  </div>${foot('5')}</section>`,
// 6 — EMAIL METRICS
()=>`<section class="slide">${hd('Email Metrics','Program-to-date')}
  <div class="body"><table class="rep small"><tr><th class="lbl" style="text-align:left">Metric</th><th>Jan</th><th>Feb</th><th>Mar</th><th>Apr</th><th>May</th><th>Totals</th></tr>
  ${[['Emails Sent','17,923','1,254','11,049','5,796','13,889','84,551'],['Avg Open Rate','15%','18.9%','7.9%','6.4%','4.7%','8%'],['Opens','2,685','236','861','496','640','7,043'],['Avg Click Rate','0.80%','3.90%','0.38%','0.40%','0.21%','0.64%'],['Clicks','148','48','42','23','28','539'],['Unsubscribe','0.18%','0.64%','0.18%','0.21%','0.07%','0.16%']].map(r=>`<tr><td class="lbl">${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td><td>${r[4]}</td><td>${r[5]}</td><td style="font-weight:800;color:#0f7a5a">${r[6]}</td></tr>`).join('')}
  </table><div class="muted small" style="margin-top:10px">Aggregated across all sends; February includes multiple webinar-promotion sends.</div></div>${foot('6')}</section>`,
// 7 — MEMBER QUESTIONS + NPI
()=>`<section class="slide">${hd('Market Research — Member Questions & HCP Activity','488 member questions captured in June')}
  <div class="body" style="display:flex;gap:28px">
   <div style="flex:1.2"><div class="badge" style="margin-bottom:8px">Top member questions — June</div>
    <div class="klist">${[['How much does it cost / is it covered?','73'],['Same as Vyalev, or different?','43'],['Similar to my current medication?','32'],['Can I use it if I’m on DBS?','28'],['Do I sleep with the pump?','25'],['First week getting used to it?','25'],['What if my neurologist isn’t familiar with it?','23'],['Does the needle stay under my skin?','21'],['Will I still need c/l?','21'],['Can emotional stress affect how it works?','19']].map(q=>`<div>${esc(q[0])} <b style="float:right">${q[1]}</b></div>`).join('')}</div></div>
   <div style="flex:.8"><div class="badge" style="margin-bottom:8px">HCP NPIs captured — June</div>
    <div class="cards" style="flex-direction:column;gap:14px">
     <div class="card"><div class="n">91</div><div class="l">Initial-form neurologists</div></div>
     <div class="card b2"><div class="n">185</div><div class="l">Pre-HCP-form neurologists</div></div>
     <div class="card b3"><div class="n">163</div><div class="l">Post-HCP-form neurologists</div></div>
    </div>
    <div class="muted small" style="margin-top:10px">439 confirmed neurologist NPIs collected across 502 June discussions.</div></div>
  </div>${foot('7')}</section>`,
// 8 — TREATMENT PLAN CHANGES
()=>`<section class="slide">${hd('Call Center ONAPGO® Qualitative Data','Did your doctor make changes to your Parkinson’s treatment plan?')}
  <div class="body"><table class="rep"><tr><th class="lbl" style="text-align:left">Reported outcome</th><th>Members</th></tr>
  ${[['No Changes (maybe next appointment)','46'],['Changed the Dose/Timing (Not C/L)','32'],['Changed the Dose/Timing (C/L)','25'],['Suggested DBS','25'],['Prescribed Another Treatment','24'],['Suggested PT or Exercise','21'],['Said My OFF Symptoms Not Bad Enough','9'],['Suggested Another Subq Infusion','5']].map(r=>`<tr><td class="lbl">${esc(r[0])}</td><td>${r[1]}</td></tr>`).join('')}
  <tr class="tot"><td class="lbl">Total responses</td><td>187</td></tr></table></div>${foot('8')}</section>`,
// 9 — DISCUSSED ONAPGO
()=>`<section class="slide">${hd('Call Center ONAPGO® Qualitative Data','Did you discuss ONAPGO® with your doctor at this recent appointment?')}
  <div class="body" style="display:flex;gap:30px">
   <div style="flex:.7"><div class="cards" style="flex-direction:column;gap:16px">
     <div class="card"><div class="n">121</div><div class="l">Yes — discussed ONAPGO® with their doctor</div></div>
     <div class="card b3"><div class="n">44</div><div class="l">No — did not get the chance</div></div>
     <div class="card b4"><div class="n">165</div><div class="l">Total responses</div></div>
   </div></div>
   <div style="flex:1"><div class="badge" style="margin-bottom:8px">If not — why?</div>
    <div class="klist" style="columns:1">${[['I discussed a different treatment option','13'],['My doctor didn’t have time / was running behind','9'],['I had other concerns I discussed instead','9'],['I’m worried about side effects','5'],['My doctor didn’t bring ONAPGO up','4'],['I didn’t express my OFF time','2'],['I’m concerned about the cost','2'],['I’m not interested in ONAPGO®','1']].map(q=>`<div>${esc(q[0])} <b style="float:right">${q[1]}</b></div>`).join('')}</div></div>
  </div>${foot('9')}</section>`,
];

// ---------- live metrics slide ----------
function renderMetrics(){const w=document.getElementById('metricsWrap');if(!w)return;const d=MET.data;
 if(!d){w.innerHTML='<div class="muted">Live figures unavailable.</div>';return;}
 const stg=[['initial','Initial Discussions','bi'],['pre_hcp','Pre-HCP Discussions','bp'],['post_hcp','Post-HCP Discussions','bo']];
 const cols=d.months;
 // table
 let th='<tr><th class="lbl" style="text-align:left">Deliverable</th>'+cols.map(c=>`<th class="${c.live?'live':''}">${c.label}${c.live?' <span style="font-size:10px">▸ LIVE</span>':''}</th>`).join('')+'<th>Totals</th></tr>';
 let rows='';const colTot={};cols.forEach(c=>colTot[c.ym]=0);let grand=0;
 stg.forEach(s=>{let rt=0;let tds=cols.map(c=>{const v=d.stages[s[0]][c.ym]||0;rt+=v;colTot[c.ym]+=v;return `<td class="${c.live?'live':''}">${v}</td>`}).join('');grand+=rt;
   rows+=`<tr><td class="lbl">${s[1]}</td>${tds}<td style="font-weight:800;color:#0f7a5a">${rt}</td></tr>`;});
 let totrow=`<tr class="tot"><td class="lbl">Monthly Totals</td>${cols.map(c=>`<td>${colTot[c.ym]}</td>`).join('')}<td>${grand.toLocaleString()}</td></tr>`;
 // chart (per month: 3 bars), scale to max
 let allv=[];cols.forEach(c=>stg.forEach(s=>allv.push(d.stages[s[0]][c.ym]||0)));const mx=Math.max(1,...allv);
 const groups=cols.map(c=>`<div class="grp">${stg.map(s=>{const v=d.stages[s[0]][c.ym]||0;return `<div class="bar ${s[2]}" style="height:${Math.max(2,v/mx*100)}%"><span>${v}</span></div>`}).join('')}</div>`).join('');
 const xl=cols.map(c=>`<div>${c.label}${c.live?' ▸':''}</div>`).join('');
 w.innerHTML=`${d.live_month?`<div class="badge live" style="margin-bottom:10px">${d.live_month} is live — updated ${esc(d.as_of)}</div>`:''}
  <div style="display:flex;gap:30px">
   <div style="flex:1.05"><table class="rep small">${th}${rows}${totrow}</table>
    <div class="muted small" style="margin-top:8px">Jan–May: client-reviewed program figures. ${d.live_month?d.live_month+' onward: real-time from the Patient Advocacy Center CRM.':''}</div></div>
   <div style="flex:.95"><div class="chart">${groups}</div><div class="xlab">${xl}</div>
    <div class="leg"><span><i class="bi"></i>Initial</span><span><i class="bp"></i>Pre-HCP</span><span><i class="bo"></i>Post-HCP</span></div></div>
  </div>`;}

// ---------- deck engine ----------
let CUR=0;const deck=document.getElementById('deck');
deck.innerHTML=SLIDES.map(f=>f()).join('');
const slides=[...deck.querySelectorAll('.slide')];
function renderCounter(){document.getElementById('counter').innerHTML=slides.map((_,i)=>`<span class="dot ${i===CUR?'on':''}" onclick="jump(${i})"></span>`).join('')+` <span style="margin-left:8px">${CUR+1} / ${slides.length}</span>`;}
function show(){slides.forEach((s,i)=>s.classList.toggle('active',i===CUR));renderCounter();if(CUR===1)renderMetrics();}
function go(d){CUR=Math.max(0,Math.min(slides.length-1,CUR+d));show();}
function jump(i){CUR=i;show();}
function fs(){const e=document.documentElement;if(!document.fullscreenElement){(e.requestFullscreen||e.webkitRequestFullscreen).call(e);}else{document.exitFullscreen();}}
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='PageDown'||e.key===' ')go(1);else if(e.key==='ArrowLeft'||e.key==='PageUp')go(-1);else if(e.key==='Home')jump(0);else if(e.key==='End')jump(slides.length-1);});
// scale the fixed 1280x720 slide to fit
function fit(){const st=document.getElementById('stage');const sc=document.getElementById('scaler');const k=Math.min((st.clientWidth-40)/1280,(st.clientHeight-40)/720);sc.style.transform='scale('+k+')';sc.style.transformOrigin='center';}
window.addEventListener('resize',fit);
show();fit();loadMetrics();
setInterval(loadMetrics,60000);   // keep July figures live
</script></body></html>"""
