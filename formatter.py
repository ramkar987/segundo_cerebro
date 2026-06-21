"""Formata a transcrição em Markdown (usado para exibição/expansão da nota
de vídeo dentro do Segundo Cérebro)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from downloader import MediaMetadata, sanitize_filename
from transcriber import TranscriptSegment, format_timestamp


def infer_source_tag(source_url: str) -> str:
    """Infere a tag da fonte com base na URL."""
    lower = source_url.lower()
    if "instagram.com" in lower:
        return "instagram"
    return "youtube"


def build_markdown(
    metadata: MediaMetadata,
    segments: list[TranscriptSegment],
    transcribed_at: datetime | None = None,
    include_timestamps: bool = True,
) -> str:
    """Cria o conteúdo Markdown no formato exigido."""
    ts = transcribed_at or datetime.now()
    source_tag = infer_source_tag(metadata.source_url)
    duration_h = format_timestamp(metadata.duration_seconds)

    lines = [
        "***",
        f'title: "{metadata.title}"',
        f'source_url: "{metadata.source_url}"',
        f'transcribed_at: "{ts.strftime("%Y-%m-%d %H:%M")}"',
        f'duration: "{duration_h}"',
        f"tags: [transcricao, {source_tag}]",
        "***",
        "",
        f"# {metadata.title}",
        "",
        "## Transcrição",
        "",
    ]

    for seg in segments:
        if include_timestamps:
            lines.append(f"[{format_timestamp(seg.start_seconds)}] {seg.text}")
        else:
            lines.append(seg.text)

    lines.append("")
    return "\n".join(lines)


def default_markdown_filename(title: str) -> str:
    """Gera um nome de arquivo Markdown sanitizado."""
    return f"{sanitize_filename(title)}.md"


def save_markdown(content: str, output_dir: Path, title: str) -> Path:
    """Salva o conteúdo Markdown em disco."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / default_markdown_filename(title)
    path.write_text(content, encoding="utf-8")
    return path
