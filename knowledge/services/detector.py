from dataclasses import dataclass
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PARAMS = {
    'fbclid', 'gclid', 'dclid', 'msclkid', 'mc_cid', 'mc_eid',
    'ref', 'ref_src', 'igshid', 'si', 'feature',
}


@dataclass(frozen=True)
class Detection:
    kind: str
    normalized: str


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

    if path.startswith('/shorts/') or path.startswith('/live/'):
        clean_path = '/' + '/'.join(part for part in path.split('/') if part)
        return urlunparse(('https', 'www.youtube.com', clean_path, '', '', ''))

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
    parsed = urlparse(value)
    if parsed.scheme in {'http', 'https'} and parsed.netloc:
        host = parsed.netloc.lower().split(':')[0]
        host = host[4:] if host.startswith('www.') else host

        if host in {'instagram.com', 'm.instagram.com'} or host.endswith('.instagram.com'):
            return Detection('instagram', _canonical_instagram(parsed))

        if host in {'youtube.com', 'm.youtube.com', 'youtu.be', 'youtube-nocookie.com'} or host.endswith('.youtube.com'):
            return Detection('youtube', _canonical_youtube(parsed))

        return Detection('web', _canonical_web(parsed))

    return Detection('note', value)
