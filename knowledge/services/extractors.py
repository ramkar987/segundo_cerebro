from __future__ import annotations

import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
import yt_dlp


def _hashtags(text: str) -> list[str]:
    return sorted({tag.lower() for tag in re.findall(r'(?<!\w)#([\wÀ-ÿ_]+)', text or '')})


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
    return {
        'title': info.get('title') or '',
        'author': info.get('uploader') or info.get('channel') or '',
        'description': description,
        'caption': description,
        'hashtags': _hashtags(description),
        'source_date': source_date,
        'metadata': {
            'extractor': info.get('extractor'),
            'duration': info.get('duration'),
            'webpage_url': info.get('webpage_url') or url,
            'uploader_id': info.get('uploader_id'),
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
