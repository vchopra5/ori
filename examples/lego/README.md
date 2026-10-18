# LEGO connector assembly

Paste a LEGO tutorial's YouTube URL into Ori. The model proposes catalog pieces
and explicit attachments; the harness computes poses and validates connections.
There are up to three geometry-correction proposals. Unsupported connections stop
explicitly. A valid plan is not a guarantee of matching the source video.

## Catalog and geometry

The version 2 catalog includes rectangular bricks, plates (including 4×6,
6×8 and 16×16), tiles, straight and curved slopes, classic hinge bases and tops, and a
1×1 side-stud brick. The tent's catalog IDs are 3036, 3032, 6636, 3937, 6134 and
47457; 3938 is also supported. Names and known part IDs are accepted as input.
Tiles have no top studs. Slopes expose studs only on the high flat row. Hinge
tops have no regular underside sockets. Adding a catalog entry defines its
connector frames and convex solid proxies without modifying the solver.

Coordinates follow [LDraw unit ratios](https://www.ldraw.org/article/218.html).
Geometry is procedurally generated and simplified, not copied manufacturing CAD.
Hinge axis/top proportions are based on the [6134 reference](https://library.ldraw.org/parts/10943)
and the LDraw 3937 base. The curved slope is faceted. Mold details, hollow interiors,
clutch forces, friction, deformation and structural strength are not simulated.
Decorative studs do not participate in solid collision tests: connector occupancy
handles stud mating. Complementary hinge hardware may interlock; the hinge plate
still participates in collision checks against its base.

## Version 2 plan

The root is anchored on the ground. Its position uses integer studs for x/y and
zero for z. Other parts attach to a previously placed part:

```json
{"piece":"roof","attach":{"to":"top","connector":"stud:0:0","self":"socket:1:2","turn":90},"instruction":"Attach the roof panel."}
```

Connector cell indices are zero based in the part's LOCAL coordinate frame.
Dimensions in the catalog specify local x/y orientation, which need not match
the conventional order of dimensions in a LEGO part's name. Turn is a quarter
turn about the parent connector normal. Attached pieces inherit the parent's
orientation, including tilt or a side-facing stud.

```json
{"piece":"top","attach":{"to":"hinge_base","connector":"hinge","self":"hinge","angle":44.5},"instruction":"Attach the hinge top."}
```

Classic hinge angles range from −90 to 90 degrees around the base's local x axis.
The top is horizontal at zero; positive angles raise its local +y direction.
A hinge can be adjusted after pieces have been attached:

```json
{"action":"rotate_hinge","piece":"top","angle":60,"instruction":"Tilt the attached panel."}
```

All descendants move rigidly. Every resulting state is checked for ground/body
penetration, occupied connectors, incompatible mates, disconnected parts and
broken existing connections. Collision checks use separating axes for convex
solids, including tilted plates. Hinge angles are prescribed and locked; the
export is not a free-running hinge dynamics simulation. Motion paths between
saved states are not validated. Playback animates approach, snap and hinge rotation between those states. The display paths are illustrative, not collision-validated insertion trajectories. Replay a single step, focus its connection or use See through to reveal hidden hinges.

Detached subassemblies are currently reordered into connected placements and
reported as an approximation. Technic pins/axles, clips/bars, ball joints,
flexible parts and arbitrary catalog imports are not yet supported.
Legacy version 1 rectangular-grid plans and recordings remain readable.

## Examples and validation

The larger demo is BrickHow's [pyramid tutorial](https://www.youtube.com/watch?v=Giar95AQ_U4).
`pyramid.json` reconstructs the largest connected model: 46 pieces on a 16×16
tan plate, seven stepped tiers and an entrance. Gemini produced the plan after
three proposals; all 46 placement states pass the connector/collision harness
(85 final connections). The two smaller detached pyramids are explicitly omitted.
The silhouette was visually reviewed, but exact source inventory is not independently
verified. The saved local library item is `lego_pyramid_demo`.

```sh
.venv/bin/python -m ori.reconstruction.lego \
  --plan examples/lego/pyramid.json --output output/lego_pyramid_demo
```

For videos with several independent builds, generation selects the largest
connected model and records the omitted alternatives in uncertainties.

```sh
.venv/bin/python -m ori.reconstruction.lego \
  --plan examples/lego/tent.json --output output/lego_tent
.venv/bin/python -m ori.coaching.server
```

Open `http://127.0.0.1:8765/src/ori/coaching/?run=lego_tent`.
The tent uses the inventory identified from the user's video. Its placement
coordinates were manually corrected after model proposals failed collision
checks. Angles are estimated; a small ridge gap is retained. This is a validated
reconstruction example, not evidence that automatic extraction is always accurate.
The original `bridge.json` is an offline version 1 regression example.

Artifacts include `lego-plan.json`, `lego-playback.json`, `report.json` and
`assembly.xml` (MuJoCo fixed bodies at the final assembly pose). Reports retain
inventory IDs, video uncertainty and assumptions. Webcam coaching remains paper-only.

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_lego*.py'
```

## Original designs and restartable validation

`ori.reconstruction.lego_design.run` asks Gemini for a JSON proposal and returns
step-by-step validator feedback. `restart_from_step` is one-based: steps before
it are retained and the proposal supplies the replacement suffix. Retained
pieces cannot change. A restart at 1 replaces the whole plan.

Every placement prefix is checked. Explicit hinge rotations are additionally
sampled at intervals of at most two degrees; this is not continuous collision
proof or insertion-path validation. Exactly ten physical pieces must be present
before a design is published. Failed trials remain available for inspection.

The local database `output/lego-builds.sqlite3` stores `lego_trials` (proposals
and feedback) and `lego_builds` (passing plans, model, validation, artifact path).
Passing builds also export the usual playback/report files for the app library.
