"""Run with python -m ori.check_gemini to verify Gemini credentials."""

from google import genai

from ori.config import load_settings


def main() -> None:
    settings = load_settings()
    with genai.Client(api_key=settings.gemini_api_key) as client:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents="Reply with exactly: Ori is connected.",
        )
        print(response.text)


if __name__ == "__main__":
    main()
