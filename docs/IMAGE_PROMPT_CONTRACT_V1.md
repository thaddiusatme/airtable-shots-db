# Image Prompt Contract v1 — SDXL/ComfyUI Per-Shot Prompt Assembler

**Status:** v1.1 (GH-32)  
**Module:** `publisher/prompt_assembler.py`  
**Assembler version:** `1.1`

---

## Overview

Transforms enriched shot data (Airtable field names from the LLM enrichment pipeline) into a structured prompt dict suitable for SDXL/ComfyUI image generation. Designed for deterministic, repeatable output with graceful handling of imperfect enrichment data.

---

## Inputs

### Required fields

| Airtable Field | Type   | Description |
|---------------|--------|-------------|
| `Shot Label`  | string | Shot identifier (e.g., "S03") |
| `Subject`     | string | Primary subject description |
| `Setting`     | string | Scene/environment description |

### Optional fields (enrichment-derived)

| Airtable Field         | Type        | Used in section    | Omission rule |
|-----------------------|-------------|-------------------|---------------|
| `Shot Type`           | string      | `camera`          | Omit if "Other" or missing |
| `Camera Angle`        | string      | `camera`          | Omit if "Other" or missing |
| `Lighting`            | string      | `lighting`        | Omit if "Other" or missing |
| `Movement`            | list[str]   | (not used in v1)  | — |
| `How It Is Shot`      | string      | `composition`     | Filter boilerplate + uninformative |
| `Shot Function`       | string      | (not used in v1)  | — |
| `On-screen Text`      | string      | `constraints`     | Omit if empty |
| `Frame Progression`   | string      | `context`         | Filter boilerplate + uninformative |
| `Production Patterns` | string      | `style`           | Filter boilerplate + uninformative |
| `Recreation Guidance` | string      | `context`         | Filter boilerplate + uninformative |

### Reference frames (optional parameter)

```python
reference_frames: list[dict] | None
# Each dict: {"url": "https://...", "role": "composition"}
# Role defaults to "composition" if absent
```

---

## Output structure

```python
{
    "positive_prompt": str,       # Comma-separated prompt string
    "negative_prompt": str,       # Baseline negative prompt
    "prompt_sections": {          # Structured breakdown
        "subject": str,           # Present if non-empty
        "setting": str,           # Present if non-empty
        "composition": str,       # From How It Is Shot (if non-boilerplate)
        "camera": str,            # Shot Type + Camera Angle (if not Other)
        "lighting": str,          # Lighting value (if not Other)
        "style": str,             # From Production Patterns (if non-boilerplate)
        "context": str,           # Frame Progression + Recreation Guidance
        "constraints": str,       # On-screen text (if present)
    },
    "reference_images": [         # Empty list if no frames provided
        {"url": str, "role": str}
    ],
    "metadata": {
        "shot_label": str,
        "assembler_version": str, # Currently "1.1"
        "omissions": [str],       # Human-readable list of what was dropped
    }
}
```

**Note:** `prompt_sections` only includes keys with non-empty values. As of v1.1, `subject` and `setting` are excluded when empty (unenriched shots).

---

## Omission rules

### Controlled vocabulary fields

Fields with a value of `"Other"` are **omitted** from the prompt entirely. Rationale: GH-31 audit showed Camera Angle and Lighting frequently return "Other" (6/16 shots in one video). Including "Other" in an SDXL prompt adds noise without information.

Tracked in `metadata.omissions` as:
- `"Camera Angle: Other (low-signal, omitted)"`
- `"Lighting: Other (low-signal, omitted)"`

### Narrative boilerplate

Known boilerplate phrases are detected and filtered:
- "No pattern information provided."
- "Not enough information to determine..."
- "No relevant information available/provided"
- "Cannot be determined"
- "Insufficient data/information"

Tracked in `metadata.omissions` as:
- `"Frame Progression: boilerplate filtered"`
- `"Production Patterns: boilerplate filtered"`

### Short uninformative narratives (v1.1)

Single-word values that are controlled-vocab leaks or non-informative placeholders are filtered from narrative fields. Discovered via live validation against real Airtable data.

Filtered values: `other`, `yes`, `no`, `n/a`, `na`, `none`, `static`, `unknown`

Examples from real data:
- `How It Is Shot: "Other"` — controlled-vocab leak, not a composition description
- `Frame Progression: "Yes"` — uninformative single-word response
- `Production Patterns: "Static"` — not a useful style descriptor

Tracked in `metadata.omissions` as:
- `"How It Is Shot: uninformative value 'Other' filtered"`
- `"Frame Progression: uninformative value 'Yes' filtered"`

### Empty/missing fields

Missing or empty fields are silently skipped (no omission log entry — these are expected for minimal shots).

---

## Positive prompt composition

Sections are concatenated in a **stable order** with comma-space separators:

```
subject, setting, composition, camera, lighting, style, context, constraints
```

Only non-empty sections are included. This produces prompts like:

```
person sitting cross-legged in a tent, forest clearing at dusk, 
Tripod-mounted medium shot shallow depth of field, medium shot eye-level angle,
natural-soft lighting, Rule of thirds warm color grading golden hour tones, ...
```

---

## Negative prompt

Baseline (v1):
```
blurry, deformed, low quality, watermark, text overlay, out of focus, oversaturated, jpeg artifacts
```

**Open question:** Shot-derived negative exclusions (e.g., if Setting is "outdoor" → add "indoor" to negative) are deferred to v2. The baseline covers universal SDXL quality issues.

---

## Examples

### Example 1: Clean shot (all fields, no Other)

**Input:**
```python
shot_fields = {
    "Shot Label": "S03",
    "Subject": "person sitting cross-legged in a tent",
    "Setting": "forest clearing at dusk",
    "Shot Type": "Medium",
    "Camera Angle": "Eye-level",
    "Lighting": "Natural-soft",
    "How It Is Shot": "Tripod-mounted medium shot, shallow depth of field",
    "Production Patterns": "Rule of thirds, warm color grading",
    "Frame Progression": "Static composition, subject shifts gaze",
    "Recreation Guidance": "Use a 50mm lens at f/2.8, shoot during golden hour",
}
```

**Output:**
```python
{
    "positive_prompt": "person sitting cross-legged in a tent, forest clearing at dusk, Tripod-mounted medium shot, shallow depth of field, medium shot, eye-level angle, natural-soft lighting, Rule of thirds, warm color grading, Static composition, subject shifts gaze; Use a 50mm lens at f/2.8, shoot during golden hour",
    "negative_prompt": "blurry, deformed, low quality, watermark, text overlay, out of focus, oversaturated, jpeg artifacts",
    "prompt_sections": {
        "subject": "person sitting cross-legged in a tent",
        "setting": "forest clearing at dusk",
        "composition": "Tripod-mounted medium shot, shallow depth of field",
        "camera": "medium shot, eye-level angle",
        "lighting": "natural-soft lighting",
        "style": "Rule of thirds, warm color grading",
        "context": "Static composition, subject shifts gaze; Use a 50mm lens at f/2.8, shoot during golden hour"
    },
    "reference_images": [],
    "metadata": {
        "shot_label": "S03",
        "assembler_version": "1.1",
        "omissions": []
    }
}
```

### Example 2: Other-heavy shot (Camera Angle + Lighting = Other, boilerplate narratives)

**Input:**
```python
shot_fields = {
    "Shot Label": "S07",
    "Subject": "laptop screen showing code editor",
    "Setting": "dimly lit home office",
    "Shot Type": "Close-up",
    "Camera Angle": "Other",
    "Lighting": "Other",
    "How It Is Shot": "Handheld close-up of laptop screen",
    "Frame Progression": "No pattern information provided.",
    "Production Patterns": "Not enough information to determine production patterns.",
    "Recreation Guidance": "Point camera directly at laptop screen",
}
```

**Output:**
```python
{
    "positive_prompt": "laptop screen showing code editor, dimly lit home office, Handheld close-up of laptop screen, close-up shot, Point camera directly at laptop screen",
    "negative_prompt": "blurry, deformed, low quality, watermark, text overlay, out of focus, oversaturated, jpeg artifacts",
    "prompt_sections": {
        "subject": "laptop screen showing code editor",
        "setting": "dimly lit home office",
        "composition": "Handheld close-up of laptop screen",
        "camera": "close-up shot",
        "context": "Point camera directly at laptop screen"
    },
    "reference_images": [],
    "metadata": {
        "shot_label": "S07",
        "assembler_version": "1.1",
        "omissions": [
            "Camera Angle: Other (low-signal, omitted)",
            "Lighting: Other (low-signal, omitted)",
            "Frame Progression: boilerplate filtered",
            "Production Patterns: boilerplate filtered"
        ]
    }
}
```

---

## Open questions (future iterations)

1. **Global video style layer**: Extract cross-shot style tokens (color palette, era, genre) from video-level metadata. Deferred — requires video-level enrichment (P2-A).

2. **Character reference roles**: The `reference_images` schema supports `role` values beyond `"composition"` (e.g., `"character"`, `"style"`). Role-specific handling deferred to v2.

3. **Negative prompt from shot context**: Shot-derived exclusions (indoor/outdoor inversion, specific artifacts) were evaluated during v1.1 live validation. Finding: enrichment data is not reliable enough for automated negative prompt derivation — Setting values like "Digital interface" or "Computer screen" don't map cleanly to exclusion terms. **Deferred to v2** pending higher-quality enrichment or manual negative prompt curation.

4. **Movement field usage**: Camera movement info (Static, Pan, etc.) is not used in v1 image prompts. May be relevant for video generation prompts (P2-C).

5. **Midjourney/ChatGPT single-string contract**: Tracked separately in GH-45. Would flatten `prompt_sections` into a single-line string with Midjourney-style weighting syntax.
