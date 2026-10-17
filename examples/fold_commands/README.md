# Executable fold commands

The model supplies actions. `FoldHarness` splits the paper along each crease,
rotates the selected panels about it, and checks the generated geometry. The
fox is a deterministic four-command example, with no model or network call.

From the repository root, using the existing simulation dependencies:

```sh
.venv/bin/python -m pip install -e '.[simulation]'
.venv/bin/python examples/fold_commands/run.py
# Select just the top flap from a two-layer stack:
.venv/bin/python examples/fold_commands/run.py examples/fold_commands/layer-selection.json --output output/fold_layers_demo
# Run another model-generated command document:
.venv/bin/python examples/fold_commands/run.py /path/to/commands.json --output output/my_fold
.venv/bin/python -m unittest discover -s tests -p 'test_fold*.py'
```

Outputs in `output/fold_commands_fox/`: `fox.gif`, `fox.png`, `steps.png`,
`commands.json`, `states.json`, `layers.json`, `report.json`, and
`model-instructions.txt`. Animation and final-image names follow the input
plan's filename. The layer example produces `layer-selection.gif` and `.png`.

## Action contract

Start with a diamond-shaped square at `(-1,0,0)`, `(0,-1,0)`, `(1,0,0)`,
`(0,1,0)`. Its area is 2 in these units. The initial front normal is +Z.

```json
{
  "commands": [
    {
      "name": "Fold the upper half behind the lower half",
      "crease": [[-1, 0, 0], [1, 0, 0]],
      "normal": [0, 0, 1],
      "moving_side": "left",
      "angle_degrees": -180,
      "layers": "all"
    }
  ]
}
```

Crease endpoints specify an infinite directed line in the **current world
coordinates**, not the material coordinates. `normal` is a unit-direction
reference perpendicular to the crease. Left is the positive half-plane along
`cross(normal, crease_end - crease_start)`; right is the negative half-plane.
Angles are incremental, with the right-hand rule around that directed line.
`layers` defaults to `"all"`. Use `"top"` or `"bottom"` to select exposed
panels on the chosen side, relative to the supplied normal. An explicit list
of current panel IDs is also accepted, for example `"layers": ["paper/m"]`.
Commands need no mesh or guessed vertex IDs.
Material coordinates remain attached to the original square as faces subdivide.

## Layer rules

Each panel has a persistent `id` until it splits. Its children append `/m`
(moving half-plane) and `/s` (stationary half-plane). These labels describe the
split geometry before layer selection. Read current IDs from `state`; do not
guess the IDs a future split will create.

Positive-area coplanar overlaps have explicit contact sides. In `state`, a
panel's `contacts[other_id]` is a unit vector pointing from the other panel
toward this panel, describing the limiting side of zero-thickness contact.
It does not offset any paper coordinates. Opposite faces store opposite
vectors. Boundary-only contact is not a stacked layer.

Subdivisions inherit contact order. When a packet moves, its contact vectors
rotate with it, reversing the stack when turned over. New landing order comes
from which side the moving flap approaches. Unfolding removes contacts when
faces no longer overlap. Cyclic or ambiguous orders fail instead of using face
IDs or drawing order to invent a result. The renderer uses the same contacts,
viewed from its camera, so front and reverse views agree with the state.

Layer selection occurs after clipping at the crease. `top` selects candidate
panels with no overlapping candidate above them; `bottom` does the converse.
This is conservative for a panel with only partial exposure: the harness does
not subdivide along arbitrary overlap boundaries to expose smaller patches.
A selected panel must fold away from any stationary layer it touches, and
shared material seams must stay together throughout the motion. A flap that
would pass through a covering layer or tear its shared edge is rejected
without changing the accepted state or its layer order.

`harness.layer_state()` and the `layers` field in execution feedback expose
the contacts and a +Z drawing order. `layers.json` saves these for each example
step. Contact constraints, rather than the arbitrary order of disjoint faces,
are the physical information in that drawing order.

For model integration, use `MODEL_INSTRUCTIONS` as the action contract, then:

```python
from ori.reconstruction.fold_commands import FoldHarness, MODEL_INSTRUCTIONS

harness = FoldHarness()
feedback = harness.execute(model_output["commands"])
# Feed feedback (and a render) back to the model for the next proposal.
# On failure, accepted commands remain committed; the failed command changes nothing.
# Retry with replacement commands only, rather than replaying the accepted prefix.
```

This is a separate small action API; existing video reconstruction and
OriSim3D workflows continue to use their current entry points.

## What passing means

Each fold preserves all pairwise distances within each panel, total material
area, and shared material seams, including T junctions. Invalid, nonfinite,
empty-side and off-axis cuts are rejected. Strict noncoplanar intersections
between moving and fixed panels are checked at intervals of at most 3 degrees.

This is a rigid **kinematic** harness, not a force-based paper simulator.
It has zero thickness, permits ordered coplanar overlap and boundary contact.
Sampled intersection checks can miss collisions between
samples or degenerate contacts. There is no gravity, friction, tearing,
elasticity or permanent crease formation. Layer selection uses whole convex
panels; inside reverse folds and coupled collapses require a richer solver. General
folds on nonflat states are rejected when clipping would cut off the hinge axis.

The example creates a simple flat fox face with two ears and a folded muzzle,
using the geometry alone. It does not claim to reconstruct a particular video.
MuJoCo remains a separate path for non-origami dynamics demos.

## Test a model on a video with harness-only feedback

```sh
.venv/bin/python -m ori.reconstruction.fold_trial 'https://www.youtube.com/shorts/FdBTwMuh1mU' --model gemini-4-argon --max-calls 12
```

The model receives the original video at 2 sampled frames/second, the fixed
command contract, current harness state and front/oblique renders, and recent
model/harness exchanges. Only `FoldHarness.submit_text` generates execution
feedback, including malformed JSON or envelope errors. No observer model,
reviewer, fox recipe, hand-authored corrections, or motion library participates.
API failures stop the trial without retries. Accepted prefixes persist after
failed proposals; the model receives their exact current state.

A unique directory under `output/fold_trials/runs/<video-id>/` contains the
fixed contract and config, each request/response, model output and harness
feedback, checkpoints, accepted `commands.json`, `final-state.json`,
`result.json`, `preview.gif`, `final.png`, and `steps.png`. Request logs refer to
image files instead of duplicating their base64 bytes.

`model_claimed_done` records the model's completion claim. It does not establish
that the folds match the video: the harness measures paper constraints, not
video correspondence. An unsupported operation can result in
`model_reported_blocked`; an unrepaired sequence stops at the call budget.

Use `--objective approximate` when a recognizable approximation of the final
object matters more than reproducing the demonstrated sequence. This is a
fixed task objective, not extra corrective feedback. `--transport generate-content`
sends the same video, contract, harness feedback, and images through Gemini's
direct content API instead of Interactions. Both paths leave JSON parsing to
the harness; no provider-enforced JSON schema discards malformed model text.

To continue a call-budget-limited run, use `--resume RUN_DIRECTORY` and a larger
**total** `--max-calls`, retaining the original objective, model, video, and API
transport. The runner checks the unchanged contract and replays every exchange
for identical harness feedback before continuing. Earlier requests and the
previous result are preserved.

Audit a completed experiment with:

```sh
.venv/bin/python -m ori.reconstruction.fold_audit RUN_DIRECTORY
```

The audit replays model proposals, compares every harness response, verifies
all dynamic text against the harness history, checks the fixed task/video, and
compares every supplied image with a fresh render of that exact harness state.
It writes `feedback-audit.json`; it does not assess video resemblance.

For Argon, `--thinking-level low --max-output-tokens 32768` selects the
SDK's `LOW` reasoning mode and uses the model's advertised full output
allowance, without a numeric thinking budget. These settings apply to the
direct content transport and are logged for every call. They can also be
changed during resume without changing the task, harness, or feedback.
Incomplete/API-failed calls are retained; continuation starts a new numbered
call from the last accepted harness checkpoint.
