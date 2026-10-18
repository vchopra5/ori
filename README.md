# Ori

Turn physical demonstrations into interactive, step-by-step tutorials.

## Run locally

Requires Python 3.11 or newer. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[simulation]"
python -m ori.coaching.server --port 8765
```

Open [localhost:8765](http://127.0.0.1:8765) and choose a saved tutorial. No frontend build is needed.

To generate new tutorials or use live coaching, copy `.env.example` to `.env` and set `GEMINI_API_KEY`. Saved tutorials work without a key.

See the [studio documentation](src/ori/coaching/README.md) for more details.
