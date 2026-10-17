# MuJoCo origami experiment

A 32 × 20 cm sheet divided into four rigid panels, joined by three parallel
hinges. The first panel is clamped above a table. Position actuators apply
torques to alternate mountain/valley creases, with gravity and contact enabled.
The 10-second experiment folds to approximately −65°, +130°, −130°, holds,
then unfolds. It steps MuJoCo dynamics; it does not assign joint positions.

From the repository root:

```sh
.venv/bin/python -m pip install -e '.[simulation]'
.venv/bin/python examples/mujoco_origami/run.py
```

Results are written to `output/mujoco_origami/`: an MP4, looping GIF, three
PNG snapshots, sampled joint angles and actuator torques in `trajectory.csv`,
and validation results in `report.json`.

For a physics-only run without an OpenGL context:

```sh
.venv/bin/python examples/mujoco_origami/run.py --no-render
```

For a live interactive MuJoCo window on macOS (close to exit early):

```sh
.venv/bin/mjpython examples/mujoco_origami/run.py --viewer --no-render
```

On Linux, use the regular Python executable for the live viewer. Headless
rendering may require an available EGL context and `MUJOCO_GL=egl`.

The standalone `accordion.xml` can also be opened in MuJoCo's viewer.
The fold/unfold control schedule is in `run.py`; XML alone opens a flat sheet.

Validation requires finite positions and velocities, no MuJoCo warnings,
maximum folded and final flat errors below 3°, and maximum sampled contact
penetration below 1 mm. Contact penetration is checked every physics step.

This is a rigid-origami approximation with prescribed crease actuation.
It does not model flexible paper, permanent crease formation, a robot folding
the sheet, or an unsupported structure retaining its shape after actuation.

MuJoCo references: [Python API](https://mujoco.readthedocs.io/en/stable/python.html)
and [modeling](https://mujoco.readthedocs.io/en/stable/modeling.html).

## Origami fox face

```sh
.venv/bin/python examples/mujoco_origami/fox.py
```

This second example begins with a complete 19.8 × 19.8 cm square sheet,
oriented as a diamond. It first folds across the diagonal into a two-layer
triangular base, then folds the left ear, right ear, and nose in sequence.
Eight convex polygons tile the original square without cuts or missing regions.
Each is a 0.4 mm thick mesh. A diagonal hinge and three pairs of layer hinges
apply the folds through actuator torques. Equality constraints keep the paired
ear/nose hinges synchronized so both layers fold together. Cream reverse-side
markings appear as the flaps turn over; eyes and cheeks are printed details.

The 14-second animation, initial square and intermediate snapshots, final image,
generated standalone `fox.xml`,
trajectory, and validation report are saved under `output/mujoco_fox/`.
Only this output directory is written by the fox generator.

```sh
# Fast dynamics check, including final angles and ear-tip positions:
.venv/bin/python examples/mujoco_origami/fox.py --no-render
# Independent timestep refinement, written separately:
.venv/bin/python examples/mujoco_origami/fox.py --no-render --timestep 0.0005 --output /tmp/ori-fox-refined
# Interactive window on macOS:
.venv/bin/mjpython examples/mujoco_origami/fox.py --viewer --no-render
```

Validation checks finite positions and velocities every step, no simulation
warnings, final crease errors below 3°, contact penetration below 1 mm, and
both ear tips extending at least 2 cm above the forehead in the sheet plane.
It also checks that the two layers' shared diagonal ear edges remain within
2 mm throughout the simulation (including the deliberate thickness offset).
The square-start run on MuJoCo 3.16.0 achieved 0.090° maximum final error,
0.801 mm maximum shared-edge separation, and no warnings. The 0.5 ms
timestep run gave matching final angles to numerical precision.

The face is held fixed and the creases remain actuated. Collision between
each flap and its directly connected face, and between opposite layers, is
excluded so finite-thickness panels can layer at near-180° folds. Collisions
between separate flaps within each layer and with the table remain enabled.
The diagonal hinge is offset to accommodate stacked paper. This approximation
does not validate physical
paper layer separation or simulate flexible paper, plastic creases, or hands.

## Single-color 3D sitting fox

```sh
.venv/bin/python examples/mujoco_origami/fox3d.py
```

This example starts with one plain 22.6 × 22.6 cm square. All 14 rigid facets
use the same orange paper material on both sides; there are no printed eyes,
cheeks, nose, or differently colored patches. It folds the diagonal, brings
the corners toward the apex, closes the body into a V, and reverses an outer
corner to form the projecting muzzle. The remaining upper points form ears,
and the broad rear triangle gives a sitting silhouette and pointed tail base.
The final shape has measurable depth; the camera orbits to show both sides.

The triangle/corner/half-fold construction is informed by
[Origami Way's sitting fox](https://www.origamiway.com/easy-origami-fox/).
The simulated crease angles and outer-flap muzzle are a simplified geometric
adaptation, not a claim to reproduce every step of that tutorial.

The fold geometry covers the full original square area (0.0512 m²). Facet
edge lengths remain fixed, and every shared material vertex is checked every
physics step to detect separation. Equality constraints keep corresponding
layer folds synchronized and close the central upper point. The square is
held during folding, then a servo support turns the folded model upright and
lowers it near the table. This last movement presents the model; it is not an
additional crease or a demonstration of unsupported standing.

Results are saved in `output/mujoco_fox_3d/`: `fox3d.xml`, `fox3d.mp4`,
`fox3d.gif`, square/folding/final/orbit PNGs, `crease_panels.json` with original
material coordinates, a joint trajectory (meters for `lift`, radians for
hinges), and `report.json`. The dynamics-only command is:

```sh
.venv/bin/python examples/mujoco_origami/fox3d.py --no-render
.venv/bin/python examples/mujoco_origami/fox3d.py --no-render --timestep 0.0005 --output /tmp/ori-fox3d-refined
```

Validation requires finite states, no MuJoCo warnings, shared-vertex gaps
below 2 mm, final hinge errors below 4°, table penetration below 1 mm, and
at least 1.5 cm of extent in all three dimensions. The nominal run on MuJoCo
3.16.0 reached a largest shared-vertex gap of 0.576 mm and a maximum final
hinge error of 0.044°, with approximately 11.3 × 6.6 × 12.1 cm final extent.

This is a rigid-origami mechanism with actuated pre-existing creases and a
presentation support. Paper-paper self-contact is disabled for thin layered
folds; only table contact is resolved. It does not establish collision-free
physical foldability, free-standing stability, flexible paper behavior, or
permanent crease formation.
