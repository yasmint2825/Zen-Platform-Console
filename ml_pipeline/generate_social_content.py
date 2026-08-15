"""
generate_social_content.py — MiniCuts / Zen Platform social content agent.

Generates ONE draft Instagram post per run: a caption (Claude, grounded in
real salon data) and a branded graphic (Pillow, using the tenant's actual
logo and colors). Writes it to mw_social_posts as pending_review — nothing
here ever publishes anything. That only happens when a human approves it
in the console, which calls Instagram's API separately.

Deliberately does NOT use real customer photos anywhere — every image is a
generated branded graphic. MiniCuts' customers are children; publishing
their likeness without explicit, tracked parental consent is a real legal
and reputational risk, not a hypothetical one, so this pipeline avoids it
entirely rather than trying to handle consent tracking as an afterthought.

Usage:
    export DATABASE_URL="postgresql://..."
    export SUPABASE_URL="https://xxx.supabase.co"
    export SUPABASE_SERVICE_ROLE_KEY="..."
    export ANTHROPIC_API_KEY="..."
    export TENANT_ID="minicuts"
    python3 generate_social_content.py
"""
import os
import sys
import json
import io
import requests
import psycopg2
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TENANT_ID = os.environ.get("TENANT_ID", "minicuts")
CLAUDE_MODEL = "claude-sonnet-5"

CANVAS_SIZE = 1080
DEFAULT_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"  # present by default on GitHub Actions ubuntu-latest runners

for var_name, var_val in [("DATABASE_URL", DATABASE_URL), ("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_SERVICE_ROLE_KEY), ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY)]:
    if not var_val:
        print(f"ERROR: {var_name} is not set.", file=sys.stderr)
        sys.exit(1)


def gather_real_context(cur) -> dict:
    """Pulls a few real, current numbers to ground the content in — the
    same philosophy as generate_insights: every claim should be tied to
    something real, not invented."""
    context = {}
    cur.execute("select value from mw_analytics_snapshot where tenant_id=%s and metric_key='active_customers_30d' and segment='all'", (TENANT_ID,))
    row = cur.fetchone()
    context["active_customers_30d"] = float(row[0]) if row else None

    cur.execute("select value from mw_analytics_snapshot where tenant_id=%s and metric_key='retention_rate_90d' and segment='all'", (TENANT_ID,))
    row = cur.fetchone()
    context["retention_rate"] = float(row[0]) if row else None

    cur.execute("select description, count(*) as cnt from mw_transactions where tenant_id=%s and transaction_date >= current_date - 30 and description is not null group by description order by cnt desc limit 1", (TENANT_ID,))
    row = cur.fetchone()
    context["popular_service_30d"] = row[0] if row else None

    cur.execute("select day_name, avg_visits from mw_load_forecast where tenant_id=%s order by avg_visits desc limit 1", (TENANT_ID,))
    row = cur.fetchone()
    context["busiest_day"] = row[0] if row else None

    return context


def load_brand_settings(cur) -> dict:
    cur.execute("select logo_url, primary_color, secondary_color, accent_color from mw_brand_settings where tenant_id=%s", (TENANT_ID,))
    row = cur.fetchone()
    if not row:
        # Reasonable neutral defaults so the pipeline still produces
        # something usable before brand assets are uploaded, rather than
        # failing outright.
        return {"logo_url": None, "primary_color": "#4A5568", "secondary_color": "#FFFFFF", "accent_color": "#ED8936"}
    return {"logo_url": row[0], "primary_color": row[1] or "#4A5568", "secondary_color": row[2] or "#FFFFFF", "accent_color": row[3] or "#ED8936"}


def generate_content_with_claude(context: dict) -> dict:
    """Asks Claude for a caption and a short graphic headline — both
    grounded in the real context gathered above. Explicit instruction to
    say so if the data doesn't support an interesting angle, rather than
    invent one."""
    context_lines = []
    if context.get("popular_service_30d"):
        context_lines.append(f"Most popular service in the last 30 days: {context['popular_service_30d']}")
    if context.get("retention_rate") is not None:
        context_lines.append(f"Customer retention rate: {context['retention_rate']}%")
    if context.get("active_customers_30d") is not None:
        context_lines.append(f"Active customers in the last 30 days: {int(context['active_customers_30d'])}")
    if context.get("busiest_day"):
        context_lines.append(f"Busiest day of the week: {context['busiest_day']}")
    context_text = "\n".join(context_lines) if context_lines else "No standout real data available this run — use a general, warm, seasonal angle instead."

    system_prompt = """You write Instagram content for a children's hair salon in Dubai. The audience is parents.
Never mention or imply any specific child, name, or photo — no real customer content, ever, only general/promotional angles.
Write warm, friendly, brief copy — not corporate, not salesy.

Respond ONLY with JSON: {"caption": "the full Instagram caption, including 2-4 relevant hashtags at the end", "graphic_headline": "a SHORT (under 8 words) headline to display ON the image itself"}"""

    user_message = f"Real data for this week:\n{context_text}\n\nGenerate today's post."

    res = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        json={"model": CLAUDE_MODEL, "max_tokens": 500, "system": system_prompt, "messages": [{"role": "user", "content": user_message}]},
        timeout=30,
    )
    res.raise_for_status()
    data = res.json()
    text = next((b["text"] for b in data.get("content", []) if b.get("type") == "text"), "{}")
    cleaned = text.replace("```json", "").replace("```", "").strip()
    first_brace, last_brace = cleaned.find("{"), cleaned.rfind("}")
    parsed = json.loads(cleaned[first_brace:last_brace + 1])
    return {"caption": parsed.get("caption", ""), "graphic_headline": parsed.get("graphic_headline", "")}


def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def generate_graphic(headline: str, brand: dict) -> bytes:
    """Builds a branded square graphic — solid brand-color background,
    logo if available, headline text. No real photos anywhere."""
    bg_color = hex_to_rgb(brand["primary_color"])
    text_color = hex_to_rgb(brand["secondary_color"])
    accent_color = hex_to_rgb(brand["accent_color"])

    img = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), bg_color)
    draw = ImageDraw.Draw(img)

    # Accent stripe along the bottom — simple, deliberate branding
    # element rather than a fully bare background.
    draw.rectangle([0, CANVAS_SIZE - 60, CANVAS_SIZE, CANVAS_SIZE], fill=accent_color)

    if brand.get("logo_url"):
        try:
            logo_resp = requests.get(brand["logo_url"], timeout=15)
            logo_resp.raise_for_status()
            logo = Image.open(io.BytesIO(logo_resp.content)).convert("RGBA")
            logo.thumbnail((220, 220))
            img.paste(logo, (CANVAS_SIZE - logo.width - 50, 50), logo)
        except Exception as e:
            print(f"  Warning: could not load logo ({e}) — continuing without it")

    try:
        font = ImageFont.truetype(DEFAULT_FONT_PATH, 72)
    except Exception:
        font = ImageFont.load_default()

    # Wrap the headline manually across a few lines rather than letting
    # it run off the canvas — simple word-wrap sized to the canvas width.
    words = headline.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        if draw.textlength(test, font=font) > CANVAS_SIZE - 160:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    total_text_height = len(lines) * 90
    y = (CANVAS_SIZE - total_text_height) // 2
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((CANVAS_SIZE - w) // 2, y), line, font=font, fill=text_color)
        y += 90

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def upload_image(image_bytes: bytes) -> str:
    path = f"{TENANT_ID}/post-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.png"
    res = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/social-posts/{path}",
        # Supabase's storage API expects BOTH headers for a direct REST
        # call like this — apikey identifies the project to the gateway,
        # Authorization carries the actual permission level. Missing
        # apikey specifically can surface as a plain 400, not an
        # obviously-auth-related error, which is exactly what happened.
        headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "image/png"},
        data=image_bytes,
        timeout=30,
    )
    if not res.ok:
        print(f"  Upload failed ({res.status_code}): {res.text}")
    res.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/social-posts/{path}"


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print(f"Generating social content for tenant '{TENANT_ID}'...")
    context = gather_real_context(cur)
    brand = load_brand_settings(cur)
    print(f"  Context: {context}")

    print("Asking Claude for caption + headline...")
    content = generate_content_with_claude(context)
    print(f"  Headline: {content['graphic_headline']}")

    print("Generating branded graphic...")
    image_bytes = generate_graphic(content["graphic_headline"], brand)

    print("Uploading image...")
    image_url = upload_image(image_bytes)
    print(f"  {image_url}")

    reasoning = "Based on: " + "; ".join(f"{k}={v}" for k, v in context.items() if v is not None) if any(context.values()) else "No standout data this run — general seasonal content."

    cur.execute(
        """insert into mw_social_posts (tenant_id, caption, image_url, reasoning, status)
           values (%s, %s, %s, %s, 'pending_review')""",
        (TENANT_ID, content["caption"], image_url, reasoning),
    )
    conn.commit()
    cur.close()
    conn.close()
    print("\nDone — draft saved to the review queue.")


if __name__ == "__main__":
    main()
