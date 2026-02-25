"""Tests for scene merger module."""

from segmenter.scene_merger import merge_short_scenes


def test_merge_empty_scenes():
    """Empty input returns empty output."""
    assert merge_short_scenes([]) == []


def test_merge_single_scene():
    """Single scene is returned as-is with reindexed sceneIndex."""
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 3,
         "firstFrame": "a.png", "lastFrame": "b.png",
         "description": None, "transition": None},
    ]
    result = merge_short_scenes(scenes, min_duration=5.0)
    assert len(result) == 1
    assert result[0]["sceneIndex"] == 0
    assert result[0]["startTimestamp"] == 0
    assert result[0]["endTimestamp"] == 3


def test_merge_all_long_scenes():
    """Scenes all >= min_duration stay separate."""
    scenes = [
        {"sceneIndex": i, "startTimestamp": i * 10, "endTimestamp": (i + 1) * 10,
         "firstFrame": f"first_{i}.png", "lastFrame": f"last_{i}.png",
         "description": f"Scene {i}", "transition": None}
        for i in range(5)
    ]
    result = merge_short_scenes(scenes, min_duration=5.0)
    assert len(result) == 5
    for i, s in enumerate(result):
        assert s["sceneIndex"] == i
        assert s["startTimestamp"] == i * 10
        assert s["endTimestamp"] == (i + 1) * 10


def test_merge_short_scenes_combined():
    """Short scenes get merged with neighbors."""
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 2,
         "firstFrame": "a.png", "lastFrame": "b.png",
         "description": None, "transition": None},
        {"sceneIndex": 1, "startTimestamp": 2, "endTimestamp": 4,
         "firstFrame": "c.png", "lastFrame": "d.png",
         "description": None, "transition": None},
        {"sceneIndex": 2, "startTimestamp": 4, "endTimestamp": 6,
         "firstFrame": "e.png", "lastFrame": "f.png",
         "description": "Desc 2", "transition": None},
        {"sceneIndex": 3, "startTimestamp": 6, "endTimestamp": 15,
         "firstFrame": "g.png", "lastFrame": "h.png",
         "description": "Desc 3", "transition": "cut"},
    ]
    result = merge_short_scenes(scenes, min_duration=5.0)

    # Scenes 0-2 (0-6s) should merge into one (group < 5s until scene 2 added)
    # Scene 3 (6-15s, 9s) is long, but scene 2 is short so it gets absorbed
    # Result: group [0,1,2] = 0-6s, then scene 3 = 6-15s
    assert len(result) == 2

    assert result[0]["sceneIndex"] == 0
    assert result[0]["startTimestamp"] == 0
    assert result[0]["endTimestamp"] == 6
    assert result[0]["firstFrame"] == "a.png"
    assert result[0]["lastFrame"] == "f.png"
    assert result[0]["description"] == "Desc 2"

    assert result[1]["sceneIndex"] == 1
    assert result[1]["startTimestamp"] == 6
    assert result[1]["endTimestamp"] == 15
    assert result[1]["firstFrame"] == "g.png"
    assert result[1]["lastFrame"] == "h.png"


def test_merge_preserves_first_description():
    """First non-null description in group is kept."""
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 1,
         "firstFrame": "a.png", "lastFrame": "b.png",
         "description": None, "transition": None},
        {"sceneIndex": 1, "startTimestamp": 1, "endTimestamp": 2,
         "firstFrame": "c.png", "lastFrame": "d.png",
         "description": "Found it", "transition": None},
        {"sceneIndex": 2, "startTimestamp": 2, "endTimestamp": 3,
         "firstFrame": "e.png", "lastFrame": "f.png",
         "description": "Second desc", "transition": None},
    ]
    result = merge_short_scenes(scenes, min_duration=5.0)
    assert len(result) == 1
    assert result[0]["description"] == "Found it"


def test_merge_unsorted_input():
    """Scenes provided out of order are sorted first."""
    scenes = [
        {"sceneIndex": 2, "startTimestamp": 10, "endTimestamp": 20,
         "firstFrame": "e.png", "lastFrame": "f.png",
         "description": None, "transition": None},
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 3,
         "firstFrame": "a.png", "lastFrame": "b.png",
         "description": None, "transition": None},
        {"sceneIndex": 1, "startTimestamp": 3, "endTimestamp": 8,
         "firstFrame": "c.png", "lastFrame": "d.png",
         "description": None, "transition": None},
    ]
    result = merge_short_scenes(scenes, min_duration=5.0)
    # After sorting: 0-3, 3-8, 10-20
    # 0-3 is < 5s, absorb 3-8 → group is 0-8 (8s, >= 5)
    # 10-20 is >= 5s and group is already >= 5s → new group
    assert len(result) == 2
    assert result[0]["startTimestamp"] == 0
    assert result[0]["endTimestamp"] == 8
    assert result[0]["firstFrame"] == "a.png"
    assert result[1]["startTimestamp"] == 10
    assert result[1]["endTimestamp"] == 20


def test_merge_with_different_threshold():
    """Different min_duration changes merge behavior."""
    scenes = [
        {"sceneIndex": i, "startTimestamp": i * 3, "endTimestamp": (i + 1) * 3,
         "firstFrame": f"f{i}.png", "lastFrame": f"l{i}.png",
         "description": None, "transition": None}
        for i in range(6)
    ]
    # With min_duration=3, all scenes are exactly at threshold → no merging
    # (current_group_duration reaches 3 which is not < 3)
    # Actually: first scene is 0-3 (3s), group_duration = 3, which is NOT < 3
    # So next scene (3s) is short (3 < 5 would be true for 5, but 3 < 3 is false)
    # With threshold 3: each 3s scene starts a new group once prior is >= 3
    result_3 = merge_short_scenes(scenes, min_duration=3.0)

    # With min_duration=10, many scenes merge
    result_10 = merge_short_scenes(scenes, min_duration=10.0)
    assert len(result_10) < len(result_3)


def test_merge_does_not_mutate_input():
    """Original scenes list is not modified."""
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 2,
         "firstFrame": "a.png", "lastFrame": "b.png",
         "description": None, "transition": None},
        {"sceneIndex": 1, "startTimestamp": 2, "endTimestamp": 4,
         "firstFrame": "c.png", "lastFrame": "d.png",
         "description": None, "transition": None},
    ]
    original_len = len(scenes)
    original_idx = scenes[0]["sceneIndex"]
    merge_short_scenes(scenes, min_duration=5.0)
    assert len(scenes) == original_len
    assert scenes[0]["sceneIndex"] == original_idx
