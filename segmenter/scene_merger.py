"""Scene merger module.

Merges short adjacent scenes into longer, more meaningful shots.
This reduces duplicate transcript lines across shots and produces
a cleaner shot list for editorial review.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def merge_short_scenes(
    scenes: list[dict[str, Any]],
    min_duration: float = 5.0,
) -> list[dict[str, Any]]:
    """Merge adjacent scenes shorter than min_duration into longer shots.

    Algorithm:
      1. Sort scenes by startTimestamp.
      2. Walk through scenes sequentially. If a scene is shorter than
         min_duration, absorb it into the current accumulating group.
      3. Once a scene >= min_duration is reached (or the accumulated
         group itself reaches min_duration), finalize the group as one
         merged scene and start a new group.
      4. The last group is always finalized regardless of duration.

    Merged scene fields:
      - sceneIndex: re-indexed from 0
      - startTimestamp: earliest start in the group
      - endTimestamp: latest end in the group
      - firstFrame: firstFrame of the earliest scene in the group
      - lastFrame: lastFrame of the latest scene in the group
      - description: first non-null description found in the group
      - transition: transition of the first scene in the group

    Args:
        scenes: List of scene dicts from analysis.json.
        min_duration: Minimum scene duration in seconds. Scenes shorter
            than this will be merged with neighbors. Default 5.0.

    Returns:
        New list of merged scene dicts with re-indexed sceneIndex values.
        Original list is not modified.
    """
    if not scenes:
        return []

    sorted_scenes = sorted(scenes, key=lambda s: s.get("startTimestamp", 0))

    groups: list[list[dict[str, Any]]] = []
    current_group: list[dict[str, Any]] = [sorted_scenes[0]]

    for scene in sorted_scenes[1:]:
        group_start = current_group[0].get("startTimestamp", 0)
        scene_duration = scene.get("endTimestamp", 0) - scene.get(
            "startTimestamp", 0
        )

        # If adding this scene keeps us under min_duration, absorb it
        current_group_duration = (
            current_group[-1].get("endTimestamp", 0) - group_start
        )
        if current_group_duration < min_duration:
            current_group.append(scene)
        elif scene_duration < min_duration:
            # Current group is already long enough but this scene is short —
            # absorb it into the current group
            current_group.append(scene)
        else:
            # Both current group and new scene are >= min_duration
            groups.append(current_group)
            current_group = [scene]

    # Finalize last group
    if current_group:
        groups.append(current_group)

    # Build merged scenes
    merged: list[dict[str, Any]] = []
    for idx, group in enumerate(groups):
        first = group[0]
        last = group[-1]

        # Find first non-null description in the group
        description = None
        for s in group:
            if s.get("description"):
                description = s["description"]
                break

        merged_scene = {
            "sceneIndex": idx,
            "startTimestamp": first.get("startTimestamp", 0),
            "endTimestamp": last.get("endTimestamp", 0),
            "firstFrame": first.get("firstFrame"),
            "lastFrame": last.get("lastFrame"),
            "description": description,
            "transition": first.get("transition"),
        }
        merged.append(merged_scene)

    logger.info(
        "Merged %d scenes into %d (min_duration=%.1fs)",
        len(scenes),
        len(merged),
        min_duration,
    )
    return merged
