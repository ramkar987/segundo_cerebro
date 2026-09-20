from dataclasses import dataclass
from urllib.parse import urlparse

@dataclass(frozen=True)
class Detection:
    kind: str
    normalized: str


def detect_capture(raw: str) -> Detection:
    value = (raw or '').strip()
    parsed = urlparse(value)
    if parsed.scheme in {'http', 'https'} and parsed.netloc:
        host = parsed.netloc.lower().split(':')[0]
        host = host[4:] if host.startswith('www.') else host
        if host in {'instagram.com', 'm.instagram.com'} or host.endswith('.instagram.com'):
            return Detection('instagram', value)
        if host in {'youtube.com', 'm.youtube.com', 'youtu.be', 'youtube-nocookie.com'} or host.endswith('.youtube.com'):
            return Detection('youtube', value)
        return Detection('web', value)
    return Detection('note', value)
