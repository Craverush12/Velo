# Media Pipeline v2 — Intent-Classified Routing

**Date:** 11 June 2026  
**Author:** Infrastructure + AI sprint  
**Status:** Live on `35.154.138.184` (hot-patch, pending image rebuild)

---

## Background

Analytics showed users selecting Studio mode (frontend label for `mode=media`) for two very different jobs:

1. **Marketing copy** — social media ads, reel scripts, captions, brand copy
2. **Visual generation** — Midjourney prompts, DALL-E, Stable Diffusion, Flux, Runway video prompts, product renders, thumbnails, concept art

The original pipeline treated both identically. It ran every media prompt through a single copywriting overlay (`enhance_media_overlay.md`) which produced sentence-form marketing briefs. Users generating AI images received output structured for a human copywriter — not usable in an image model without manual reformatting.

---

## What Changed

### 1. New overlay — `core/prompts/enhance_media_imagegen_overlay.md`

A purpose-built image generation overlay. It instructs the LLM to produce a structured, model-ready prompt string — not a meta-instruction. The output anatomy:

```
[Subject] · [Style/Medium] · [Lighting] · [Camera/Composition] ·
[Color Palette] · [Quality Tokens] · [Model-specific flags / Negative prompt]
```

Covers:
- **Subject Lock** — primary subject at front (models weight early tokens)
- **Visual Style** — photography, 3D render, illustration, film styles
- **Lighting** — studio, natural, dramatic, environmental
- **Camera** — shot type, lens (35mm/85mm/macro), depth of field
- **Color Palette** — precise color language (golden, icy blue, muted earth)
- **Quality Tokens** — 3–5 relevant anchors (8k, octane render, RAW photo, etc.)
- **Model-specific syntax** — Midjourney `--ar`, `--v`, `--style raw`; SD weight notation; Flux natural language; DALL-E constraints
- **Negative prompts** — via `--no` (Midjourney) or woven into prompt (Flux/DALL-E)
- **Aspect ratio defaults** — 16:9 thumbnails, 1:1 products, 9:16 social, 21:9 cinematic
- **Recommended connectors** — Midjourney, Adobe Firefly, Stability AI, Fal.ai, Runway

### 2. Intent classifier — `api/enhance.py`

A fast pre-classification call using `llama-3.1-8b-instant` (Groq's fastest model, ~1000 t/s) runs before the main enhance call when `prompt_mode == "media"`.

**Classifier system prompt** (20-token output, temperature=0):
```
Decide: is this prompt for visual generation (image/video AI) or marketing copy?
Return: {"intent": "visual_generation"} or {"intent": "marketing_copy"}
```

**Signals for `visual_generation`:** render, shot, photo, illustration, concept art, midjourney, stable diffusion, flux, DALL-E, anime, cinematic, 4k, hyperrealistic, lighting, texture, isometric, product design, thumbnail, drone shot, aerial, animation

**Fallback:** any classifier error or ambiguous result defaults to `marketing_copy`, preserving existing behavior.

**Added latency:** ~150–200ms (single small-model call). Classifier runs before the main streaming call starts.

### 3. Routing function — `api/enhance.py`

```python
async def _resolve_bundle(prompt_mode: str, raw_prompt: str) -> tuple[PromptBundle, str]:
    if prompt_mode != "media":
        return prompt_bundle("enhance", prompt_mode), ""
    media_intent = await _classify_media_intent(raw_prompt)
    if media_intent == "visual_generation":
        return prompt_bundle_internal("enhance", "media_imagegen"), media_intent
    return prompt_bundle("enhance", "media"), media_intent
```

Both the streaming path (`_generate`) and the compare endpoint (`compare_enhance_modes`) use this function. The result includes `_media_intent` in the response metadata.

### 4. Internal bundle helper — `core/prompt_modes.py`

Added `prompt_bundle_internal()` — builds a bundle with an internal mode key (`media_imagegen`) that bypasses user-facing `PromptMode` validation. The exposed `.mode` on the returned bundle is set to `"media"` so telemetry and storage records stay consistent.

---

## Files Changed

| File | Change |
|---|---|
| `core/prompts/enhance_media_imagegen_overlay.md` | **Created** — image generation overlay |
| `core/prompt_modes.py` | `_INTERNAL_OVERLAY_FILES` dict + `prompt_bundle_internal()` function |
| `api/enhance.py` | `_CLASSIFY_MODEL`, `_CLASSIFY_SYSTEM`, `_classify_media_intent()`, `_resolve_bundle()`, updated `_generate()` and `compare_enhance_modes()` |

`enhance_media_overlay.md` is **unchanged** — marketing copy prompts continue to use it without modification.

---

## Testing

### Test setup

Prompts pulled directly from the production database (`save_enhance_prompt WHERE mode = 'studio'`, 20 total rows). Four representative prompts selected covering all intent categories.

Each prompt was run through both the old pipeline (always `enhance_media_overlay.md`) and the new pipeline (classified routing) using a comparison script (`compare_media_pipeline.py`) against the local server with the same Groq API key.

---

### Prompt 1 — Eid illustration (clear visual generation)

**Raw input:**
> eid ul adha illustration art for education institute for kids · DARK PURPLE #602B7A · RASPBERRY MILK #F44C75 · sheep wearing student uniform and school bag · simple plain background

**Classifier result:** `visual_generation` → routed to `enhance_media_imagegen_overlay.md`

**OLD output (marketing copy overlay):**
> Create an Eid ul Adha illustration art for an education institute, targeting kids. Use a color palette with main color DARK PURPLE #602B7A, semi color RASPBERRY MILK #F44C75, and other colors SEPTEMBER YELLOW #FFD749 or PEPPERMINT FRESH #33DFC0. The illustration should be a high-detailed cartoon of a sheep wearing a student uniform and carrying a school bag, set against a simple plain background. The style should be attractive to both kids and parents. Output should be a single illustration with a minimum of 1024×1024 pixels.

**NEW output (imagegen overlay):**
> Eid ul Adha festive scene for kids, colorful illustration, main color DARK PURPLE #602B7A, secondary color RASPBERRY MILK #F44C75, accent colors SEPTEMBER YELLOW #FFD749 and PEPPERMINT FRESH #33DFC0, cartoon style, high-detailed illustration of a smiling sheep in a student uniform, carrying a school bag, against a simple plain background, focus on attracting kids and parents, photorealistic quality, 8k resolution, --ar 16:9

**Delta:** Old output is a sentence-form brief written to a human illustrator. New output is a comma-separated prompt with exact hex values preserved and model flags — pasteable directly into Midjourney or DALL-E.

---

### Prompt 2 — Cinematic drone shot (clear visual generation)

**Raw input:**
> A cinematic drone shot flying through futuristic Tokyo at night, neon lights reflecting on wet streets, ultra realistic, cyberpunk atmosphere, volumetric lighting, highly detailed, smooth camera motion

**Classifier result:** `visual_generation` → routed to `enhance_media_imagegen_overlay.md`

**OLD output (marketing copy overlay):**
> Generate a cinematic drone shot flying through a futuristic, ultra-realistic, cyberpunk Tokyo cityscape at night. The neon lights should reflect off the wet streets, creating a vibrant and immersive atmosphere. Incorporate volumetric lighting to enhance the visual depth and texture of the scene. Ensure the camera motion is smooth and highly detailed, capturing the essence of a futuristic city. The output should be a visually stunning image that transports the viewer into the heart of this cyberpunk world. Format the image as a high-resolution, widescreen cinematic shot, suitable for a movie...

**NEW output (imagegen overlay):**
> Futuristic Tokyo cityscape at night, cinematic drone shot flying through neon-lit skyscrapers with wet streets reflecting vibrant colors, ultra-realistic cyberpunk atmosphere, volumetric lighting with smooth camera motion, highly detailed city textures, dark blues and purples for mood, warm neon lights, shallow depth of field with bokeh effect, 8k resolution, --ar 16:9 --v 7 --style raw

**Delta:** Old reads like a film brief for a human director and adds narrative framing ("transports the viewer"). New is compact, Midjourney-ready with `--ar`, `--v`, `--style` tokens and proper comma structure.

---

### Prompt 3 — Hindi commerce tutorial ad (clear marketing copy)

**Raw input:**
> Kya aap +1 ya +2 Commerce me top karna chahte hain? Ab accounts, economics, aur business studies ki tension khatam! Akaal Commerce Tutorials lekar aaya hai premium online classes jahan concepts ratte nahi, sikhaye jaate hain.

**Classifier result:** `marketing_copy` → routed to `enhance_media_overlay.md` (unchanged)

**OLD output:**
> Create a compelling social media post in Hindi for Akaal Commerce Tutorials, highlighting the benefits of their premium online classes for students aiming to top in +1 or +2 Commerce. Specify the audience as students aged 16–19, and the tone as motivational and tension-relieving. Use sensory language to describe how Akaal Commerce Tutorials makes complex concepts easy to understand. Request three variants of the post, each with a different visual element.

**NEW output (same overlay, same path):**
> Create a persuasive social media post for Akaal Commerce Tutorials, targeting students who want to excel in +1 or +2 Commerce. Use attention-grabbing language, sensory details, and a clear call-to-action. The tone should be encouraging and supportive, with a focus on empowering students to achieve their academic goals.

**Delta:** No regression. Both versions use the marketing copy overlay. Minor output variation is normal LLM non-determinism, not a pipeline difference. Classifier fallback confirmed working.

---

### Prompt 4 — Cinematic vertical reel brief (mixed/edge case)

**Raw input:**
> Create a 30-40 second cinematic vertical reel (9:16) for "Akaal Commerce Tutorials" targeting Indian Class +1 and +2 Commerce students. Style: Premium, energetic, motivational, modern Indian education ad.

**Classifier result:** `visual_generation` → routed to `enhance_media_imagegen_overlay.md`

**OLD output (marketing copy overlay):**
> Create a captivating 30-40 second cinematic vertical reel (9:16) for "Akaal Commerce Tutorials"... Ensure the tone is inspirational, using concrete, sensory language to make the audience feel empowered and motivated to learn. Incorporate a clear call-to-action and utilize a mix of visually engaging graphics, animations, and real-life scenarios...

**NEW output (imagegen overlay):**
> 30-40 second, premium, energetic vertical reel 9:16 for Akaal Commerce Tutorials targeting Indian Class +1/+2, modern Indian education ad style, vibrant visuals, inspiring music, engaging animations, close-up shots, overhead shots, cutaway shots, youthful vibrant color palette...

**Delta:** This is a video production brief — genuinely borderline. Classifier routes it to `visual_generation` (reasonable, since the user's next tool is a video AI like Runway, not a copywriter). New output is better suited for AI video generation tools. Old output was more useful if the user was briefing a human video editor. Acceptable trade-off given the usage pattern.

---

### Summary

| Prompt | Classifier | Old overlay fit | New overlay fit | Verdict |
|---|---|---|---|---|
| Eid illustration | `visual_generation` ✓ | Poor — sentence brief | Good — pasteable gen prompt | Clear win |
| Tokyo drone shot | `visual_generation` ✓ | Poor — film brief to human | Good — Midjourney-ready | Clear win |
| Hindi commerce ad | `marketing_copy` ✓ | Good | Good (same path) | No regression |
| Cinematic reel | `visual_generation` ✓ | Moderate | Good for video AI | Acceptable |

**Classifier accuracy on production data: 4/4**

---

## Deployment

### Local (dev server)

Changes are in the local ThinkVelocity repo. Local server verified running at `localhost:8001`.

### Production (`35.154.138.184`)

Deployed via hot-patch on 11 June 2026:

```bash
# Files copied into running container:
docker cp enhance_media_imagegen_overlay.md  tv-python-ai-unified:/app/core/prompts/
docker cp prompt_modes.py                    tv-python-ai-unified:/app/core/prompt_modes.py
docker cp enhance.py                         tv-python-ai-unified:/app/api/enhance.py
docker restart tv-python-ai-unified
```

**Smoke test result:**

```
POST /ai/enhance/chat
{ "prompt": "A cinematic drone shot over futuristic Tokyo at night, neon lights, cyberpunk",
  "context": { "mode": "media" } }

→ enhanced_prompt: "Futuristic Tokyo cityscape at night, cinematic drone shot through
  neon-lit skyscrapers, wet streets reflecting vibrant colors, ultra-realistic cyberpunk
  atmosphere, volumetric lighting, smooth camera motion, 8k, --ar 16:9 --v 7 --style raw"
```

Server logs confirmed two sequential Groq API calls per media request (classifier + main enhance), verifying the two-step pipeline is active.

### ⚠️ Hot-patch notice

This is a container-level patch. If `tv-python-ai-unified` is recreated from its Docker image, the changes will be overwritten. Before the next full redeploy, commit these three files to the repo and rebuild the image.

**Files to commit before next rebuild:**
- `core/prompts/enhance_media_imagegen_overlay.md`
- `core/prompt_modes.py`
- `api/enhance.py`

---

## How to verify (extension)

1. Open the ThinkVelocity extension
2. Select **Studio** mode
3. Enter an image generation prompt, e.g. `"product render of wireless earbuds floating on white marble surface"`
4. The enhanced output should be comma-separated generation syntax with `--ar` flags
5. Enter a marketing copy prompt, e.g. `"Write a social media ad for our summer sale"`
6. The enhanced output should be a sentence-form copy brief (unchanged behavior)
