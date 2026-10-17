# Gemini working with Genesis

This trial gives Gemini control of material parameters and a putty knife's
motion, runs a real Genesis MPM simulation, and returns rendered frames plus
particle measurements to Gemini. It can revise its plan for another run.
Every request, response, plan, simulation log, and review is saved.
Exposed controls include elastic modulus, plastic yield stress, density,
panel coupling friction, blade friction, blade tilt, and the motion keyframes.

The initial experiment uses a horizontal drywall sample and uncalibrated
elastoplastic paste. The tool is kinematic; the paste moves through gravity,
contact, and constitutive deformation. No material particles are repositioned
after initialization, and spreading does not use visibility changes. This is
a test of one material interaction, not a completed vertical-wall repair.

Create the isolated simulation environment (the main Ori environment retains
the Gemini SDK and credentials):

```sh
python3 -m venv .local/genesis-venv
.local/genesis-venv/bin/python -m pip install genesis-world==1.4.4 torch
```

Generate a plan from video and allow two simulation/review attempts:

```sh
.venv/bin/python -m ori.reconstruction.genesis_trial \
  --url 'https://www.youtube.com/watch?v=Fdy9uRvpI-E' \
  --output output/new_genesis_trial --attempts 2
```

Or start from the saved Gemini plan:

```sh
.venv/bin/python -m ori.reconstruction.genesis_trial \
  --plan output/genesis_compound/plan.json --output output/new_genesis_trial
```

The default backend is Apple Metal. Use `--backend cpu` or `--backend cuda`
on compatible hardware. First-run kernel compilation can take a while; watch
the per-attempt `simulation.log`. The loop makes at most one initial planning
call plus one review call per attempt; API errors stop without retries. Model
visual approval is recorded as an assessment, not physical calibration.

Offline replay uses only the isolated environment:

```sh
.local/genesis-venv/bin/python examples/genesis_compound/run.py \
  --plan output/genesis_trial/attempt-01/plan.json --output output/genesis_replay
```

Use `--no-render` to export physical particle trajectories and a report without
rendering. `--duration .04` provides a short initialization/contact smoke test.
The output contains `animation.mp4`, snapshots, `contact-sheet.png`, generated
tool OBJ meshes, `particles.npz`, and `report.json`.

Limitations: a rigid blade approximates flexible steel; the paste model has no
calibrated rheology, chemical adhesion, or drying. A smooth reconstructed
surface improves appearance but does not establish material accuracy. Coarse
particle spacing limits the thinnest reliably resolved coating.
