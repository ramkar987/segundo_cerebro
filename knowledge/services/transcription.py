from __future__ import annotations

import mimetypes
import tempfile
from pathlib import Path

import requests
import yt_dlp
from django.conf import settings

from ..models import Chunk, Item


class TranscriptionSkipped(Exception):
    """Transcrição pulada sem transformar a captura em erro."""


def _download_media(url: str, directory: Path) -> Path:
    output_template = str(directory / '%(id)s.%(ext)s')
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'restrictfilenames': True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        requested = info.get('requested_downloads') or []
        for part in requested:
            filepath = part.get('filepath')
            if filepath and Path(filepath).exists():
                return Path(filepath)

        prepared = Path(ydl.prepare_filename(info))
        if prepared.exists():
            return prepared

    candidates = sorted(
        (p for p in directory.iterdir() if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError('O áudio/vídeo foi baixado, mas o arquivo final não foi encontrado.')
    return candidates[0]


def _call_groq(audio_path: Path) -> dict:
    api_key = settings.GROQ_API_KEY
    if not api_key:
        raise TranscriptionSkipped('GROQ_API_KEY não configurada.')

    size = audio_path.stat().st_size
    if size > settings.MAX_TRANSCRIPTION_BYTES:
        mb = size / (1024 * 1024)
        limit = settings.MAX_TRANSCRIPTION_BYTES / (1024 * 1024)
        raise TranscriptionSkipped(
            f'Arquivo de áudio com {mb:.1f} MB excede o limite configurado de {limit:.0f} MB.'
        )

    mime_type = mimetypes.guess_type(audio_path.name)[0] or 'application/octet-stream'
    with audio_path.open('rb') as fh:
        response = requests.post(
            'https://api.groq.com/openai/v1/audio/transcriptions',
            headers={'Authorization': f'Bearer {api_key}'},
            files={'file': (audio_path.name, fh, mime_type)},
            data=[
                ('model', settings.GROQ_WHISPER_MODEL),
                ('language', settings.TRANSCRIPTION_LANGUAGE),
                ('response_format', 'verbose_json'),
                ('timestamp_granularities[]', 'segment'),
                ('temperature', '0'),
            ],
            timeout=180,
        )

    if response.status_code >= 400:
        detail = response.text[:1000]
        raise RuntimeError(f'Groq retornou HTTP {response.status_code}: {detail}')

    return response.json()


def _segment_value(segment: dict, key: str):
    value = segment.get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def save_transcript(item: Item, payload: dict) -> None:
    source = item.source
    transcript = (payload.get('text') or '').strip()
    source.transcript = transcript

    metadata = dict(source.metadata or {})
    metadata['transcription'] = {
        'status': 'done',
        'model': settings.GROQ_WHISPER_MODEL,
        'language': payload.get('language') or settings.TRANSCRIPTION_LANGUAGE,
        'duration': payload.get('duration'),
    }
    source.metadata = metadata
    source.save(update_fields=['transcript', 'metadata'])

    # Em mídia, chunks com timestamp representam a fala. Quando retranscrever,
    # substituímos somente os chunks de transcrição.
    item.chunks.filter(kind='transcript').delete()

    segments = payload.get('segments') or []
    chunks = []
    for position, segment in enumerate(segments):
        text = (segment.get('text') or '').strip()
        if not text:
            continue
        chunks.append(
            Chunk(
                item=item,
                kind='transcript',
                text=text,
                position=position,
                start_seconds=_segment_value(segment, 'start'),
                end_seconds=_segment_value(segment, 'end'),
            )
        )

    if chunks:
        Chunk.objects.bulk_create(chunks)


def transcribe_item(item: Item, progress=None) -> str:
    if item.type not in {Item.Type.INSTAGRAM, Item.Type.YOUTUBE}:
        raise ValueError('Somente Instagram e YouTube podem ser transcritos neste marco.')

    if not settings.TRANSCRIBE_MEDIA:
        raise TranscriptionSkipped('TRANSCRIBE_MEDIA está desativado.')

    with tempfile.TemporaryDirectory(prefix='segundo-cerebro-') as temp:
        if progress:
            progress(35, 'Baixando áudio do vídeo')
        media_path = _download_media(item.source_url, Path(temp))
        if progress:
            progress(50, 'Transcrevendo áudio')
        payload = _call_groq(media_path)

    save_transcript(item, payload)
    if progress:
        progress(65, 'Transcrição concluída')
    return item.source.transcript


def mark_transcription_state(item: Item, status: str, message: str = '') -> None:
    source = item.source
    metadata = dict(source.metadata or {})
    metadata['transcription'] = {
        'status': status,
        'message': message[:1000],
        'model': settings.GROQ_WHISPER_MODEL,
    }
    source.metadata = metadata
    source.save(update_fields=['metadata'])
