# Lessons Learned — GH-57: Dynamic IPAdapter Workflow Stripping

**Branch:** `fix/gh-57-dynamic-workflow-stripping`
**Commit:** `3966ce8`
**Date:** 2026-03-19

## What was built

- **`_strip_ipadapter_nodes(workflow)`** classmethod in `comfyui/comfyui_client.py`:
  - Deep-copies workflow to avoid in-place mutation
  - Removes nodes `10` (IPAdapter), `12` (LoadImage), `14` (IPAdapterUnifiedLoader)
  - Rewires node `1` (KSampler) model input from `["10", 0]` → `["3", 0]` (CheckpointLoaderSimple)
- **`inject_prompt()`** now calls `_strip_ipadapter_nodes()` when `reference_image is None`
- **Class constants**: `_IPADAPTER_NODES`, `_KSAMPLER_NODE`, `_BASE_MODEL_NODE` for node ID management
- **4 new tests** in `TestIPAdapterDynamicStripping` (45/45 targeted suite pass)
- **Real repro validated**: video `8uP2IrP3IG8` shot `S03` — 3 variant PNGs generated successfully

## Root cause

The `Storyboarder_api.json` workflow contains an IPAdapter conditioning path (nodes 10→12→14) that requires a valid reference image file on the ComfyUI server. When `reference_image` was `None`, `inject_prompt()` simply skipped updating node `12`'s image field, but the node remained in the submitted workflow with its placeholder filename `"reference_montage.png"`. ComfyUI's validation rejected this with HTTP 400 `prompt_outputs_failed_validation` at node 12.

## Key lessons

1. **Skipping a node update ≠ removing the node**: The previous code's `if reference_image is not None` guard only prevented overwriting the filename — it didn't address the structural problem that the LoadImage node still referenced a nonexistent file. The fix removes the entire IPAdapter subgraph rather than leaving orphaned nodes.

2. **`copy.deepcopy` is the correct isolation boundary**: `inject_prompt()` already mutates the workflow dict in-place (setting prompts, seed, etc.). The stripping helper returns a deep copy so the caller's original workflow is not modified, which matters for the e2e `generate_image()` path where the workflow object might be reused or inspected after submission.

3. **Graph rewiring follows the dependency chain**: Node `1` (KSampler) → `10` (IPAdapter) → `14` (IPAdapterUnifiedLoader) → `3` (CheckpointLoaderSimple). When removing the middle nodes, the rewire target is the terminal dependency `3`, not an intermediate node. This was directly readable from the workflow JSON.

4. **RED phase had 3 FAIL, 1 PASS**: The backward-compat test (`test_preserves_ipadapter_nodes_with_reference`) passed immediately — expected since it exercises the existing code path. The e2e test initially had a mock scoping bug (`assert_called_once` on a non-mock after `with` block exit), caught and fixed before GREEN.

5. **Real repro confirmed the fix end-to-end**: The same video/shot combination (`8uP2IrP3IG8`/`S03`) that previously failed with HTTP 400 now generates 3 variant storyboard PNGs. Reference Images count was 0, confirming the stripped workflow path was exercised.

6. **Implementation was minimal**: 3 class constants + 1 classmethod (8 lines of logic) + 4-line change in `inject_prompt()`. The `deepcopy` + `pop` + rewire pattern is self-documenting.

7. **Node ID constants enable future extensibility**: If the workflow adds more IPAdapter-dependent nodes, they can be added to `_IPADAPTER_NODES` without changing the stripping logic. The constants also serve as documentation of the workflow's graph structure.

## Test count progression

- GH-56 queue observability: 41 total in targeted suite
- GH-57 dynamic stripping: 45 total (4 new), 0 regressions

## Next steps

- **P2-A**: Wire Airtable Frames table → `reference_frames_by_shot` mapping (GH-57 Option B)
- **P2-B**: Add pre-submission workflow validation to detect missing required inputs
- **P2-C**: Optional `--force-ipadapter` flag to fail loudly instead of stripping
