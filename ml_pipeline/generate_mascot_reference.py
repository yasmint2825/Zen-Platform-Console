"""
generate_mascot_reference.py — creates a candidate reference image for
"Minicuts Panda" using Replicate's flux-2-pro. This is a one-time (or
occasional) tool, not part of the recurring content pipeline — it just
produces a candidate for review; nothing here auto-approves anything.

Once a candidate is approved in the console, its image_url becomes
mw_brand_settings.mascot_reference_url — the reference every future
monthly-planning prompt will point to for character consistency.

Usage:
    export DATABASE_URL / SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / REPLICATE_API_TOKEN
    export TENANT_ID="minicuts"
    export MASCOT_DESCRIPTION="..." (optional override; falls back to
        mw_brand_settings.mascot_description, or a built-in default)
    python3 generate_mascot_reference.py
"""
import os
import sys
import io
import time
import requests
import psycopg2
from datetime import datetime, timezone

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
TENANT_ID = os.environ.get("TENANT_ID", "minicuts")
DESCRIPTION_OVERRIDE = os.environ.get("MASCOT_DESCRIPTION")

DEFAULT_DESCRIPTION = (
    "A friendly, round-faced cartoon panda mascot character, black and white fur, "
    "big warm eyes, a cheerful smile. Wears a small colorful bow tie. "
    "Flat, clean children's-illustration art style, not photorealistic. "
    "Friendly, welcoming, gentle personality, like a beloved children's book character. "
    "Simple plain background, centered, full body visible."
)

for var_name, var_val in [("DATABASE_URL", DATABASE_URL), ("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_SERVICE_ROLE_KEY), ("REPLICATE_API_TOKEN", REPLICATE_API_TOKEN)]:
    if not var_val:
        print(f"ERROR: {var_name} is not set.", file=sys.stderr)
        sys.exit(1)


def generate_image(prompt: str) -> bytes:
    headers = {"Authorization": f"Bearer {REPLICATE_API_TOKEN}", "Content-Type": "application/json", "Prefer": "wait"}
    res = requests.post(
        "https://api.replicate.com/v1/models/black-forest-labs/flux-2-pro/predictions",
        headers=headers,
        json={"input": {"prompt": prompt, "aspect_ratio": "1:1", "output_format": "png"}},
        timeout=65,
    )
    res.raise_for_status()
    prediction = res.json()

    get_url = prediction.get("urls", {}).get("get")
    while prediction.get("status") not in ("succeeded", "failed", "canceled") and get_url:
        time.sleep(1)
        poll_res = requests.get(get_url, headers=headers, timeout=30)
        poll_res.raise_for_status()
        prediction = poll_res.json()

    if prediction.get("status") != "succeeded":
        raise ValueError(f"Replicate prediction did not succeed: {prediction.get('error')}")

    output = prediction.get("output")
    image_url = output[0] if isinstance(output, list) else output
    if not image_url:
        raise ValueError("Replicate response contained no output image URL")

    img_res = requests.get(image_url, timeout=30)
    img_res.raise_for_status()
    return img_res.content


def upload_image(image_bytes: bytes) -> str:
    path = f"{TENANT_ID}/mascot-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.png"
    res = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/brand-assets/{path}",
        headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "image/png"},
        data=image_bytes,
        timeout=30,
    )
    if not res.ok:
        print(f"  Upload failed ({res.status_code}): {res.text}")
    res.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/brand-assets/{path}"


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    description = DESCRIPTION_OVERRIDE
    if not description:
        cur.execute("select mascot_description from mw_brand_settings where tenant_id=%s", (TENANT_ID,))
        row = cur.fetchone()
        description = (row[0] if row else None) or DEFAULT_DESCRIPTION

    print(f"Generating mascot candidate for tenant '{TENANT_ID}'...")
    print(f"  Description: {description}")

    image_bytes = generate_image(description)
    print("Uploading...")
    image_url = upload_image(image_bytes)
    print(f"  {image_url}")

    cur.execute(
        """insert into mw_mascot_candidates (tenant_id, image_url, description_used, status)
           values (%s, %s, %s, 'pending_review')""",
        (TENANT_ID, image_url, description),
    )
    conn.commit()
    cur.close()
    conn.close()
    print("\nDone — candidate saved for review.")


if __name__ == "__main__":
    main()
