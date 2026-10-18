# Ori physics studio

A light, glass-like frontend for exploring reconstructed physical motion and moving into webcam-assisted practice. No frontend build or new dependencies required. The renderer is the Three.js bundle already vendored in this repository.

From the repository root:

```sh
python3 -m src.ori.coaching.server --port 8765
```

Open http://127.0.0.1:8765. Or run `npm run coaching`.

## What works

- Home page with an interactive Three.js origami sculpture: one square folds and unfolds through a coordinated eight-panel linkage, with pause/refold controls and a tutorial library. The animation respects reduced motion and stops when offscreen or the tab is hidden.

- Orbitable toy 3D scene, play/pause/reset, contact overlays, seeking, and step thumbnails.
- Library discovers Argon fold trials, the fox and layer examples, and saved MuJoCo recordings. The home page lists saved tutorials; opening one starts paused at the beginning; `?run=toy` opens the original sample.
- Paper playback follows the actual crease axes and selected material panels with smooth angular timing. Straight folds use rigid rotation; compound folds evaluate their validated parametric motion rather than morphing endpoints. Perspective/top views, three paper palettes, grain, soft shadows, a crease overlay, and automatic framing are available.
- “Teach me” opens step-by-step practice with optional local webcam preview. Camera tracks stop when exiting, finishing, switching examples, or leaving the page. One camera button starts the camera, microphone, Gemini Live coaching, and spoken replies for paper lessons. The full camera view streams at 1 fps; Ori does not save audio or frames. The snapshot API can also include local paper/depth images.
- Pasting the source YouTube link opens its saved harness run. New links start a local Argon job: video classification selects the paper harness or MuJoCo.
- Narrow-screen layouts, native keyboard controls, reduced-motion-aware scrolling, and camera-denial states.

## Integration boundary

The default toy scene uses illustrative animation, not a physics solver. The activity panel describes exploration; it never claims sample animation is a validated MuJoCo run. Saved runs show actual stored validation, not fabricated live progress.

New YouTube links use Gemini 4 Argon to classify the video. Paper folding routes to FoldHarness with high reasoning, 32,768 output tokens, and a default allowance of 512 calls (`ORI_LIVE_MAX_CALLS` overrides it). The runner continues on the same sheet after a blocked response; it does not restart the geometry or discard accepted folds. A fixed target and one-fold-at-a-time instructions reduce target drift and stale layer IDs. Other physical demonstrations route to the existing MuJoCo scene compiler and renderer; unsupported videos stop explicitly. The backend needs GEMINI_API_KEY in the root .env. One job runs at a time. Paper lessons use Gemini judging with optional local mask/depth context.

Google Fonts is optional: a system font fallback is provided. All functional code and 3D assets load locally. The local Python server binds to loopback and exposes only coaching assets, the renderer bundle, and saved output artifacts. It is a local demo server, not a deployment server.

## Continuous paper replay

For local rehearsals, `.local/demo-hints.json` (gitignored) may contain
`{"version":1,"videos":{"YOUTUBE_ID":{"guidance":["..."],"prefer_fresh_run":true}}}`.
Only an exact canonical video-ID match adds those hints to a new paper job's
prompt. Each job snapshots its hints; resumed jobs retain their saved prompt.
Hints never bypass model generation or harness validation. Deliberately rehearsed
mistakes are operator guidance, not evidence of spontaneous model recovery.
An optional `thinking_level` (`low`, `medium`, `high`) applies only to that video;
explicit caller overrides take precedence, and resumes keep the saved level.
An optional `model` sets the generation model for that exact video only; other
videos use the default model, and resumed jobs retain their saved model.
`video_sampling_fps` optionally lowers video sampling for that video (default 2);
resumed jobs retain the saved sampling rate.
When `rehearsal_sequence` is supplied, each generation request identifies the next
entry by matching prior model outputs against successful harness feedback. This
keeps intentional mistake/undo steps in order across retries and resumes; the
model still emits every action and the harness still validates it.
`prefer_fresh_run` makes pasting that video's link start a new job; saved library
cards still replay normally. Remove the entry/file to disable it.

`GET /api/library` discovers accepted runs. `GET /api/paper/<id>` returns a
compact replay compiled from `commands.json` by `paper_playback.py`. The compiler
replays each command through `FoldHarness`, keeping the resulting subdivisions,
material coordinates, moving panels, contact order, and exact directed hinge.
The generated `playback.json` is cached alongside the run and keyed by the
command hash. First-time preparation uses `.venv/bin/python` and the simulation
dependencies; subsequent requests use the cache. Run metadata and original
model outputs are never changed.

The browser uses those hinge rotations for motion and retains the accepted
state at every endpoint. Small cosmetic layer offsets follow contact order;
they never modify harness/material coordinates or imply finite paper thickness.
The original harness renders used for model feedback remain unchanged. MuJoCo
recordings remain a separate playback mode. Saved replay does not make model calls.

## Following a fold

The **Fold guide** toggle shows only the current action's real hinge as a
contrasting blue dashed line, clipped to the moving paper's hinge intervals.
Paper colors stay unchanged when guides are enabled, preserving the front/back
color distinction. A curved arrow shows the fold direction; the key explains
the crease, direction, and faded behind-paper segments. The arrow traces an interior point of a moving panel through
the first 60 degrees of the recorded hinge rotation (or the whole fold for
smaller angles), with its head scaled
to the travel distance. Portions hidden behind paper use a softer dashed stroke;
visible portions stay solid. Shaded 3D arrowheads taper along the fold arc, joining the shaft at their base
and staying fixed to the path when the camera rotates. The cue shows departure
into or out of the sheet, rather than turning back toward the viewer at the
end of a half-turn; playback still shows the complete fold. Quiet panel edges remain as a reference; they are not all
instructions to fold. The guide is derived from the recorded command and
selected panels, rather than supplied by a model or guessed from an image.

Selecting a step displays its starting pose; thumbnails show its result.
**Replay fold** plays that one action and pauses at its endpoint. Each action
holds its starting and ending poses briefly so the crease is readable.
These are animation and teaching changes only; saved geometry, harness checks,
and the feedback sent to the model remain unchanged.

## Live video jobs

`POST /api/jobs` with JSON `{"url":"https://www.youtube.com/watch?v=..."}`
starts a bounded worker. `GET /api/jobs/<id>` returns durable status and events;
`GET /api/jobs/<id>/playback` returns the latest accepted paper replay.
The frontend polls every 1.2 seconds and reconnects through `?job=<id>` after
reload. New accepted folds animate with the existing fold guide. Submitted
command names and harness rejection messages appear in the activity feed;
private model reasoning is not displayed. Events arrive after each complete
model response, and accepted folds appear as each validation finishes.

All classification requests, model exchanges, harness results and job state
are saved under `output/fold_trials/runs/<video-id>/live-<uuid>/`. Classification
is separate from the fold conversation. The classifier supplies a fixed target description in the run contract.
The UI only observes events; execution feedback still comes directly from the
harness. Context compaction preserves the current paper and the full accepted
command history. Accepted-prefix behavior remains unchanged. MuJoCo
shows scene compilation/rendering progress and then a recording, rather than
claiming individual folds or dynamics frames have been approved live.

## Live camera coaching

Turning on the camera in a paper lesson starts Gemini Live (`gemini-3.8-live`;
override with `ORI_LIVE_COACH_MODEL`). Set `GEMINI_API_KEY` in the root `.env`.
A persistent session receives the **full camera view once per second**, including
hands and surrounding workspace. The old stillness gate is not used. The
selected action and BEFORE, MID-FOLD, TARGET harness renders provide the actual
fold reference; the model is asked to follow the moving corner, edge, and crease
over time. These are visual judgments, not measured hidden geometry.

The coach reports working, out of view, needs another view, visible mistake,
matched, or a gentle check-in. It can request a specific tilt/reverse view when
important geometry is hidden and suggest one reversible correction. It is
instructed to tolerate fingers, imperfect creases, and arbitrary backgrounds.
Working on the desk off-camera and lifting the paper for a check is the default
workflow. Ori must not request a view of the desk or continuous paper visibility.
An out-of-view report gives one patient reminder and suppresses repeated notices
and timed check-ins until paper returns. It does not infer being lost from gaze
or a face. Check-ins require visible paper and at least 45 seconds without
reported progress, and are rate limited to once per minute. The exact visual
judgments and coaching quality still depend on the model and camera view.

The demo has one start action: **Turn on camera** requests camera and microphone
permission together and starts Live coaching and spoken replies automatically.
**Stop session** releases both devices and stops playback. Desk View starts the
same conversation, obtaining its microphone separately after window selection.
There are no separate live, mic, or speaker buttons. Users can also type a question
and press Enter. Both their speech and Ori's replies have captions.

An AudioWorklet converts microphone input to mono, little-endian PCM16 at 16 kHz,
sending 100 ms chunks through the authenticated relay. Echo cancellation, noise
suppression and automatic gain are requested. Gemini's voice activity detection
ends speech turns and supports interruption; an interruption clears queued reply
audio. Reply audio is 24 kHz PCM. Audio and video are not recorded by Ori.

Useful progress updates are requested after the first two camera frames and
every eight frames thereafter; transport runs at 1 fps, not one answer per second.
Automatic visual feedback waits while the user is speaking or a reply is streaming.
Persistent connection failures release the devices and restore the same camera button for
retry, after bounded automatic recovery. API error responses use JSON; old/static servers returning HTML produce a
readable server message instead of a JSON parser exception.

`GET /api/health` reports the running backend's protocol and instance ID. Live
startup checks protocol 4 first, so a fresh frontend served by an older Python
process cannot silently start an incompatible session. Restart the Python
process after backend edits; changing a file on disk does not reload its imports.

`POST /api/live/session` resolves the saved run's trusted replay and starts a
single-client authenticated loopback WebSocket relay in the project runtime.
A random `client_id` identifies each browser controller. Another tab or test gets
a conflict response instead of terminating the existing demo. Only the owning
controller may replace its transport during reconnect; legacy requests cannot
evict an active session. The browser gets a random local session URL, with exact
Origin checks; the Gemini key remains server-side. Media and transcripts stay
in memory and are not written to disk by Ori.

The relay emits a heartbeat every five seconds. Missing heartbeats, transient
socket errors, and Gemini connection expiry trigger up to three reconnects with
backoff, while retaining the same camera/mic tracks and current lesson stage.
Recovery supplies the current step's references to a fresh model session; it does
not resume conversation history or replay buffered speech. Recovered microphone
streams explicitly re-enable audio on the new relay. Quiet model output by itself
is not a connection failure. Explicit Stop session cancels pending reconnects.

A matched report is held in the browser until the model finishes its response
AND every queued audio source has actually ended. Model generation finishing is
not the same as the person finishing hearing it. Only then does auto advance
change the demo. Manual navigation, user interruption, stop, and transport
recovery invalidate pending handoffs; interruption requests a new visual check.
Long responses are not silently truncated at the old 12-second queue limit.
The browser sends playback-start/end signals, preventing automatic camera
feedback from piling new speech on top of a reply still being heard.

Tool responses are acknowledged upstream before sending completion to the UI,
so a newly selected stage cannot race the preceding tool acknowledgement.
Generation completion clears the speaking flag even if a separate turn-complete
signal is delayed. The relay detects an outstanding model request with no model
output for 20 seconds and requests reconnect; a quiet idle coach alone does not
trigger this. Live receives actual camera video for conversation, but no second periodic Live
judging turn is injected. All runtime text uses `send_realtime_input(text=...)`
alongside audio/video; it does not mix turn-based `send_client_content` calls into
the stream. Harness reference images go exclusively to the independent verifier;
Live receives the current action, fold count, and verifier findings as text. A separate fast vision judge is the sole authority for automatic
completion: `gemini-3.8-flash` (`ORI_STEP_CHECK_MODEL`), with thinking set to
`LOW`, up to 2048 output tokens, and no conversation history. The available Gemini 3
models do not support a guaranteed full thinking-off setting. The judge starts
on the first fresh frame and keeps checking the newest frame, one request at a
time, with no request queue or sequential Live approval. Camera capture stays at
one frame per second. UNFOLDED/BEFORE/TARGET references are rendered once per selected
stage and reused; the completion judge omits intermediate animation references
and local segmentation/depth. Live continues handling voice, tips, and questions.

The vision judge's nonmatching findings also reach Live as `VISUAL DIAGNOSIS`, including
stage/epoch/frame ID, paper visibility, visible evidence, observation, and suggested
correction. A visible mistake requests two short spoken sentences after existing
speech: the specific observed mismatch, then one reversible repair with a visible
destination/alignment. Likely folding history is phrased tentatively, and already
correct folds are preserved. Ear-forming stages check the ear direction against
the current target without presuming an error or demanding two ears prematurely.
Before-fold results explain the missing action without claiming an incorrect fold, while
ambiguous visible results request one specific view. Absent-paper findings update
context silently. Identical feedback is suppressed; changed advice has a 25-second
cooldown within a stage, so paper returning after absence can still get immediate help. Stale diagnoses are discarded just like
stale passes; diagnostics never authorize advancement.

A Live `matched` report alone never advances. The independent result must identify
actual visible paper and a specific observed feature distinguishing this target
from BEFORE and UNFOLDED. The structured result must select TARGET over those
alternatives, explicitly rule both out, and name the distinguishing target feature
and its visible counterpart in the actual camera. Paper detection, a generic
match claim, and a prior crease do not meet this contract. Inconsistent match
responses are downgraded to before-fold/unclear; the progress guard enforces the
same contract independently of the API decoder. This is one model call per check,
not consecutive approval calls. Frame IDs bind each check to the selected step and epoch, after that
stage's frame boundary; old checks cannot complete the next fold. A verified result
waits for existing speech, asks for one brief spoken confirmation, and advances
only after that confirmation finishes playing. Results expire 12 seconds after
capture. Stage changes cancel pending inference, and interruptions request a
fresh camera check. Failures and nonmatches leave the live session running.
Actual recognition remains dependent on visible shape, lighting, occlusion, and
model accuracy. `tests/manual/fold_verification_benchmark.py` is an opt-in
network evaluation that sends synthetic paper views plus saved harness references
to Gemini. It tests clutter, finger occlusion, rotation, perspective-skewed flat
paper, a wrong triangle, and flat/previous/correct targets at every saved fold.
It records verdicts and timings in `output/verification-eval/latest.json` and
returns nonzero for any incorrect classification. Run only when those uploads
are authorized:

```bash
PYTHONPATH=src .venv/bin/python tests/manual/fold_verification_benchmark.py
```

Flash-Lite with low thinking still falsely approved a skewed unfolded sheet in
this evaluation. The stronger `gemini-3.8-flash` with low thinking rejected that
case, so it is now the default single background judge. Synthetic performance
does not establish accuracy in real webcam lighting and backgrounds.


The protocol-4 lesson flow is explicit: start media → spoken introduction →
browser waits for generation AND audio playback → reveal selected fold →
`intro_done` → Live explains that displayed action → independent visual checks →
spoken correction/view request or verified confirmation → next displayed fold.
Camera frames are withheld during the intro; audio and heartbeat traffic continue.
Each stage includes `total_folds` and `is_final`. A verified final fold sends
`LESSON COMPLETE`, explicitly asking Live to acknowledge that all folds are done;
only after its audio ends does the UI mark completion. Browser pings keep the voice
session alive after verification stops. Reconnect preserves a completed intro.
The UI numbers actual folds from one, labeling the flat sheet separately.
Humor is optional and conversational; there is no scheduled pun or fallback intro joke.

Unclaimed sessions expire after 30 seconds; connected sessions are bounded to
30 minutes and close on disconnect. Context compression is enabled. Camera stop,
source changes, lesson exit, and page departure close the stream and stop playback.

**Teach me** selects the first actual fold (stage 1) immediately, so its
animation is visible before coaching begins; the flat starting sheet remains
available through Previous. Each stage context is sent only after the lesson
text and demo have switched. The model receives a DISPLAY CONFIRMED message and
may teach only that displayed action. A successful check advances the display
before the next fold's references are supplied. Ori must wait for that display
confirmation rather than verbally assign future folds from memory. Teaching the
selected fold does not require a camera view; checking completion does.

Only a current-step/current-epoch tool report backed by a camera frame received
within five seconds can advance, and it can complete that stage only once. Stage
changes clear prior camera evidence and supply fresh references. Auto advance
moves exactly one step; disabling it keeps progress manual. Reports never modify
the simulation or its saved fold commands. Other task types use manual steps.

## Snapshot API and optional depth

Paper checks use Gemini (`gemini-4-argon` by default; override with
`ORI_COACH_MODEL`). Set `GEMINI_API_KEY` in the root `.env`. The original camera
crop is the primary evidence. Gemini also receives the selected action and
BEFORE, MID-FOLD (when motion data exists), and TARGET harness renders, each
from front and oblique views. The middle frame uses a real half-angle rigid
rotation, not a vertex interpolation.

Local SAM 2.1 mask and Depth Anything V2 previews are optional supporting
context. Install/prepare them with:

```sh
uv pip install --python .venv/bin/python -e '.[local-vision]'
npm run coaching:vision-setup
```

The setup downloads DINOv2, SAM 2.1 Tiny, and Depth Anything V2 Small into
`.local/models/` with checkpoint revisions recorded in `ori-model.json`. Local
inference is offline. Missing models or failed segmentation/depth never block
the camera judge. The prompt explicitly says these auxiliary images are
fallible and must not veto a recognizable shape. Estimated relative depth is
not a distance or crease-angle measurement.

A valid Gemini match immediately advances exactly one step when auto advance
is enabled. There is no local score threshold or second Gemini pass required.
Nonmatches show a visible observation and one useful correction. Malformed
responses, API errors, and stale responses never advance. With auto advance
disabled, a passed check leaves advancement to the user. Ordinary finger
coverage, busy backgrounds, color/angle differences, and minor imperfections
are tolerated; hidden layer correctness is not claimed.

`POST /api/observe` accepts `run_id`, zero-based `step`, base64 JPEG `frame`, and
optional normalized `point: [x,y]`. The server resolves trusted references. The
response provider is `gemini-assisted`, and `advance_allowed` is derived from
the validated verdict. Optional PNG preview data URLs remain under `perception`.

Sampled camera crops, masks, and estimated depth are sent to Gemini during
snapshot API checks. Ori does not persist these images or coaching
responses; they remain in memory/stdin. A persistent worker reuses the models
and client. Camera/step changes invalidate old requests; exiting releases
camera/window/microphone tracks and stops sampling. Other task types use manual steps.

## Long sessions and physics-safe context compaction

Live sessions default to 512 model calls. Set `ORI_LIVE_MAX_CALLS` before starting
the server to change that allowance. A blocked response prompts replanning on
the current sheet; every unfold or change still goes through the harness.

Every request retains the original video, fixed target/contract, and exact current
harness feedback: world vertices, material coordinates, panel IDs, contacts/layer
order, metrics when supplied, and **all accepted commands**. These are never
rounded, summarized by a model, or truncated. Physics data is not subject to the
dialogue budget: if it grows, the request grows with it.

`fold_context.py` deterministically compacts the redundant dialogue to at most
8 recent exchanges / 24,000 characters plus 24 failed-move records / 12,000
characters. Historical copies of state and accepted commands are omitted;
failed commands retain exact harness errors and repeat counts. Per-request
history and physics hashes and `context.json` make the context reproducible.
Full raw requests, outputs, and feedback remain on disk.

A durable `checkpoint.json` stores the full exchange history and exact physics
snapshot with a hash and an explicit committed-call list. Live folds publish
only after this checkpoint is saved. An interrupted, uncommitted response stays
in the diagnostic archive but cannot advance the restored physics.
On resume, every historical proposal is independently replayed, its feedback is
compared exactly, and the resulting physics must equal the checkpoint before
another request can be sent. A mismatch stops the run. `fold_audit.py` independently
verifies compacted payloads, images, and checkpoints, including 100+ call logs.

`POST /api/jobs` with `{"resume_id":"live-…"}` continues an incomplete compacting
run and grants another configured call allowance. The UI calls this through
**Continue this run**. It retains the same video, target, accepted folds, and
playback; it does not create a fresh sheet. The previous straight-fold action
contract can be upgraded to the constructive tools only after exact checkpoint
replay, with the upgrade boundary recorded and old requests preserved for audit.
Unrecognized contract changes are rejected. Older pre-compaction runs remain
readable but require a new run to use this runner. Only model-completed runs
appear as finished tutorials; partial results remain explicitly labeled.

## macOS Desk View

The teaching screen includes a camera selector and **Use Mac Desk View**.
After camera permission is granted, the selector lists available camera inputs,
including a Desk View device if the browser exposes one.

For Apple's window-sharing workflow:

1. Turn on the camera in Ori.
2. Open the macOS Video menu → Desk View → Start Desk View.
3. Choose **Use Mac Desk View** in Ori and select the Desk View window in the
   browser's sharing picker. Audio is never requested.

This button uses `getDisplayMedia` and does not turn on the macOS effect itself.
The user chooses the shared window. If window sharing is unavailable in the
embedded browser, open Ori in Chrome or Safari, or choose a Desk View camera
input when available. Hardware support and system instructions:
https://support.apple.com/en-us/121541

Switching sources stops the old tracks and invalidates old coaching requests.
Ending window sharing stops sampling and clears the previews. Cancelling the
picker restores the source controls; exiting a lesson also disposes of capture
that finishes opening late. Gemini-assisted checks use the selected feed exactly
as they use the webcam. There is no custom “holding/desk” inference toggle.

## Deleting saved runs

Each saved library entry has a Delete action in the home library and library
dialog. Confirmation names the selected run. `POST /api/library/delete` accepts
an opaque `token` returned by the library; arbitrary paths are never accepted.
The run directory is moved into `output/.trash/<id>` with a sibling JSON file
recording its original relative path. Files remain recoverable locally.
Reconstruction must finish before deletion is allowed. Deleting the currently
open run stops camera/playback and returns to the home library.

Completed attempts for the same video now have separate stable IDs; deleting
one does not remove another. Older `trial-<video-id>` links still resolve to the
latest remaining completed run. The built-in toy sample has no Delete action.

## Constructing folds without a predefined recipe

Gemini can use `type: "precrease"` to subdivide existing paper without moving it,
and `type: "compound"` to supply simultaneous parametric paths for existing
material vertices. A small arithmetic/trigonometric expression language describes
continuous linkage motion; it cannot execute code, replace the mesh or add paper.
Shared vertices move together. The harness checks panel dimensions, seams,
intersections, contact departure and layer ordering at dense staggered samples.
Failures reject the entire action and report the failing time/constraint.
This extends the straight-hinge API; it is not a general automatic crease solver
or a continuous collision certificate. Cutting and stretching remain unsupported.

`{"commands":[],"probe":[...],"done":false}` tests a sequence on a private copy.
The feedback includes predicted geometry or an exact failure; the live sheet,
accepted history and playback remain unchanged. Probe outcomes and failed
candidates survive dialogue compaction. Gemini must submit successful candidates
in `commands` to commit them. Live reconstruction uses high reasoning to derive
linkage motion and revise candidates from the constraints.

Playback evaluates the same parsed expressions as the harness, including at
arbitrary intermediate times; it never linearly morphs compound endpoints.
Single-hinge arrows are suppressed for compound motions because they would give
incorrect instructions. The crease overlay remains available. Tests include an
analytic eight-panel square-base collapse and coordinated unfold, speculative
failure rollback, checkpoint resume/audit and browser material-distance checks.

The coaching side demonstration has an **Autoloop** checkbox, initially on.
When enabled it repeats the current fold with a short hold at its endpoint.
Its clock is independent of the main timeline and camera checks, so repeats
do not advance steps or reset coach matching. Unchecking finishes the current
cycle; leaving the lesson stops rendering the side demonstration.

## LEGO assembly

LEGO tutorial links route to the catalog-based snap harness. The viewer shows
validated placements, piece quantities and video uncertainties. See
[the LEGO example](../../../examples/lego/README.md) for supported pieces, limits,
offline replay and the anchored MuJoCo assembly export. Webcam coaching remains
paper-only.

Approval freshness: the relay invalidates in-flight positives when local camera tiles change materially or sharpness drops, and on Live out-of-view reports. A positive also requires a camera frame received within two seconds that remains visually consistent with the checked frame. This conservative motion gate cannot recognize folds and never grants approval; returning paper requires a fresh check. It adds no cloud round trip. Correction narration explains the alignment goal another way rather than simply repeating the last instruction.

## Generation feedback and final shape

The paper character animates while a job is running. Cloud verdicts come only from recorded accepted/rejected harness events or explicit probe outcomes; idle animation never simulates a pass or failure. Reduced-motion preferences stop decorative animation. Coral, wisteria, and sage papers use complementary reverse colors so folded layers remain visible.

The harness supports small flat flaps through off-center creases, selected layers, and open hinges at angles below 180 degrees. Video generation receives explicit guidance distinguishing crease placement from hinge angle. A run cannot finish on the same turn that changes the sheet: Argon must inspect the resulting front and oblique renders and confirm completion on a later turn, using HIGH thinking. This is model self-review, not independent proof of video fidelity. Existing saved tutorials are preserved.

Whole-sheet turns use a distinct `reorient` action with `origin`, `axis`, and signed `angle_degrees`. It rotates every panel and contact normal together, preserving panel IDs, material coordinates, relative shape and layer adjacency. It never splits paper or creates a crease. The browser animates it as a rigid turn and omits the fold-here guide. The model contract explicitly forbids expressing view changes as half-plane folds. Older runs can resume with a recorded contract upgrade, retaining their original requests and audit trail. Existing incorrectly generated folds are not silently reinterpreted as turns.

Planning undo is a separate model action: `{"commands":[],"undo":1,"done":false}` removes the last accepted action (or a positive number of trailing actions) and deterministically restores the earlier paper. It removes discarded crease subdivisions and panel IDs rather than physically unfolding them. The live replay and lesson are rebuilt from the retained prefix; the preview also refreshes when a correction changes commands without changing their count. Original proposals, undo requests, and restored feedback remain in the durable audit/checkpoint history. Undo must be submitted alone and cannot finish the run; the next turn sees the restored paper before proposing a replacement. Physical unfolding remains an ordinary accepted motion that retains crease structure and appears in the lesson. No new UI button is required.
