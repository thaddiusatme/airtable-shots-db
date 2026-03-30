# GH-53 Airtable Frame IPAdapter Wiring — Lessons Learned

## TDD Iteration Summary

**Branch**: `feature/gh-53-airtable-frame-ipadapter-wiring`  
**Commit**: `1c9e67b`  
**Date**: 2026-03-19  
**Status**: ✅ P0-T1 Complete (Frame URL extraction + wiring)

---

## What Was Built

### Core Functionality
- **`fetch_shot_frame_urls(shot_fields)`** in `publisher/storyboard_handoff.py`
  - Extracts URLs from Airtable `Scene Start` and `Scene End` attachment fields
  - Returns list of `{"url": str, "role": "composition"}` dicts
  - Preserves scene order (Scene Start before Scene End)
  - Graceful handling of missing fields, empty arrays, malformed attachments

### Integration Points
- **`scripts/validate_storyboard_handoff.py`** updated to:
  - Import and use `fetch_shot_frame_urls()`
  - Build `reference_frames_by_shot` mapping from shot records
  - Pass frame URLs to `build_storyboard_series()` for IPAdapter conditioning
  - Log frame count per shot for observability

### Test Coverage
- **9 unit tests** in `TestFetchShotFrameUrls` covering all edge cases:
  - Both fields present, single field only, missing fields, empty arrays
  - Multiple attachments per field, missing URLs, order preservation
- **2 integration tests** in `TestStoryboardSeriesWithFrameUrls`:
  - Series building with frame URLs, backward compatibility without frames

---

## Key Lessons

### 1. RED Phase Design Clarity
- **ImportError is the cleanest RED signal**: Adding `fetch_shot_frame_urls` to imports caused immediate, unambiguous test failures before any test body ran.
- **Test-first drove robust API design**: Writing tests for edge cases (missing fields, empty arrays, malformed attachments) forced comprehensive error handling in the implementation.

### 2. Airtable Attachment Field Handling
- **Attachment fields are arrays of objects**: Each Scene Start/End field contains `[{id, url, filename, ...}]` objects, not simple strings.
- **URL field is optional**: Some attachments may lack `url` (e.g., broken uploads), requiring defensive `attachment.get("url")` checks.
- **Field presence vs emptiness**: Need to distinguish between missing fields (`shot_fields.get("Scene Start")` returns `None`) vs empty arrays (`[]`).

### 3. Data Structure Consistency
- **Role field standardization**: All frame dicts use `"role": "composition"` to match IPAdapter expectations from GH-57.
- **Order preservation matters**: Scene Start attachments should precede Scene End for temporal consistency in conditioning.
- **List return type**: Always return a list (empty vs `None`) for consistent downstream handling.

### 4. Integration Patterns
- **Mapping by shot label**: `reference_frames_by_shot[shot_label]` pattern matches existing `build_storyboard_series()` contract.
- **Observability logging**: Adding frame count logging per shot (`"S03: 2 frame URLs"`) provides immediate operational visibility.
- **Backward compatibility**: `build_storyboard_series()` works without `reference_frames_by_shot` parameter, ensuring existing code continues to work.

### 5. Test Organization
- **Separate unit vs integration concerns**: Unit tests focus on `fetch_shot_frame_urls()` edge cases; integration tests verify wiring with `build_storyboard_series()`.
- **Reuse existing fixtures**: Leveraged `CLEAN_SHOT` and `MINIMAL_SHOT` fixtures from GH-33 tests for consistency.
- **Import management**: Added function to main import block to avoid redundant per-test imports.

---

## Technical Decisions

### Why `fetch_shot_frame_urls()` Lives in `storyboard_handoff.py`
- **Domain proximity**: Close to `build_storyboard_payload()` which consumes the frame URLs
- **Reusability**: Can be used by other storyboard-related scripts beyond validation
- **Avoid circular dependencies**: Keeps function in consumer module rather than data source modules

### Why Role is Always "composition"
- **IPAdapter contract**: GH-57 established "composition" as the standard role for visual conditioning
- **Future extensibility**: Could add "style", "content", etc. later if needed
- **Simplicity**: Single role reduces complexity for initial implementation

### Why Scene Order Matters
- **Temporal conditioning**: IPAdapter may give different weight to first vs last frames
- **Predictable behavior**: Consistent ordering makes debugging and testing easier
- **User expectations**: Scene Start naturally comes before Scene End in video timelines

---

## Extension Points Identified

### P1-T2: Frame Attachment Edge Cases
- **Partial frame downloads**: Handle 404/timeout errors gracefully with fallback to prompt-only
- **Frame validation**: Check image dimensions, format, size before conditioning
- **Alternative attachment fields**: Support other frame fields if added to schema

### P1-T3: Multi-Shot Validation
- **Frame availability statistics**: Report % of shots with frames across entire video
- **Quality comparison**: Side-by-side comparison of frame-conditioned vs prompt-only outputs
- **Performance impact**: Measure generation time differences with vs without frames

### P2: Advanced Frame Selection
- **Intelligent sampling**: Instead of even sampling, select keyframes based on scene content
- **Frame quality scoring**: Prioritize higher-quality frames (resolution, clarity)
- **Temporal clustering**: Group similar frames to avoid redundant conditioning

---

## Next Steps

### Immediate (P0-T3)
- **End-to-end validation**: Run `validate_storyboard_handoff.py` with video `8uP2IrP3IG8` shot `S03`
- **Compare outputs**: Generate with and without frame URLs to assess visual fidelity improvement
- **IPAdapter verification**: Confirm ComfyUI workflow receives reference images without HTTP 400 errors

### Short-term (P1)
- **Frame download observability**: Add logging for successful/failed frame downloads in montage generation
- **Error handling**: Graceful degradation when frame URLs are inaccessible
- **Batch validation**: Test across multiple shots and videos to ensure robustness

### Long-term (P2)
- **ControlNet integration**: Explore edge-based conditioning as alternative to IPAdapter
- **Frame selection strategy**: Implement intelligent frame selection beyond even sampling
- **IPAdapter weight tuning**: Experiment with different weight values for style vs content balance

---

## Test Count Progression

- **Iteration start**: 455 existing tests in `test_storyboard_handoff.py`
- **Added**: 11 new tests (9 unit + 2 integration)
- **Total**: 466 tests (+2.4% coverage)
- **Pass rate**: 100% for new functionality, pre-existing unrelated failure unaffected

---

## Operational Impact

### Script Changes
- **`validate_storyboard_handoff.py`** now shows frame attachment status per shot
- **No breaking changes**: Existing command-line interface unchanged
- **Enhanced observability**: Operators can see which shots have frames available

### Performance Considerations
- **Minimal overhead**: `fetch_shot_frame_urls()` processes small attachment arrays (<10 items typically)
- **No network calls**: Only processes existing Airtable data, no external requests
- **Memory efficient**: Processes shots sequentially, no large data structures

---

## Files Modified

1. **`publisher/storyboard_handoff.py`** - Added `fetch_shot_frame_urls()` function
2. **`tests/test_storyboard_handoff.py`** - Added 11 new tests across 2 test classes
3. **`scripts/validate_storyboard_handoff.py`** - Integrated frame URL extraction and wiring

---

**Result**: GH-53 P0-T1 complete with robust frame URL extraction, full test coverage, and integration into storyboard validation pipeline. Ready for end-to-end IPAdapter conditioning validation.
