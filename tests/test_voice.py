"""Tests for Sarvam AI Voice Transcriber."""

import io
from voice.transcriber import SarvamVoiceTranscriber


def test_voice_transcriber_empty_audio():
    transcriber = SarvamVoiceTranscriber(api_key="mock_key")
    res = transcriber.transcribe_audio(b"")
    assert res["success"] is False
    assert "Empty audio" in res["error"]


def test_voice_transcriber_missing_key():
    transcriber = SarvamVoiceTranscriber(api_key="")
    dummy_bytes = b"RIFF....WAVEfmt ...."
    res = transcriber.transcribe_audio(dummy_bytes)
    assert res["success"] is False
    assert "SARVAM_API_KEY" in res["error"]
