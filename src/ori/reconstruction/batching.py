"""Compact action prompts and atomic JSON output."""

import json
from pathlib import Path


def new_checkpoint(video_url: str, model: str) -> dict:
    return {"checkpoint_version": 3, "video_url": video_url, "model": model,
            "folds": [], "video_complete": False, "previous_interaction_id": None,
            "batches": []}


def build_request(checkpoint: dict, batch_size: int, max_output_tokens: int, *, clip: dict | None = None, **_) -> dict:
    prompt = f"""Watch this origami demonstration. Extract the next {batch_size}
actions in order. Keep only the information needed to describe each fold:
- kind: fold, unfold, rotate, turn_over, or unknown.
- description: one short sentence explaining the action.
- template: "square_base_collapse" for an observed square/preliminary-base
collapse, or null for all other actions.
- moving_point_uv and target_point_uv: coordinates of the material point that
moves and the point it aligns with, or null when not identifiable.
- angle_degrees: rotation magnitude (usually 180 for a complete fold), or null.
- fold_direction: toward_front, toward_back, or unknown.
- reverse_step: for an unfold, the 1-based step number of the fold it reverses;
null for other actions or if unclear. Step numbers continue across batches.

Use normalized MATERIAL coordinates on the original square: (0,0) bottom-left,
(1,0) bottom-right, (1,1) top-right, (0,1) top-left, original front normal +z.
Coordinates stay attached to the original paper after it folds. toward_front
means motion initially toward original +z, toward_back means -z. Infer a point
alignment only when supported by the video; otherwise leave coordinates null
and describe the action. Do not invent precision or skip complex folds.
Include unfolds and paper turns when needed to reproduce the demonstration.

These instructions feed a FOLD-based origami simulator. Our adapter builds the
FOLD mesh locally; you should output actions, not a FOLD mesh. Simple folds use
your point coordinates, angle, and direction. Unfolds reuse the geometry of the
earlier fold referenced by reverse_step (which must be an earlier step).
The only available compound template is square_base_collapse: it coordinates
several creases to collapse a precreased square into a square/preliminary base.
For that action use kind="fold", template="square_base_collapse", and null
moving_point_uv, target_point_uv, angle_degrees, and fold_direction. The template
supplies canonical geometry; describe any visible orientation in the sentence.
Select it only when supported by the video, not just because this is a crane.
Petal folds, squash folds, inside-reverse folds, and later layered movements do
not yet have templates. Still include them faithfully with template=null and
unknown coordinates null; never substitute the square-base template for them.
Paper rotations and turnovers must use rotate or turn_over, not fold. Do not
omit real actions just because the simulator cannot animate them yet.

Return only a JSON array of these small action objects. No crease lines, moving
polygons, IDs, dependency lists, state summaries, timestamps, or physics metadata.
If fewer actions remain, return those. Return [] only when no actions remain.
"""
    if checkpoint["folds"]:
        prompt += "\nThese actions have already been extracted. Continue after the last one; do not repeat them:\n" + json.dumps(checkpoint["folds"], ensure_ascii=False)
    if clip is not None:
        prompt = prompt.replace(f"Extract the next {batch_size}\nactions in order.", "Extract all completed actions visible in this clip, in order.")
        prompt = prompt.replace("If fewer actions remain, return those. Return [] only when no actions remain.",
                                "Return [] if this clip contains no completed actions. Do not infer actions beyond the clip boundary.")
        processing = {"type": "static", **clip}
        for key in ("start_offset", "end_offset"):
            if key in processing and isinstance(processing[key], (int, float)):
                processing[key] = f"{processing[key]:g}s"
        return {"model": checkpoint["model"], "input": [
            {"type": "video", "uri": checkpoint["video_url"], "processing": processing},
            {"type": "text", "text": prompt}],
            "response_format": {"type": "text", "mime_type": "application/json"},
            "generation_config": {"max_output_tokens": max_output_tokens}, "store": False}
    content = [{"type": "text", "text": prompt}]
    if not checkpoint["previous_interaction_id"]:
        content.insert(0, {"type": "video", "uri": checkpoint["video_url"], "processing": "agentic"})
    request = {"model": checkpoint["model"], "input": content,
               "response_format": {"type": "text", "mime_type": "application/json"},
               "generation_config": {"max_output_tokens": max_output_tokens}, "store": True}
    if checkpoint["previous_interaction_id"]:
        request["previous_interaction_id"] = checkpoint["previous_interaction_id"]
    return request


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
