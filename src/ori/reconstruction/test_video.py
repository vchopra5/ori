"""Manual agentic-video experiment; importing this module makes no API calls.

Preview: python -m ori.reconstruction.test_video --dry-run
Run:     python -m ori.reconstruction.test_video
"""

import argparse
from collections import Counter
import json

from ori.reconstruction.fold_plan import SCHEMA, SIMULATION_PROMPT


VIDEO_URL = "https://www.youtube.com/watch?v=GC_Szxdqh2Y"
MODEL = "gemini-3.5-flash-lite"



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=VIDEO_URL, help="Public YouTube video URL")
    parser.add_argument("--model", default=MODEL, help="Agentic-video-capable model")
    parser.add_argument("--dry-run", action="store_true", help="Print request without credentials or API calls")
    args = parser.parse_args()

    # Deliberately independent of GEMINI_MODEL: the original scaffold's default
    # model does not support agentic video. Override this experiment via --model.
    request = {
        "model": args.model,
        "input": [
            {"type": "video", "uri": args.url, "processing": "agentic"},
            {"type": "text", "text": SIMULATION_PROMPT},
        ],
        "response_format": {"type": "text", "mime_type": "application/json", "schema": SCHEMA},
        "generation_config": {"max_output_tokens": 100000},
        "store": False,
    }
    if args.dry_run:
        print(json.dumps(request, indent=2))
        return

    from google import genai
    from google.genai import types
    from ori.config import load_settings

    settings = load_settings()
    print(f"Model: {args.model}\nVideo: {args.url}", flush=True)
    print("Sending one request; no automatic retries. This may take several minutes.", flush=True)
    # A timeout is not a spending cap and does not guarantee server cancellation.
    with genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=300_000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    ) as client:
        interaction = client.interactions.create(**request)

    print(f"\nStatus: {interaction.status}")
    if interaction.status == "completed" and interaction.output_text:
        from jsonschema import validate

        plan = json.loads(interaction.output_text)
        validate(instance=plan, schema=SCHEMA)
        print(json.dumps(plan, indent=2))
        print("\nJSON schema validated. Geometry and physical validity still require review.")
    else:
        print(interaction.output_text or "No text returned; inspect the status and token limit.")
    # Use the JSON representation to inspect processing evidence and usage
    # without depending on individual SDK response subclasses.
    result = interaction.model_dump(mode="json", exclude_none=True)
    counts = Counter(step.get("type") for step in result.get("steps", []))
    print("\nProcessing steps:", json.dumps(dict(counts), indent=2))
    if counts["processing_call"] and counts["processing_result"]:
        print("Confirmed: the response contains agentic video navigation steps.")
    else:
        print("Agentic navigation was requested, but processing evidence was not returned.")
    print("\nToken usage:", json.dumps(result.get("usage", {}), indent=2))
    if interaction.status != "completed":
        raise SystemExit("Request did not complete successfully. No retry was made.")


if __name__ == "__main__":
    main()
