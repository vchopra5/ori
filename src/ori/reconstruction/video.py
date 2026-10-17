"""Shared video identifiers and output paths."""
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

VIDEO_URL = "https://www.youtube.com/watch?v=GC_Szxdqh2Y"
PLAN_DIRECTORY = Path(__file__).resolve().parent / "origami plans"


def plan_path(video_url: str) -> Path:
    """Use the actual video's ID, regardless of URL spelling or tracking params."""
    url = urlparse(video_url)
    host = (url.hostname or "").lower()
    parts = url.path.strip("/").split("/")
    if host == "youtu.be":
        video_id = parts[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parts[0] == "watch":
            video_id = parse_qs(url.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in {"shorts", "embed", "live"}:
            video_id = parts[1]
        else:
            video_id = ""
    else:
        video_id = ""
    if url.scheme not in {"https", "http"} or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Provide a YouTube video URL containing a valid video ID.")
    return PLAN_DIRECTORY / f"{video_id}.json"
