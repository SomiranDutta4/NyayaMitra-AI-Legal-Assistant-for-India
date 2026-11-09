"""Sarvam AI Voice Transcriber (Speech-to-Text).

Integrates Sarvam AI Saaras model (https://api.sarvam.ai/speech-to-text)
to transcribe Indian voice inputs (English, Hindi, and Hinglish) directly from
microphone recordings or audio files.
"""

import os
import io
from typing import Optional, Dict, Any, Union
from config.settings import API_KEYS

SARVAM_API_KEY = API_KEYS.get("sarvam", "")


class SarvamVoiceTranscriber:
    """Handles Speech-to-Text conversion using Sarvam AI Saaras API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else (SARVAM_API_KEY or os.getenv("SARVAM_API_KEY", ""))
        self.endpoint = "https://api.sarvam.ai/speech-to-text"

    def transcribe_audio(
        self,
        audio_data: Union[bytes, io.BytesIO],
        model: str = "saaras:v3",
        language_code: str = "unknown",
        filename: str = "input.wav"
    ) -> Dict[str, Any]:
        """Transcribes audio input using Sarvam AI Saaras model.
        
        Supports Hindi, English, and Indian code-mixed speech.
        """
        # Read bytes
        if isinstance(audio_data, io.BytesIO):
            audio_bytes = audio_data.getvalue()
        elif hasattr(audio_data, "read"):
            audio_bytes = audio_data.read()
        else:
            audio_bytes = audio_data

        if not audio_bytes:
            return {"success": False, "error": "Empty audio data received.", "transcript": ""}

        # If no API key is provided, return offline message / simulation
        if not self.api_key:
            return {
                "success": False,
                "error": "SARVAM_API_KEY not configured in .env. Please set your key to enable live Indian speech recognition.",
                "transcript": ""
            }

        try:
            import httpx
            headers = {
                "api-subscription-key": self.api_key
            }
            files = {
                "file": (filename, audio_bytes, "audio/wav")
            }
            data = {
                "model": model,
                "mode": "transcribe"
            }
            if language_code and language_code != "unknown":
                data["language_code"] = language_code

            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    self.endpoint,
                    headers=headers,
                    data=data,
                    files=files
                )

                if response.status_code == 200:
                    result = response.json()
                    transcript = result.get("transcript", "").strip()
                    return {
                        "success": True,
                        "transcript": transcript,
                        "detected_language": result.get("language_code", language_code),
                        "raw_response": result
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Sarvam API error (Status {response.status_code}): {response.text}",
                        "transcript": ""
                    }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to connect to Sarvam AI voice service: {str(e)}",
                "transcript": ""
            }
