from __future__ import annotations

import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
import yt_dlp


def _hashtags(text: str) -> list[str]:
    return sorted({tag.lower() for tag in re.findall(r'(?<!\w)#([\wÀ-ÿ_]+)', text or '')})


def _useful_handle(raw: str) -> str:
    handle = (raw or '').strip().lstrip('@')
    if not handle:
        return ''
    # Instagram às vezes entrega apenas um ID numérico; YouTube pode entregar
    # um channel id UC... Ambos são úteis como metadado, mas ruins para exibir.
    if handle.isdigit() or handle.startswith('UC'):
        return ''
    return handle


def _author_label(info: dict) -> str:
    name = (info.get('uploader') or info.get('channel') or '').strip()
    handle = _useful_handle(info.get('uploader_id') or '')

    if name and handle and handle.lower() not in name.lower():
        return f'{name} (@{handle})'
    if name:
        return name
    if handle:
        return f'@{handle}'
    return ''


def extract_video_metadata(url: str) -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    description = info.get('description') or ''
    timestamp = info.get('timestamp')
    source_date = datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp else None
    uploader_id = (info.get('uploader_id') or '').strip().lstrip('@')

    return {
        'title': info.get('title') or '',
        'author': _author_label(info),
        'description': description,
        'caption': description,
        'hashtags': _hashtags(description),
        'source_date': source_date,
        'metadata': {
            'extractor': info.get('extractor'),
            'duration': info.get('duration'),
            'webpage_url': info.get('webpage_url') or url,
            'uploader_id': uploader_id or None,
            'channel_id': info.get('channel_id'),
            'view_count': info.get('view_count'),
        },
    }


def extract_webpage(url: str, timeout: int = 20) -> dict:
    response = requests.get(
        url,
        timeout=timeout,
        headers={'User-Agent': 'Mozilla/5.0 SegundoCerebro/0.1'},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    for node in soup(['script', 'style', 'noscript', 'svg']):
        node.decompose()

    title = (soup.title.string.strip() if soup.title and soup.title.string else '')
    paragraphs = []
    for node in soup.find_all(['p', 'article', 'main']):
        text = ' '.join(node.get_text(' ', strip=True).split())
        if len(text) >= 40:
            paragraphs.append(text)

    # Deduplica mantendo a ordem.
    content = '\n\n'.join(dict.fromkeys(paragraphs))
    return {'title': title, 'content': content[:200000]}
