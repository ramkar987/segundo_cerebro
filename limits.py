"""Limites configuráveis para tamanho/duração de áudio, para evitar travar
o app com vídeos gigantes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AudioLimits:
    """Limites configuráveis para áudio e vídeo."""

    warn_mb: float = 25.0
    block_mb: float = 100.0
    max_duration_seconds: int = 2 * 60 * 60


def file_size_mb(path: Path) -> float:
    """Retorna o tamanho do arquivo em MB."""
    return path.stat().st_size / (1024 * 1024)


def should_warn_audio_size(size_mb: float, limits: AudioLimits) -> bool:
    """Indica se o áudio deve gerar aviso."""
    return size_mb >= limits.warn_mb


def should_block_audio_size(size_mb: float, limits: AudioLimits) -> bool:
    """Indica se o áudio deve bloquear o processamento."""
    return size_mb >= limits.block_mb
