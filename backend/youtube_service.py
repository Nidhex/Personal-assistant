import math
import re
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    AgeRestricted,
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeRequestFailed,
)

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
MAX_URL_LEN = 2048
MAX_SNIPPETS = 20000
MAX_CHARS = 500000
MAX_SECTIONS = 24


class YouTubeServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def extract_youtube_video_id(url: str) -> str:
    if not isinstance(url, str):
        raise YouTubeServiceError(400, "INVALID_YOUTUBE_URL", "Please provide a valid HTTPS YouTube URL.")
    raw = url.strip()
    if not raw or len(raw) > MAX_URL_LEN:
        raise YouTubeServiceError(400, "INVALID_YOUTUBE_URL", "Invalid or overly long YouTube URL.")

    parsed = urlparse(raw)
    if parsed.scheme != "https":
        raise YouTubeServiceError(400, "INVALID_YOUTUBE_URL", "Only HTTPS YouTube URLs are supported.")
    if parsed.username is not None or parsed.password is not None:
        raise YouTubeServiceError(400, "INVALID_YOUTUBE_URL", "URLs with credentials are not allowed.")
    if not parsed.netloc or ":" in parsed.netloc:
        raise YouTubeServiceError(400, "INVALID_YOUTUBE_URL", "Invalid YouTube host or port.")

    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise YouTubeServiceError(400, "INVALID_YOUTUBE_URL", "Only youtube.com and youtu.be links are supported.")

    video_id = ""
    path = parsed.path or ""
    if host == "youtu.be":
        parts = [p for p in path.split("/") if p]
        if len(parts) == 1:
            video_id = parts[0]
    else:
        if path == "/watch":
            qs = parse_qs(parsed.query)
            vals = qs.get("v", [])
            if len(vals) == 1:
                video_id = vals[0]
        elif path.startswith("/embed/"):
            parts = [p for p in path.split("/") if p]
            if len(parts) == 2 and parts[0] == "embed":
                video_id = parts[1]

    if not VIDEO_ID_RE.match(video_id):
        raise YouTubeServiceError(400, "INVALID_YOUTUBE_URL", "Could not extract a valid 11-character YouTube video ID.")
    return video_id


def _format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()


def _select_track(transcript_list: Any):
    tracks = list(transcript_list)
    if not tracks:
        raise YouTubeServiceError(422, "NO_TRANSCRIPT", "No captions are available for this video. Paste a transcript manually.")

    def _is_english(t: Any) -> bool:
        code = (getattr(t, "language_code", "") or "").lower()
        return code == "en" or code.startswith("en-")

    manual_tracks = [t for t in tracks if not getattr(t, "is_generated", False)]
    generated_tracks = [t for t in tracks if getattr(t, "is_generated", False)]

    for pool in (manual_tracks, generated_tracks):
        for t in pool:
            if _is_english(t):
                return t
    if manual_tracks:
        return manual_tracks[0]
    return generated_tracks[0]


def fetch_youtube_transcript(video_id: str) -> Dict[str, Any]:
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        track = _select_track(transcript_list)
        fetched = track.fetch()
    except YouTubeServiceError:
        raise
    except (TranscriptsDisabled, NoTranscriptFound):
        raise YouTubeServiceError(
            422,
            "NO_TRANSCRIPT",
            "Captions are disabled or unavailable for this video. Paste the transcript manually below.",
        )
    except (VideoUnavailable, InvalidVideoId, AgeRestricted):
        raise YouTubeServiceError(
            422,
            "VIDEO_UNAVAILABLE",
            "This video is unavailable, private, or age-restricted. Try another video or paste text manually.",
        )
    except (RequestBlocked, IpBlocked, YouTubeRequestFailed, ConnectionError, TimeoutError):
        raise YouTubeServiceError(
            503,
            "CAPTION_SERVICE_UNAVAILABLE",
            "YouTube blocked or could not reach the caption service. Try again later or paste the transcript manually.",
        )
    except Exception:
        raise YouTubeServiceError(
            502,
            "YOUTUBE_NOTES_FAILED",
            "Unexpected error retrieving captions. Please try again or use manual transcript paste.",
        )

    snippets: List[Dict[str, Any]] = []
    total_chars = 0
    for item in fetched:
        text = _clean_text(getattr(item, "text", None) if not isinstance(item, dict) else item.get("text", ""))
        start = float(getattr(item, "start", 0.0) if not isinstance(item, dict) else item.get("start", 0.0))
        if not text:
            continue
        total_chars += len(text)
        snippets.append({"start": start, "text": text})
        if len(snippets) > MAX_SNIPPETS or total_chars > MAX_CHARS:
            raise YouTubeServiceError(
                422,
                "TRANSCRIPT_TOO_LARGE",
                "This transcript exceeds processing limits. Please paste a shorter excerpt manually.",
            )

    if not snippets:
        raise YouTubeServiceError(
            422,
            "NO_TRANSCRIPT",
            "No caption text was found for this video. Paste the transcript manually below.",
        )

    return {
        "video_id": video_id,
        "language_code": getattr(track, "language_code", "en") or "en",
        "language": getattr(track, "language", "English") or "English",
        "is_generated": bool(getattr(track, "is_generated", False)),
        "snippets": snippets,
    }


def build_timestamp_sections(snippets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not snippets:
        return []
    max_start = max(s["start"] for s in snippets)
    interval = 300.0
    if max_start > 0:
        needed_interval = math.ceil((max_start + 1.0) / MAX_SECTIONS)
        if needed_interval > interval:
            interval = float(needed_interval)

    buckets: Dict[int, List[Dict[str, Any]]] = {}
    for s in snippets:
        idx = min(MAX_SECTIONS - 1, int(s["start"] // interval))
        buckets.setdefault(idx, []).append(s)

    topics: List[Dict[str, Any]] = []
    for i, idx in enumerate(sorted(buckets.keys())):
        group = buckets[idx]
        start_ts = _format_timestamp(group[0]["start"])
        combined = " ".join(s["text"] for s in group).strip()
        sentences = [seg.strip() for seg in re.split(r"(?<=[.!?])\s+", combined) if seg.strip()]
        if not sentences:
            sentences = [combined]

        title_words = combined.split()[:8]
        title = " ".join(title_words)
        if len(combined.split()) > 8:
            title += "..."

        summary = " ".join(sentences[:2])[:320]
        key_points = [s[:160] for s in sentences[:3]]
        answer = sentences[0][:240]
        question = f"What key point is covered around {start_ts} regarding \"{title}\"?"

        topics.append({
            "id": f"yt_sec_{i + 1}",
            "timestamp": start_ts,
            "title": title,
            "summary": summary,
            "keyPoints": key_points,
            "questions": [{"q": question, "a": answer}],
        })

    return topics
