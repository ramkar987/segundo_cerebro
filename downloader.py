"""
Baixa o áudio de um vídeo (YouTube, Instagram, etc.) usando yt-dlp e extrai
metadados básicos (título, duração, URL de origem).

Reescrito do zero (não foi possível ler o arquivo original do repo
`transcriber` por bloqueio do GitHub às tentativas de leitura), mas segue
exatamente a interface usada pelo resto do projeto: download_audio(),
extract_metadata(), MediaMetadata, sanitize_filename() e as exceções
UnsupportedURLError, PrivateOrUnavailableVideoError, LongDurationVideoError,
DownloadError.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from limits import AudioLimits


class DownloadError(Exception):
    """Erro genérico de download."""


class UnsupportedURLError(DownloadError):
    """A URL não é suportada/reconhecida pelo yt-dlp."""


class PrivateOrUnavailableVideoError(DownloadError):
    """O vídeo é privado, foi removido ou está indisponível."""


class LongDurationVideoError(DownloadError):
    """O vídeo excede a duração máxima permitida."""


@dataclass
class MediaMetadata:
    title: str
    source_url: str
    duration_seconds: int


def sanitize_filename(title: str) -> str:
    """Remove caracteres inválidos de nome de arquivo e limita o tamanho."""
    nome = re.sub(r'[\\/*?:"<>|]', "", title).strip()
    nome = re.sub(r"\s+", "_", nome)
    return nome[:100] or "video"


def _classificar_erro(exc: Exception) -> DownloadError:
    mensagem = str(exc).lower()
    if "private" in mensagem or "sign in" in mensagem or "login" in mensagem:
        return PrivateOrUnavailableVideoError(f"Vídeo privado ou indisponível: {exc}")
    if "unavailable" in mensagem or "removed" in mensagem or "not available" in mensagem:
        return PrivateOrUnavailableVideoError(f"Vídeo privado ou indisponível: {exc}")
    if "unsupported url" in mensagem or "no video formats" in mensagem or "is not a valid url" in mensagem:
        return UnsupportedURLError(f"URL não suportada: {exc}")
    return DownloadError(f"Falha ao processar o vídeo: {exc}")


def extract_metadata(url: str) -> MediaMetadata:
    """Busca metadados do vídeo sem baixar o arquivo."""
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise _classificar_erro(exc) from exc

    if info is None:
        raise UnsupportedURLError("Não foi possível extrair informações dessa URL.")

    duration = int(info.get("duration") or 0)
    limites = AudioLimits()
    if duration and duration > limites.max_duration_seconds:
        raise LongDurationVideoError(
            f"O vídeo dura {duration // 60} minutos; o limite é "
            f"{limites.max_duration_seconds // 60} minutos."
        )

    return MediaMetadata(
        title=info.get("title") or "Sem título",
        source_url=url,
        duration_seconds=duration,
    )


def download_audio(url: str, audio_dir: Path) -> tuple[Path, MediaMetadata]:
    """Baixa o áudio do vídeo como .mp3 e retorna (caminho_do_arquivo, metadados)."""
    metadata = extract_metadata(url)

    audio_dir.parent.mkdir(parents=True, exist_ok=True)
    output_template = str(audio_dir) + ".%(ext)s"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        raise _classificar_erro(exc) from exc

    audio_path = Path(str(audio_dir) + ".mp3")
    if not audio_path.exists():
        raise DownloadError("O áudio foi processado, mas o arquivo final não foi encontrado.")

    return audio_path, metadata
