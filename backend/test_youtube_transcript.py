import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from backend.database import get_db, init_db
from backend.main import _yt_rate_limits, app
from backend.security import generate_session_id, get_session_expiry
from backend.youtube_service import YouTubeServiceError, extract_youtube_video_id


def _setup_user(user_id: str, email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_workspace_notes WHERE user_id = ?", (user_id,))
    cursor.execute(
        "INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES (?, ?, ?, datetime('now'))",
        (user_id, email, f"User {user_id}"),
    )
    conn.commit()
    conn.close()
    _yt_rate_limits.pop(user_id, None)


def _client_for(user_id: str) -> TestClient:
    sid = generate_session_id()
    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, ?, ?, datetime('now'))",
        (sid, user_id, get_session_expiry()),
    )
    conn.commit()
    conn.close()
    client = TestClient(app)
    client.cookies.set("session_id", sid)
    return client


def _make_track(lang_code: str, lang: str, is_generated: bool, snippets: list):
    track = MagicMock()
    track.language_code = lang_code
    track.language = lang
    track.is_generated = is_generated
    track.fetch.return_value = snippets
    return track


def test_url_validation():
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    bad_urls = [
        "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://evil-youtube.com/watch?v=dQw4w9WgXcQ",
        "https://user:pass@www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com:8443/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&" + ("a=1&" * 600),
    ]
    for url in bad_urls:
        try:
            extract_youtube_video_id(url)
            raise AssertionError(f"Expected YouTubeServiceError for {url}")
        except YouTubeServiceError as e:
            assert e.status_code == 400
            assert e.code == "INVALID_YOUTUBE_URL"
    print("PASS: test_url_validation")


def test_generated_and_manual_captions_save_and_dedupe():
    init_db()
    uid = "test_yt_user_1"
    _setup_user(uid, "yt1@example.com")
    client = _client_for(uid)

    snippets = [
        {"start": 0.0, "text": "Welcome to the lecture on algorithms."},
        {"start": 120.0, "text": "Binary search runs in logarithmic time."},
        {"start": 310.0, "text": "Merge sort divides and conquers."},
    ]
    gen_track = _make_track("en", "English", True, snippets)

    with patch("backend.youtube_service.YouTubeTranscriptApi") as mock_api:
        mock_api.return_value.list.return_value = [gen_track]
        res1 = client.post("/api/youtube/notes", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        assert res1.status_code == 200, res1.text
        d1 = res1.json()
        assert d1["success"] is True
        assert d1["video_id"] == "dQw4w9WgXcQ"
        assert d1["is_generated"] is True
        assert len(d1["topics"]) == 2
        assert d1["topics"][0]["timestamp"] == "00:00"
        assert d1["topics"][1]["timestamp"] == "05:10"
        for topic in d1["topics"]:
            assert isinstance(topic.get("questions"), list) and len(topic["questions"]) >= 1
            assert isinstance(topic["questions"][0].get("q"), str) and topic["questions"][0]["q"].strip()
            assert isinstance(topic["questions"][0].get("a"), str) and topic["questions"][0]["a"].strip()
        note_id = d1["note"]["id"]

        # Duplicate processing returns existing note without calling YouTube again
        res2 = client.post("/api/youtube/notes", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["note"]["id"] == note_id
        for topic in d2["topics"]:
            assert isinstance(topic.get("questions"), list) and len(topic["questions"]) >= 1
            assert isinstance(topic["questions"][0].get("q"), str) and topic["questions"][0]["q"].strip()
            assert isinstance(topic["questions"][0].get("a"), str) and topic["questions"][0]["a"].strip()
        assert mock_api.return_value.list.call_count == 1

    # Manual captions
    uid2 = "test_yt_user_2"
    _setup_user(uid2, "yt2@example.com")
    client2 = _client_for(uid2)
    man_track = _make_track("en", "English", False, snippets)
    with patch("backend.youtube_service.YouTubeTranscriptApi") as mock_api:
        mock_api.return_value.list.return_value = [man_track]
        res3 = client2.post("/api/youtube/notes", json={"url": "https://www.youtube.com/embed/dQw4w9WgXcQ"})
        assert res3.status_code == 200
        assert res3.json()["is_generated"] is False

    # User isolation: uid2 has its own note, not uid1's
    assert res3.json()["note"]["id"] != note_id
    print("PASS: test_generated_and_manual_captions_save_and_dedupe")


def test_error_mappings():
    init_db()
    uid = "test_yt_user_err"
    _setup_user(uid, "yterr@example.com")
    client = _client_for(uid)

    cases = [
        (TranscriptsDisabled("dQw4w9WgXcQ"), 422, "NO_TRANSCRIPT"),
        (NoTranscriptFound("dQw4w9WgXcQ", ["en"], {}), 422, "NO_TRANSCRIPT"),
        (VideoUnavailable("dQw4w9WgXcQ"), 422, "VIDEO_UNAVAILABLE"),
        (IpBlocked("dQw4w9WgXcQ"), 503, "CAPTION_SERVICE_UNAVAILABLE"),
        (RuntimeError("boom"), 502, "YOUTUBE_NOTES_FAILED"),
    ]
    for exc, expected_status, expected_code in cases:
        _yt_rate_limits.pop(uid, None)
        with patch("backend.youtube_service.YouTubeTranscriptApi") as mock_api:
            mock_api.return_value.list.side_effect = exc
            res = client.post("/api/youtube/notes", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
            assert res.status_code == expected_status, f"Expected {expected_status}, got {res.status_code}: {res.text}"
            assert res.json()["code"] == expected_code

    # Oversize transcript -> 422 TRANSCRIPT_TOO_LARGE
    _yt_rate_limits.pop(uid, None)
    huge_snippets = [{"start": float(i), "text": "x" * 100} for i in range(6000)]
    huge_track = _make_track("en", "English", True, huge_snippets)
    with patch("backend.youtube_service.YouTubeTranscriptApi") as mock_api:
        mock_api.return_value.list.return_value = [huge_track]
        res = client.post("/api/youtube/notes", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        assert res.status_code == 422
        assert res.json()["code"] == "TRANSCRIPT_TOO_LARGE"
    print("PASS: test_error_mappings")


if __name__ == "__main__":
    test_url_validation()
    test_generated_and_manual_captions_save_and_dedupe()
    test_error_mappings()
    print("\nALL YOUTUBE TRANSCRIPT TESTS PASSED!")
