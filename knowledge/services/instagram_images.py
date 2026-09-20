from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass

import instaloader
import requests
from django.conf import settings


SHORTCODE_RE = re.compile(
    r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([^/?#]+)',
    re.IGNORECASE,
)


class InstagramImageExtractionError(RuntimeError):
    pass


@dataclass
class InstagramPostData:
    title: str
    author: str
    caption: str
    description: str
    hashtags: list[str]
    source_date: object
    image_urls: list[str]
    media_kind: str
    has_video: bool
    metadata: dict


def _hashtags(text: str) -> list[str]:
    return sorted(
        {
            tag.lower()
            for tag in re.findall(r'(?<!\w)#([\wÀ-ÿ_]+)', text or '')
        }
    )


def _shortcode(url: str) -> str:
    match = SHORTCODE_RE.search(url or '')
    if not match:
        raise InstagramImageExtractionError('URL do Instagram sem shortcode reconhecível.')
    return match.group(1)


def extract_instagram_post(url: str) -> InstagramPostData:
    """Lê posts /p/ com Instaloader, inclusive carrosséis de imagens."""
    shortcode = _shortcode(url)

    loader = instaloader.Instaloader(
        quiet=True,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        request_timeout=30.0,
    )

    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
    except Exception as exc:
        raise InstagramImageExtractionError(
            f'Instaloader não conseguiu ler o post: {exc}'
        ) from exc

    caption = (post.caption or '').strip()
    author = f'@{post.owner_username}' if post.owner_username else ''
    typename = getattr(post, 'typename', '') or ''

    image_urls: list[str] = []
    has_video = bool(post.is_video)

    if typename == 'GraphSidecar':
        nodes = list(post.get_sidecar_nodes())
        has_video = any(node.is_video for node in nodes)
        image_urls = [
            node.display_url
            for node in nodes
            if getattr(node, 'display_url', None)
        ]
        media_kind = 'carousel'
    elif post.is_video:
        # Vídeo normal: o yt-dlp continua responsável por áudio/transcrição.
        media_kind = 'video'
    else:
        media_kind = 'image'
        if post.url:
            image_urls = [post.url]

    return InstagramPostData(
        title='',
        author=author,
        caption=caption,
        description=caption,
        hashtags=_hashtags(caption),
        source_date=post.date_utc,
        image_urls=image_urls[: settings.MAX_INSTAGRAM_IMAGES],
        media_kind=media_kind,
        has_video=has_video,
        metadata={
            'extractor': 'instaloader',
            'shortcode': shortcode,
            'instagram_typename': typename,
            'media_kind': media_kind,
            'image_count': len(image_urls),
            'has_video': has_video,
            'webpage_url': url,
        },
    )


def _download_image(url: str) -> tuple[bytes, str]:
    response = requests.get(
        url,
        timeout=30,
        headers={
            'User-Agent': 'Mozilla/5.0 SegundoCerebro/0.1',
            'Referer': 'https://www.instagram.com/',
        },
    )
    response.raise_for_status()

    data = response.content
    if len(data) > settings.MAX_VISION_IMAGE_BYTES:
        limit_mb = settings.MAX_VISION_IMAGE_BYTES / (1024 * 1024)
        raise InstagramImageExtractionError(
            f'Imagem maior que o limite configurado de {limit_mb:.0f} MB.'
        )

    content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip()
    if not content_type.startswith('image/'):
        guessed = mimetypes.guess_type(url)[0]
        content_type = guessed if guessed and guessed.startswith('image/') else 'image/jpeg'

    return data, content_type


def _vision_batch(batch: list[tuple[int, str]]) -> list[dict]:
    if not settings.GROQ_API_KEY:
        raise InstagramImageExtractionError('GROQ_API_KEY não configurada.')

    parts = [
        {
            'type': 'text',
            'text': (
                'Transcreva SOMENTE o texto visível nas imagens a seguir. '
                'Não explique, não resuma e não complete frases por conhecimento externo. '
                'Preserve a ordem de leitura e os números importantes. '
                'Cada imagem é um slide de um carrossel. '
                'Retorne JSON válido no formato '
                '{"slides":[{"index":1,"text":"texto literal"}]}. '
                'Se um slide não tiver texto legível, use text vazio.'
            ),
        }
    ]

    for index, url in batch:
        data, content_type = _download_image(url)
        encoded = base64.b64encode(data).decode('ascii')
        parts.append({'type': 'text', 'text': f'SLIDE {index}'})
        parts.append(
            {
                'type': 'image_url',
                'image_url': {
                    'url': f'data:{content_type};base64,{encoded}',
                },
            }
        )

    response = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {settings.GROQ_API_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'model': settings.GROQ_VISION_MODEL,
            'messages': [{'role': 'user', 'content': parts}],
            'response_format': {'type': 'json_object'},
            'temperature': 0,
            'max_completion_tokens': 3000,
        },
        timeout=settings.AI_TIMEOUT,
    )

    if response.status_code >= 400:
        raise InstagramImageExtractionError(
            f'Groq Vision retornou HTTP {response.status_code}: '
            f'{response.text[:1200]}'
        )

    raw = response.json()['choices'][0]['message']['content']
    payload = json.loads(raw)
    slides = payload.get('slides') or []
    return slides if isinstance(slides, list) else []


def extract_visual_text(image_urls: list[str], progress=None) -> tuple[str, list[dict]]:
    """Extrai o texto dos slides em lotes de até 3 imagens (limite do modelo)."""
    urls = [url for url in image_urls if url][: settings.MAX_INSTAGRAM_IMAGES]
    if not urls:
        return '', []

    expected = set(range(1, len(urls) + 1))
    results: dict[int, str] = {}

    for offset in range(0, len(urls), 3):
        batch_urls = urls[offset: offset + 3]
        batch = [
            (offset + position + 1, url)
            for position, url in enumerate(batch_urls)
        ]

        if progress:
            progress(
                35 + int((offset / max(len(urls), 1)) * 25),
                f'Lendo texto dos slides {batch[0][0]}–{batch[-1][0]}',
            )

        for entry in _vision_batch(batch):
            if not isinstance(entry, dict):
                continue
            try:
                index = int(entry.get('index'))
            except (TypeError, ValueError):
                continue
            if index not in expected:
                continue
            text = str(entry.get('text') or '').strip()
            results[index] = text

    details = [
        {'index': index, 'text': results.get(index, '')}
        for index in range(1, len(urls) + 1)
    ]

    blocks = [
        f'[SLIDE {entry["index"]}]\n{entry["text"]}'
        for entry in details
        if entry['text']
    ]
    return '\n\n'.join(blocks), details
