# Video to MuJoCo

Gemini watches a YouTube tutorial and creates a declarative scene: objects,
compound box geometry, material colors, action captions, and tool pose tracks.
The local compiler writes triangle OBJ meshes, separate box collision shapes,
and a runnable `scene.xml`. MuJoCo advances gravity and contacts; the renderer
exports `animation.mp4`, snapshots, `contact-sheet.png`, `trajectory.json`, and
`report.json`. Model output is JSON data, never executable code.

```sh
.venv/bin/python -m ori.reconstruction.mujoco_scene \
  --url 'https://www.youtube.com/watch?v=Fdy9uRvpI-E' \
  --output output/my_video --model gemini-3.5-flash
```

Requires the project's Gemini credentials and simulation extras:
`pip install -e '.[simulation]'`. Omit `--model` to use `GEMINI_MODEL`.
Up to three generation calls are allowed for syntax/compilation corrections.
API errors stop immediately. All requests, responses, and compiler errors
are retained in the output directory. Use a new directory for a new run.

Replay or edit a generated scene without any model calls:

```sh
.venv/bin/python -m ori.reconstruction.mujoco_scene \
  --scene output/my_video/scene.json --output output/replay
```

Add `--no-render` to run physics checks and export trajectory/report without
creating a movie. Add `--review` for one additional Gemini call comparing the
actual rendered frames with the source video; findings are saved to `review.json`.
For offline replay with review, retain `source.json` in the output directory.
Generated recordings also appear in the Ori studio library.
Open `scene.xml` in a MuJoCo viewer to inspect its geometry;
the Python runner applies the motion tracks and visibility events.

This produces an approximate instructional animation. Tools follow prescribed
mocap paths; loose dynamic bodies obey rigid-body dynamics. Hidden static
material overlays have no colliders. Cutting, compound spreading, adhesion,
drying, and paint are visual state changes, not simulated material processes.
Generated assets are block-based approximations, not recovered CAD or detailed
human hands. Successful compilation and finite physics do not establish that
Gemini matched every demonstrated step; inspect the movie and saved scene.

Verification:

```sh
.venv/bin/python -m unittest discover -s tests -p test_mujoco_scene.py
```
