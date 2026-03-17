---
description: How to create/export a ComfyUI workflow for GH-51 auto-generation
---

# How-To: Create the ComfyUI piece (GH-51)

This doc is a practical guide for building/exporting a **ComfyUI SDXL workflow** that we can drive programmatically from this repo to generate storyboard PNGs.

The repo currently expects storyboard payloads shaped like:
- `positive_prompt` (variant-specific)
- `negative_prompt` (shared per shot)
- `width`, `height` (defaults: 1024×576)
- output path convention: `{output_dir}/{video_id}/{shot_label}/{shot_label}_variant_{A|B|C}.png`

We will use ComfyUI’s HTTP API pattern:
- `POST /prompt` (submit workflow)
- `GET /history/{prompt_id}` (poll until done)
- `GET /view?...` (download resulting image bytes)


## 1) Build a workflow in ComfyUI that already works manually

1. Start ComfyUI (usually `http://localhost:8188`).
2. Build or load a workflow that successfully generates an image (SDXL base is fine).
3. Confirm you can click **Queue Prompt** and get an output image.

**Important:** Do not proceed until manual generation works.


## 2) Ensure your workflow contains the nodes we need to parameterize

For a basic SDXL workflow, we need to be able to programmatically set:

- **Positive prompt text**
  - Typically a `CLIPTextEncode` node whose `inputs.text` is the positive prompt.

- **Negative prompt text**
  - Typically a second `CLIPTextEncode` node whose `inputs.text` is the negative prompt.

- **Width / Height**
  - Typically an `EmptyLatentImage` node with `inputs.width` and `inputs.height`.

- **Seed (optional but recommended)**
  - A sampler node (often `KSampler`) with `inputs.seed` or `inputs.noise_seed`.
  - This enables reproducibility and deterministic reruns.

- **A SaveImage / output node**
  - So the workflow produces an output image entry in ComfyUI history.


## 3) Export “API format” workflow JSON (this is the critical step)

We need the **API format** export (not the UI export).

### What you should click in the ComfyUI UI

In the ComfyUI top bar, look for one of:
- `Save (API Format)`
- `Export (API)`
- a Save/Export dropdown with an `API` option

Save the file to:

`airtable-shots-db/comfyui/workflows/Storyboarder_api.json`

### How to tell you exported the correct thing

Open the file and confirm it is **not empty** and contains a top-level `prompt` object.

A valid API-format workflow typically looks like:

```json
{
  "prompt": {
    "3": {"class_type": "CheckpointLoaderSimple", "inputs": {...}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "...", "clip": ["3", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "...", "clip": ["3", 1]}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 576, ...}},
    ...
  }
}
```

If you instead see `{}` (empty object), it is **not** a usable export.


## 4) Identify which node IDs to inject (positive/negative/width/height)

Once `Storyboarder_api.json` exists, we will:

- find the **positive** `CLIPTextEncode` node ID
- find the **negative** `CLIPTextEncode` node ID
- find the `EmptyLatentImage` node ID
- find the `SaveImage` node ID (for outputs)

**Why node IDs matter:** ComfyUI’s API workflow is a node graph keyed by IDs like `"6"`, `"7"`. Our Python code will deep-copy the JSON and only edit `inputs` values.


## 5) Best practices for our use case (storyboards + variants)

### A) Deep-copy the workflow template per generation

Never mutate a shared dict across variants/shots.

- Load the template JSON once.
- For each variant, `copy.deepcopy(template)`.

### B) Keep deterministic filenames out of ComfyUI, use our filesystem layout

We already have a deterministic output structure. Best practice is:
- download image bytes via `/view`
- write to our chosen `output_path`
- don’t rely on ComfyUI output naming

### C) Poll `/history` rather than guessing file paths

For each `prompt_id`:
- `GET /history/{prompt_id}`
- find the output image metadata under the node that produced images (commonly the `SaveImage` node)
- download via `/view?filename=...&subfolder=...&type=output`

### D) Seed control (recommended)

For storyboards, deterministic outputs help compare prompt tweaks.

- Use a stable seed per `{shot_label, variant}` (e.g., hash → int32)
- or allow `--seed` override

### E) Variant batching

Start simple:
- queue A, wait, download, write
- queue B, wait, download, write
- queue C, wait, download, write

Only batch later once the single-variant path is stable.


## 6) Common pitfalls

- **Empty export (`{}`)**
  - Usually means you didn’t use API-format export, or ComfyUI didn’t include the graph.

- **Wrong export type (UI graph export)**
  - UI exports may not be directly postable to `/prompt`.

- **Missing model / missing custom nodes**
  - If your workflow depends on missing checkpoints/nodes, `/prompt` can fail or outputs never appear.

- **Assuming linked-record IDs in Airtable formulas**
  - For storyboard validation, we now filter client-side to avoid Airtable formula brittleness.


## 7) What you do next

1. In ComfyUI, export API format workflow JSON to:
   `airtable-shots-db/comfyui/workflows/Storyboarder_api.json`

2. Confirm it contains a top-level `prompt` object.

3. Paste the first ~50 lines in chat (or tell me the node IDs) so I can wire:
   - positive prompt node ID
   - negative prompt node ID
   - width/height node ID
   - output image node ID

Then I’ll implement the GH-51 runner:
- generate PNG locally
- upload to R2
- create Storyboards table record with attachment URL
