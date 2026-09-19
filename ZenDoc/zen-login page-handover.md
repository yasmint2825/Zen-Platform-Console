# Zen — handover notes

`zen-platform-premium.html` is the single file to deploy. Everything below is
presentation only: no id, handler, form, route, Supabase call or workflow in the
application was edited at any point. Each build asserts that — it compares the
full set of `id=` and `on*=` attributes before and after, and fails if anything
is missing.

---

## 1. Image slots

Fourteen artwork areas are real photo slots. Paste a URL (or a `data:` URI) next
to a slot name in the `ZEN_MEDIA` object near the bottom of the file and the
photo appears there, colour-graded to match the rest of the page. Leave a slot
empty and its built-in artwork stays. A broken URL silently falls back — the
page cannot break because of this.

Every slot is lazy-loaded, decoded off the main thread, and has declared
dimensions so nothing shifts as images arrive.

| Slot | Size | Subject |
|---|---|---|
| `hero-backdrop` | 2400×1400 | Wide, low-detail interior at golden hour. Renders at 32% behind the hero — mood only, detail is wasted. |
| `hero-post-1` | 1080×1350 | Weekend braids — close crop of the finished work, warm window light. |
| `hero-post-2` | 1080×1350 | Birthday moment — celebration detail, warm bokeh. |
| `hero-post-3` | 1080×1350 | A fresh teen fade, barber's hands still in frame. |
| `studio-birthday` | 1080×1350 | Second frame from the birthday set. |
| `studio-weekend` | 1080×1350 | Salon chair, styling in progress. |
| `studio-video` | 1080×1350 | Video still — child in a cape mid-haircut, motion on the scissors. |
| `studio-referral` | 1080×1350 | Two customers leaving together, warm exterior light. |
| `studio-hours` | 1080×1350 | Shopfront at dusk, interior lights on. |
| `studio-ad` | 1080×1350 | Back-to-school — fresh cut and a backpack, morning light. |
| `persona-salon` | 1200×1500 | Salon owner on her phone between appointments. |
| `persona-clinic` | 1200×1500 | Clinic manager with a tablet at a calm front desk. |
| `persona-food` | 1200×1500 | Café owner at the pass during service. |
| `persona-services` | 1200×1500 | Service-business owner reviewing quotes on a laptop. |

### One campaign, one look

- **Light** — soft directional daylight, warm key from one side, open shadows. No on-camera flash.
- **Palette** — warm neutrals, terracotta, deep forest green, brass. The page grades everything slightly toward green-teal, so avoid heavily blue or magenta source files.
- **Depth** — shallow focus, subject sharp, background falling away.
- **People** — real working adults, 25–50, diverse, Gulf-relevant, mid-action rather than smiling at camera.
- **Composition** — leave the bottom third quiet. Captions sit there in HTML.
- **Never** — cartoon, 3D render, illustration, clipart, avatar, or fake UI text baked into the image.

### Prompt pattern (Flux / Midjourney / Ideogram)

Swap the subject line; keep everything after it identical so the set stays consistent.

```
[SUBJECT], candid documentary photograph, soft directional window light,
warm terracotta and deep green palette, shallow depth of field 85mm f/1.8,
fine film grain, natural skin tones, quiet uncluttered lower third,
premium commercial photography, --ar 4:5
```

For `hero-backdrop` use `--ar 16:9` and add `wide establishing shot, out of
focus, no subject in the centre`.

Export JPEG or WebP at 70–80% quality, under ~250KB each. Test one slot first:
set `studio-weekend`, reload, confirm the photo fades in with the caption still
legible over it.

---

## 2. What changed, and why

### Landing page

- **Photographic media system** — fourteen slots, a brand colour grade in soft-light blend so mixed sources land on one palette, film grain, bottom scrim for caption legibility, slow scale-in on load, Ken Burns on persona hover.
- **Captions moved out of SVG into HTML** — crisper, responsive, selectable, translatable, and they survive a photo being dropped behind them.
- **Flat gradient panels replaced** with lit multi-layer scenes; the vector doodles on persona cards are gone, replaced by graded panels carrying a live glass stat chip.
- **Four-figure band redesigned** — each cell gained a diagram: hourly activity bars with the late hours picked out, five app tiles collapsing into the Zen mark, a four-step setup line, an approval toggle beside a shield.
- **Workspace showcase spacing** — KPI values hold one line, labels share a baseline, laptop base shares the lid's angle, right-column rhythm evened out.
- **Navigation links** — the browser's default underline was showing on top of the design's own hover underline. Nav is clean at rest with a 1.5px underline growing on hover; body-copy links keep their underline, 3px off the baseline.

### Application

- **Brand bridge** across `#app` and `#onb` — Bricolage Grotesque on headings and figures, forest-green gradient primary buttons, sidebar with a green active accent, landing radii and hover depth on cards, green focus rings.
- **Shared chrome bridge** — sign in, sign up, password reset, in-app dialogs and toasts were outside those scopes and still used the old near-black primary. All now match.
- **New-user wizard** — the shell was branded earlier, but its content was not: goal cards now use the landing card language with a mint selected state and tinted icon tiles, the step rail runs green, Zen's speech bubble gained a hairline and gradient avatar, and the kicker/heading scale was lifted.
- **Command Centre** — four stacked chrome bars compressed to one quiet line (~80px recovered); one card language across KPI, money and opportunity cards; attention rows get numbered chips and hover; the opportunity card became a white card with a green accent edge instead of a flat slab.
- **"What Zen did in the last 24 hours"** now spans full width as a row of cards rather than a narrow stack with dead space beside it.

### Two structural decisions worth knowing

1. **Home is no longer pinned to `100dvh`.** A `1fr` row in the middle of the grid meant a quiet day left a hole above the activity strip, and a busy day risked clipping. Home flows naturally now and the page scrolls. The inbox keeps its bounded workspace deliberately.
2. **Amber count badges were left alone.** Amber means "this costs something" in your design system; repainting them green would quietly destroy that signal.

---

## 3. Known open items

- **Pricing is still placeholder** — `Free`, `—`, `Talk to us`. Set real figures before launch.
- **Global `.btn-p` is untouched.** It is green inside app, auth and dialogs. If a button renders somewhere not covered by those scopes it will still be near-black. One line to flip globally if you want it.
- **Photos are the remaining gap.** Until slots are filled the page shows crafted artwork, which is good but is not photography.
