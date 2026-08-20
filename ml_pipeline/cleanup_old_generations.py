"""
cleanup_old_generations.py — deliberate 30-day retention policy for
generated images. Runs daily; finds generations older than 30 days
whose file hasn't already been cleaned up, deletes the actual file from
Supabase Storage, and marks expired_at so the console can show "this
image was auto-deleted" instead of a broken thumbnail.

Usage:
    export DATABASE_URL / SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
    python3 cleanup_old_generations.py
"""
import os
import sys
import re
import requests
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))

for var_name, var_val in [("DATABASE_URL", DATABASE_URL), ("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_SERVICE_ROLE_KEY)]:
    if not var_val:
        print(f"ERROR: {var_name} is not set.", file=sys.stderr)
        sys.exit(1)


def storage_path_from_url(url: str):
    # Public URLs look like:
    # {SUPABASE_URL}/storage/v1/object/public/marketing-assets/{path}
    match = re.search(r"/storage/v1/object/public/marketing-assets/(.+)$", url or "")
    return match.group(1) if match else None


def delete_from_storage(path: str) -> bool:
    headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}
    res = requests.delete(f"{SUPABASE_URL}/storage/v1/object/marketing-assets/{path}", headers=headers, timeout=30)
    if res.ok:
        return True
    print(f"  Storage delete failed for {path}: {res.status_code} {res.text}")
    return False


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute(
        """select id, output_url from generations
           where output_url is not null and expired_at is null
             and created_at < now() - interval '%s days'""",
        (RETENTION_DAYS,),
    )
    rows = cur.fetchall()
    print(f"Found {len(rows)} generation(s) older than {RETENTION_DAYS} days to clean up.")

    cleaned = 0
    for gen_id, output_url in rows:
        path = storage_path_from_url(output_url)
        if not path:
            print(f"  Skipping {gen_id} — could not parse storage path from URL: {output_url}")
            continue
        if delete_from_storage(path):
            cur.execute("update generations set expired_at = now() where id = %s", (gen_id,))
            conn.commit()
            cleaned += 1
            print(f"  Cleaned up {gen_id} ({path})")

    cur.close()
    conn.close()
    print(f"\nDone — {cleaned}/{len(rows)} cleaned up successfully.")


if __name__ == "__main__":
    main()
