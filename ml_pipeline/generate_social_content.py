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
import time
import requests
import psycopg2
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
TENANT_ID = os.environ.get("TENANT_ID", "minicuts")
CLAUDE_MODEL = "claude-sonnet-5"

# Set when this run is a "request changes" regeneration rather than a
# fresh scheduled post — REGEN_POST_ID identifies which existing draft
# to revise, REGEN_FEEDBACK is what the reviewer asked to change.
REGEN_POST_ID = os.environ.get("REGEN_POST_ID")
REGEN_FEEDBACK = os.environ.get("REGEN_FEEDBACK")

CANVAS_SIZE = 1080
DEFAULT_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"  # present by default on GitHub Actions ubuntu-latest runners

for var_name, var_val in [("DATABASE_URL", DATABASE_URL), ("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_SERVICE_ROLE_KEY), ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY), ("REPLICATE_API_TOKEN", REPLICATE_API_TOKEN)]:
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


def generate_content_with_claude(context: dict, previous_caption: str = None, feedback: str = None) -> dict:
    """Asks Claude for a caption and a short graphic headline — both
    grounded in the real context gathered above. Explicit instruction to
    say so if the data doesn't support an interesting angle, rather than
    invent one. When previous_caption + feedback are given, this is a
    revision request, not a fresh draft — Claude sees exactly what it
    wrote before and exactly what the reviewer asked to change."""
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

    if previous_caption and feedback:
        user_message = f"Real data for this week:\n{context_text}\n\nYou previously wrote this caption:\n\"{previous_caption}\"\n\nThe reviewer asked for this change:\n\"{feedback}\"\n\nRevise it accordingly."
    else:
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
    # strict=False allows raw control characters (like a literal newline)
    # inside JSON string values — Claude naturally writes multi-line
    # Instagram captions (separating text from hashtags with a blank
    # line), and a literal newline in a caption is completely reasonable
    # content that happens to be technically invalid under strict JSON.
    # Fighting the model into never using line breaks is the wrong fix;
    # relaxing the parser to accept genuinely valid content is the right
    # one — verified this actually resolves the exact error before
    # shipping it, not just assumed.
    parsed = json.loads(cleaned[first_brace:last_brace + 1], strict=False)
    return {"caption": parsed.get("caption", ""), "graphic_headline": parsed.get("graphic_headline", "")}


def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def generate_ai_background(headline: str) -> Image.Image:
    """
    Generates an illustrated (never photorealistic) background scene via
    Replicate's flux-schnell model. The safety boundary is structural,
    not just a good intention — it's baked directly into every prompt
    sent, every single time, not something that depends on remembering
    to add it manually:
      - Illustrated/stylized only, explicitly never photorealistic —
        this avoids the real ambiguity a photorealistic AI child could
        create ("is that an actual customer?").
      - No real customer likeness is possible here at all — this
        function has no photo input, nothing to base a real person on.
      - No text requested in the generated image — Pillow's text overlay
        (below) is what actually renders the headline, since AI image
        models are still unreliable at clean, correctly-spelled text.
    """
    prompt = (
        f"A warm, cheerful, FLAT ILLUSTRATED cartoon-style scene for a children's hair salon's Instagram post. "
        f"Bright, friendly children's-book illustration art style — explicitly NOT photorealistic, NOT a photograph. "
        f"Theme: {headline}. "
        f"Absolutely no text, letters, or words anywhere in the image. Square composition, colorful, welcoming."
    )
    headers = {"Authorization": f"Bearer {REPLICATE_API_TOKEN}", "Content-Type": "application/json", "Prefer": "wait"}
    res = requests.post(
        "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
        headers=headers,
        json={"input": {"prompt": prompt, "aspect_ratio": "1:1"}},
        timeout=65,
    )
    res.raise_for_status()
    prediction = res.json()

    # "Prefer: wait" usually completes synchronously for a fast model
    # like flux-schnell, but if it times out before finishing, fall back
    # to polling rather than treating an unfinished prediction as a
    # failure — same "don't crash on a partial state" philosophy as the
    # rest of this pipeline.
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
    return Image.open(io.BytesIO(img_res.content)).convert("RGB").resize((CANVAS_SIZE, CANVAS_SIZE))


def generate_graphic(headline: str, brand: dict) -> bytes:
    """Builds a branded square graphic. Tries the AI-illustrated
    background first; falls back to a solid brand-color background if
    Gemini is unavailable or errors — a temporary image-API hiccup
    should never be able to break the whole pipeline. No real photos
    anywhere, either way."""
    accent_color = hex_to_rgb(brand["accent_color"])
    text_color = hex_to_rgb(brand["secondary_color"])

    try:
        img = generate_ai_background(headline)
        print("  Using AI-generated illustrated background")
    except Exception as e:
        print(f"  Warning: AI background generation failed ({e}) — falling back to solid color")
        img = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), hex_to_rgb(brand["primary_color"]))

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

    if REGEN_POST_ID:
        # Regeneration — revising an existing draft with feedback, not
        # creating a new row. The existing post is the source of truth
        # for what was there before; feedback is what changes.
        print(f"Regenerating post {REGEN_POST_ID} with feedback: {REGEN_FEEDBACK}")
        cur.execute("select caption from mw_social_posts where id = %s and tenant_id = %s", (REGEN_POST_ID, TENANT_ID))
        row = cur.fetchone()
        if not row:
            print(f"ERROR: post {REGEN_POST_ID} not found for tenant {TENANT_ID}.", file=sys.stderr)
            sys.exit(1)
        previous_caption = row[0]
        content = generate_content_with_claude(context, previous_caption=previous_caption, feedback=REGEN_FEEDBACK)
    else:
        content = generate_content_with_claude(context)

    print("Asking Claude for caption + headline...")
    print(f"  Headline: {content['graphic_headline']}")

    print("Generating branded graphic...")
    image_bytes = generate_graphic(content["graphic_headline"], brand)

    print("Uploading image...")
    image_url = upload_image(image_bytes)
    print(f"  {image_url}")

    reasoning = "Based on: " + "; ".join(f"{k}={v}" for k, v in context.items() if v is not None) if any(context.values()) else "No standout data this run — general seasonal content."
    if REGEN_POST_ID:
        reasoning = f"Revised per feedback: \"{REGEN_FEEDBACK}\". " + reasoning

    if REGEN_POST_ID:
        cur.execute(
            """update mw_social_posts
               set caption = %s, image_url = %s, reasoning = %s, status = 'pending_review', error = null, reviewed_at = null
               where id = %s and tenant_id = %s""",
            (content["caption"], image_url, reasoning, REGEN_POST_ID, TENANT_ID),
        )
    else:
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
