from dataclasses import dataclass
import re
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PARAMS = {
    'fbclid', 'gclid', 'dclid', 'msclkid', 'mc_cid', 'mc_eid',
    'ref', 'ref_src', 'igshid', 'si', 'feature',
}

BARE_URL_RE = re.compile(
    r'^(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?::\d+)?(?:[/?#].*)?$',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Detection:
    kind: str
    normalized: str


def _parse_possible_url(value: str):
    parsed = urlparse(value)
    if parsed.scheme in {'http', 'https'} and parsed.netloc:
        return parsed

    # Aceita URLs coladas sem protocolo:
    # www.instagram.com/..., instagram.com/..., youtu.be/..., example.com/...
    if (
        value
        and not any(ch.isspace() for ch in value)
        and BARE_URL_RE.match(value)
    ):
        return urlparse('https://' + value)

    return None


def _canonical_instagram(parsed) -> str:
    path = parsed.path.rstrip('/') + '/'
    return urlunparse(('https', 'www.instagram.com', path, '', '', ''))


def _canonical_youtube(parsed) -> str:
    host = parsed.netloc.lower().split(':')[0]
    host = host[4:] if host.startswith('www.') else host
    path = parsed.path or '/'

    if host == 'youtu.be':
        video_id = path.strip('/').split('/')[0]
        if video_id:
            return f'https://www.youtube.com/watch?v={video_id}'

    if path == '/watch':
        video_id = (parse_qs(parsed.query).get('v') or [''])[0]
        if video_id:
            return 'https://www.youtube.com/watch?' + urlencode({'v': video_id})

    for prefix in ('/shorts/', '/live/', '/embed/'):
        if path.startswith(prefix):
            video_id = path[len(prefix):].strip('/').split('/')[0]
            if video_id:
                return 'https://www.youtube.com/watch?' + urlencode({'v': video_id})

    return urlunparse(('https', 'www.youtube.com', path, '', parsed.query, ''))


def _canonical_web(parsed) -> str:
    host = parsed.netloc.lower()
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        low = key.lower()
        if low.startswith('utm_') or low in TRACKING_PARAMS:
            continue
        query.append((key, value))
    query.sort()
    return urlunparse((
        parsed.scheme.lower(),
        host,
        parsed.path or '/',
        parsed.params,
        urlencode(query, doseq=True),
        '',
    ))


def detect_capture(raw: str) -> Detection:
    value = (raw or '').strip()
    parsed = _parse_possible_url(value)

    if parsed:
        host = parsed.netloc.lower().split(':')[0]
        host = host[4:] if host.startswith('www.') else host

        if host in {'instagram.com', 'm.instagram.com'} or host.endswith('.instagram.com'):
            return Detection('instagram', _canonical_instagram(parsed))

        if host in {'youtube.com', 'm.youtube.com', 'youtu.be', 'youtube-nocookie.com'} or host.endswith('.youtube.com'):
            return Detection('youtube', _canonical_youtube(parsed))

        return Detection('web', _canonical_web(parsed))

    return Detection('note', value)
