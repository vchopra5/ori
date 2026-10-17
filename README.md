# Ori — Learn Physical Skills from Video

Turn videos of physical skills into step-by-step guidance for learning them.

## Current experiment: extracting information from video with Gemini

This repository currently tests whether Gemini can extract an ordered,
geometrically useful action sequence from a physical-skill demonstration.
The first example is a paper-crane YouTube tutorial: Gemini is asked to recover
the first three folds and any intervening unfolds or reorientations, with
timestamps, crease geometry, moving regions, and explicit uncertainty.

The experiment evaluates extraction quality. Schema-valid JSON does not establish
that the recovered geometry is correct or that a simulator can execute it.
No benchmark results or successful physics reconstructions are claimed yet.

Review the output against the video for action order (including unfolds),
timestamp accuracy, consistent material coordinates, correct layer selection,
and honest handling of obscured details. Processing-step counts show whether
agentic navigation occurred; they do not measure extraction accuracy.

## Longer-term direction

Ori has two planned parts, connected by a shared skill plan:

1. **Video reconstruction** (`src/ori/reconstruction/`): analyze a demonstration
   with Gemini and reconstruct an ordered, timestamped sequence of teachable steps.
2. **Live coaching** (`src/ori/coaching/`): monitor a learner's webcam against that
   plan, track progress, and offer guidance when the learner needs help.

This repository currently contains the architecture and configuration scaffold.
A manual video-analysis experiment is included. Production video reconstruction,
webcam capture, and live feedback are not implemented yet.

## Gemini setup

Requires Python 3.11 or newer. From this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Copy `.env.example` to `.env` if you do not already have a local `.env` file.
Create an API key in
[Google AI Studio](https://aistudio.google.com/apikey), then fill in:

```dotenv
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

For a fresh clone, copy `.env.example` to `.env` first. `.env` is ignored by Git.
Keep this key in the Python backend; do not expose it to a browser or commit it.
The model is configurable so it can be changed independently of the code.

`ori.config.load_settings()` loads the root `.env` and checks for the API key.
The official `google-genai` SDK (2.x, required by the current Interactions API)
is included for the reconstruction implementation.
See Google's [video understanding documentation](https://ai.google.dev/gemini-api/docs/video-understanding).

## Try agentic video understanding

Review `src/ori/reconstruction/test_video.py`. It includes the paper-crane
YouTube link and requests a simulator-neutral JSON plan for the first three folds.
The schema and coordinate conventions are in `src/ori/reconstruction/fold_plan.py`. It uses `gemini-3.5-flash-lite` with explicit
agentic video processing through the Interactions API.

After the setup above, preview the exact request without making an API call:

```sh
python -m ori.reconstruction.test_video --dry-run
```

When ready, run the experiment yourself:

```sh
python -m pip install --upgrade -e .
python -m ori.reconstruction.test_video
```

This script uses its own model default, independent of `GEMINI_MODEL`; override
it with `--model` if needed. `--url` accepts another public YouTube link.
It makes one synchronous request with no automatic retries, uses the output token limit configured in the script, and prints the answer, status, processing-step counts,
and token usage. The output limit is not a total cost cap: video input and
internal processing also consume tokens, and the whole video may be inspected.
The request disables server-side interaction storage (`store=False`). No local
recordings or response files are written. A timeout may still leave server work
running; check usage before rerunning.

Look for both `processing_call` and `processing_result` counts to confirm that
video navigation occurred. JSON is checked against the schema locally.

The plan uses persistent normalized coordinates on the original sheet, crease
endpoints, moving material polygons, signed rotation increments, alignment
constraints, and video evidence. It is a candidate kinematic plan, not a validated
physics reconstruction or a simulator-specific import file. A simulator adapter
still needs mesh splitting, layer tracking, collision/contact handling, and
material parameters. Reorientations and obscured geometry are explicitly marked
unresolved; do not replay operations with missing geometry automatically.
See the [agentic video guide](https://ai.google.dev/gemini-api/docs/video-understanding#agentic-video-understanding).

## Shared contract

Reconstruction should produce a **skill plan** containing the skill name, source
video, and ordered steps. Each step should include its source time range,
instruction, observable completion criteria, common mistakes, and any uncertainty
in the reconstruction. Coaching consumes this plan instead of reinterpreting the
original video on every frame.

Coaching should report the current step, observed evidence, a progress state
(`in_progress`, `completed`, `needs_guidance`, or `uncertain`), and optional
guidance. An unclear camera view should produce `uncertain`, rather than an
unsupported correction. Webcam capture should be an explicit user action.
