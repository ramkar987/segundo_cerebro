"""
Transcrição local de áudio usando Whisper (openai-whisper).
Roda na sua máquina/servidor, sem precisar de chave de API.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import whisper


@dataclass
class TranscriptSegment:
    """Segmento de transcrição com timestamp e texto."""

    start_seconds: float
    text: str


class TranscriptionError(Exception):
    """Erro de transcrição."""


def format_timestamp(seconds: float) -> str:
    """Converte segundos em formato HH:MM:SS."""
    total = max(0, int(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def transcribe_audio(
    audio_path: Path,
    model_name: str = "base",
    max_retries: int = 3,
    language: str | None = None,
) -> list[TranscriptSegment]:
    """Transcreve um arquivo de áudio local usando Whisper."""
    last_error: Exception | None = None
    model = whisper.load_model(model_name)

    for attempt in range(1, max_retries + 1):
        try:
            result: dict[str, Any] = model.transcribe(
                str(audio_path),
                word_timestamps=False,
                language=language,
                verbose=False,
            )
            segments: list[TranscriptSegment] = []
            for seg in result.get("segments", []):
                segments.append(
                    TranscriptSegment(
                        start_seconds=float(seg.get("start", 0.0)),
                        text=str(seg.get("text", "")).strip(),
                    )
                )
            return segments
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(2 * attempt)

    raise TranscriptionError(f"Falha na transcrição após {max_retries} tentativas: {last_error}")
