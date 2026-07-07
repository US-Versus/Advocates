"""Consistent snapshot of the live SQLite DB -> gs://<bucket>/db-backups/.

Bridge safety net (Stage 0) until the Cloud SQL/Postgres migration. Runs as a
Cloud Run Job triggered hourly by Cloud Scheduler. It:
  1. downloads the current app.db object (atomic read of one GCS generation),
  2. verifies it with PRAGMA quick_check, retrying if it caught a torn/mid-flush
     state (writes are infrequent, so a retry lands a clean moment),
  3. makes a transactionally-consistent copy via the SQLite online-backup API,
  4. uploads it as db-backups/YYYY-MM-DD_HHMM.db,
  5. prunes snapshots older than RETAIN_DAYS.

The app's startup integrity guard (_integrity_guard in main.py) restores the
newest snapshot that passes quick_check from this same db-backups/ prefix.
"""
import os, sqlite3, tempfile, datetime, time
from google.cloud import storage

BUCKET = os.environ.get('BACKUP_BUCKET', 'research-catalyst-crm-data')
DB_OBJECT = os.environ.get('DB_OBJECT', 'app.db')
PREFIX = os.environ.get('BACKUP_PREFIX', 'db-backups/')
RETAIN_DAYS = int(os.environ.get('RETAIN_DAYS', '14'))


def _quickcheck(path):
    try:
        c = sqlite3.connect(path, timeout=10.0)
        try:
            r = c.execute("PRAGMA quick_check").fetchone()
        finally:
            c.close()
        return bool(r) and str(r[0]).lower() == 'ok'
    except sqlite3.DatabaseError:
        return False


def main():
    client = storage.Client()
    bucket = client.bucket(BUCKET)
    blob = bucket.blob(DB_OBJECT)
    if not blob.exists():
        print('CRITICAL: gs://%s/%s not found' % (BUCKET, DB_OBJECT)); return
    tmp = tempfile.mkdtemp()
    live = os.path.join(tmp, 'live.db')
    snap = os.path.join(tmp, 'snap.db')

    # Download the current object; retry if we catch a torn/mid-flush write.
    ok = False
    for attempt in range(4):
        blob.reload(); blob.download_to_filename(live)
        if _quickcheck(live):
            ok = True; break
        print('attempt %d: downloaded app.db failed quick_check, retrying in 5s' % (attempt + 1))
        time.sleep(5)
    if not ok:
        print('CRITICAL: could not obtain a consistent app.db this cycle; skipping'); return

    # Transactionally-consistent copy via the online-backup API.
    src = sqlite3.connect(live, timeout=10.0)
    dst = sqlite3.connect(snap)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    if not _quickcheck(snap):
        print('CRITICAL: online-backup produced a bad snapshot; skipping'); return

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d_%H%M')
    name = '%s%s.db' % (PREFIX, stamp)
    bucket.blob(name).upload_from_filename(snap)
    print('snapshot uploaded: gs://%s/%s (%d bytes)' % (BUCKET, name, os.path.getsize(snap)))

    # Prune snapshots older than RETAIN_DAYS.
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=RETAIN_DAYS)
    pruned = 0
    for b in bucket.list_blobs(prefix=PREFIX):
        if b.name.endswith('.db') and b.time_created and b.time_created < cutoff:
            b.delete(); pruned += 1
    print('pruned %d snapshot(s) older than %d days' % (pruned, RETAIN_DAYS))


if __name__ == '__main__':
    main()
