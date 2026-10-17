# YouTube assembly → Genesis animation

Gemini reads the video and produces a bounded JSON scene: component meshes,
poses, assembly steps, source time ranges and comparison criteria. Genesis
renders the resulting scripted assembly with fixed cameras and shaded materials.
This reconstructs visible steps; it does not infer electrical operation or
recover physical dynamics from the video.

Generate a plan with the project's Gemini credentials:

```sh
.venv/bin/python -m ori.reconstruction.visual_animation \
  --url 'https://www.youtube.com/watch?v=TFkUan5Uujs' \
  --output output/genesis_robot_bug --generate-only
```

Render using the installed Genesis environment (macOS Metal):

```sh
.local/genesis-venv/bin/python src/ori/reconstruction/visual_animation.py \
  --render-plan output/genesis_robot_bug/plan.json \
  --output output/genesis_robot_bug
```

Add `--preview` to export the comparison images without rendering the movie.
Inspect `contact-sheet.png` before committing to a full render.

Outputs include `animation.mp4`, reusable GLB meshes, and `comparison.json`.
Each step has before/during/after RGB images from two cameras, entity masks,
depth arrays, object poses, camera settings, and approximate source timestamps.
The clean comparison images have no titles or annotations. Mask IDs are
mapped to semantic component names in the manifest. Source timestamp alignment
and reconstruction accuracy require review; exported frames are synthetic
references, not ground-truth observations of the source video.
