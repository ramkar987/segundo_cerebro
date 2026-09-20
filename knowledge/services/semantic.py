from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Chunk, Item


class SemanticIndexSkipped(Exception):
    """Indexação semântica não disponível, sem invalidar o item."""


class SemanticSearchUnavailable(Exception):
    """Busca semântica não disponível no ambiente atual."""


@dataclass
class SemanticHit:
    chunk: Chunk
    score: float


def _clean_text(value: str) -> str:
    value = (value or '').replace('\r\n', '\n').replace('\r', '\n')
    value = re.sub(r'[ \t]+', ' ', value)
    value = re.sub(r'\n{3,}', '\n\n', value)
    return value.strip()


def split_text(value: str, max_chars: int | None = None) -> list[str]:
    """Quebra texto em blocos legíveis, sem cortar agressivamente frases."""
    text = _clean_text(value)
    if not text:
        return []

    limit = max_chars or settings.SEMANTIC_CHUNK_CHARS
    paragraphs = [
        ' '.join(part.split())
        for part in re.split(r'\n\s*\n', text)
        if part.strip()
    ]

    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= limit:
            pieces.append(paragraph)
            continue

        sentences = [
            part.strip()
            for part in re.split(r'(?<=[.!?…])\s+', paragraph)
            if part.strip()
        ]
        if len(sentences) == 1:
            words = paragraph.split()
            current: list[str] = []
            current_len = 0
            for word in words:
                addition = len(word) + (1 if current else 0)
                if current and current_len + addition > limit:
                    pieces.append(' '.join(current))
                    current = [word]
                    current_len = len(word)
                else:
                    current.append(word)
                    current_len += addition
            if current:
                pieces.append(' '.join(current))
            continue

        current = ''
        for sentence in sentences:
            if not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= limit:
                current += ' ' + sentence
            else:
                pieces.append(current)
                current = sentence
        if current:
            pieces.append(current)

    chunks: list[str] = []
    current = ''
    for piece in pieces:
        if not current:
            current = piece
        elif len(current) + 2 + len(piece) <= limit:
            current += '\n\n' + piece
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if chunk.strip()]


def _slide_chunks(item: Item) -> list[dict]:
    text = item.content or ''
    if item.type != Item.Type.INSTAGRAM or '[SLIDE ' not in text:
        return []

    matches = list(
        re.finditer(
            r'\[SLIDE\s+(\d+)\]\s*(.*?)(?=\n\n\[SLIDE\s+\d+\]|\Z)',
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
    )
    result = []
    for match in matches:
        body = _clean_text(match.group(2))
        if not body:
            continue
        slide = int(match.group(1))
        for part in split_text(body):
            result.append({
                'kind': Chunk.Kind.CONTENT,
                'text': part,
                'page': slide,
            })
    return result


def _group_transcript(existing: list[Chunk]) -> list[dict]:
    if not existing:
        return []

    limit = settings.SEMANTIC_CHUNK_CHARS
    groups: list[dict] = []
    texts: list[str] = []
    start = None
    end = None

    def flush():
        nonlocal texts, start, end
        text = ' '.join(texts).strip()
        if text:
            groups.append({
                'kind': Chunk.Kind.TRANSCRIPT,
                'text': text,
                'start_seconds': start,
                'end_seconds': end,
            })
        texts = []
        start = None
        end = None

    for chunk in existing:
        text = _clean_text(chunk.text)
        if not text:
            continue

        candidate = ' '.join(texts + [text]).strip()
        if texts and len(candidate) > limit:
            flush()

        if not texts:
            start = chunk.start_seconds
        texts.append(text)
        if chunk.end_seconds is not None:
            end = chunk.end_seconds

    flush()
    return groups


def build_chunks(item: Item) -> list[Chunk]:
    """Reconstrói chunks pesquisáveis usando somente material de origem."""
    source = item.source

    old_transcript = list(
        item.chunks.filter(kind=Chunk.Kind.TRANSCRIPT).order_by('position')
    )

    specs: list[dict] = []

    slide_specs = _slide_chunks(item)
    if slide_specs:
        specs.extend(slide_specs)
    elif item.content:
        specs.extend(
            {'kind': Chunk.Kind.CONTENT, 'text': text}
            for text in split_text(item.content)
        )

    caption = _clean_text(source.caption)
    if caption and caption != _clean_text(item.content):
        specs.extend(
            {'kind': Chunk.Kind.CAPTION, 'text': text}
            for text in split_text(caption)
        )

    transcript_groups = _group_transcript(old_transcript)
    if transcript_groups:
        specs.extend(transcript_groups)
    elif source.transcript:
        specs.extend(
            {'kind': Chunk.Kind.TRANSCRIPT, 'text': text}
            for text in split_text(source.transcript)
        )

    # Evita indexar o mesmo texto repetido em duas origens.
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for spec in specs:
        text = _clean_text(spec.get('text', ''))
        if not text:
            continue
        key = (spec['kind'], text.casefold())
        if key in seen:
            continue
        seen.add(key)
        spec['text'] = text
        deduped.append(spec)

    with transaction.atomic():
        item.chunks.all().delete()
        chunks = [
            Chunk(
                item=item,
                kind=spec['kind'],
                text=spec['text'],
                position=position,
                page=spec.get('page'),
                start_seconds=spec.get('start_seconds'),
                end_seconds=spec.get('end_seconds'),
                embedding=[],
            )
            for position, spec in enumerate(deduped)
        ]
        if chunks:
            Chunk.objects.bulk_create(chunks)

    return list(item.chunks.order_by('position'))


def _embedding_endpoint(batch: bool = False) -> str:
    method = 'batchEmbedContents' if batch else 'embedContent'
    return (
        'https://generativelanguage.googleapis.com/v1beta/models/'
        f'{settings.GEMINI_EMBEDDING_MODEL}:{method}'
    )


def _embedding_headers() -> dict:
    if not settings.GEMINI_API_KEY:
        raise SemanticSearchUnavailable('GEMINI_API_KEY não configurada.')
    return {
        'x-goog-api-key': settings.GEMINI_API_KEY,
        'Content-Type': 'application/json',
    }


def _post_embedding(payload: dict, batch: bool = False):
    response = None
    for attempt in range(4):
        response = requests.post(
            _embedding_endpoint(batch=batch),
            headers=_embedding_headers(),
            json=payload,
            timeout=settings.AI_TIMEOUT,
        )

        if response.status_code not in {429, 500, 502, 503, 504}:
            return response
        if attempt >= 3:
            return response

        retry_after = response.headers.get('Retry-After')
        try:
            wait_seconds = float(retry_after) if retry_after else (2 ** attempt) * 3
        except (TypeError, ValueError):
            wait_seconds = (2 ** attempt) * 3

        time.sleep(max(2.0, min(wait_seconds, 45.0)))

    return response


def embed_query(text: str) -> list[float]:
    query = _clean_text(text)
    if not query:
        raise SemanticSearchUnavailable('Consulta vazia.')

    response = _post_embedding({
        'model': f'models/{settings.GEMINI_EMBEDDING_MODEL}',
        'content': {'parts': [{'text': query}]},
        'embedContentConfig': {
            'taskType': 'RETRIEVAL_QUERY',
            'outputDimensionality': settings.EMBEDDING_DIMENSIONS,
        },
    })

    if response.status_code >= 400:
        raise SemanticSearchUnavailable(
            f'Gemini Embeddings retornou HTTP {response.status_code}: '
            f'{response.text[:1000]}'
        )

    values = response.json().get('embedding', {}).get('values') or []
    if not values:
        raise SemanticSearchUnavailable('Gemini não retornou embedding para a consulta.')
    return [float(value) for value in values]


def _embed_documents(chunks: list[Chunk], title: str) -> list[list[float]]:
    if not chunks:
        return []

    result: list[list[float]] = []
    batch_size = max(1, settings.EMBEDDING_BATCH_SIZE)

    for offset in range(0, len(chunks), batch_size):
        group = chunks[offset: offset + batch_size]
        requests_payload = []
        for chunk in group:
            requests_payload.append({
                'model': f'models/{settings.GEMINI_EMBEDDING_MODEL}',
                'content': {'parts': [{'text': chunk.text}]},
                'embedContentConfig': {
                    'taskType': 'RETRIEVAL_DOCUMENT',
                    'title': title[:300],
                    'outputDimensionality': settings.EMBEDDING_DIMENSIONS,
                },
            })

        response = _post_embedding(
            {'requests': requests_payload},
            batch=True,
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f'Gemini Embeddings retornou HTTP {response.status_code}: '
                f'{response.text[:1000]}'
            )

        embeddings = response.json().get('embeddings') or []
        if len(embeddings) != len(group):
            raise RuntimeError(
                'Gemini Embeddings retornou quantidade inesperada de vetores.'
            )

        for entry in embeddings:
            values = entry.get('values') or []
            if not values:
                raise RuntimeError('Gemini retornou embedding vazio.')
            result.append([float(value) for value in values])

    return result


def _set_index_metadata(item: Item, **values) -> None:
    source = item.source
    metadata = dict(source.metadata or {})
    current = dict(metadata.get('semantic_index') or {})
    current.update(values)
    metadata['semantic_index'] = current
    source.metadata = metadata
    source.save(update_fields=['metadata'])


def index_item(item: Item, force: bool = False) -> int:
    if not settings.GEMINI_API_KEY:
        raise SemanticIndexSkipped('GEMINI_API_KEY não configurada.')

    if not settings.SEMANTIC_SEARCH_ENABLED:
        raise SemanticIndexSkipped('Busca semântica está desativada.')

    existing = item.chunks.exclude(embedding=[]).count()
    metadata = (item.source.metadata or {}).get('semantic_index') or {}
    same_model = (
        metadata.get('model') == settings.GEMINI_EMBEDDING_MODEL
        and metadata.get('dimensions') == settings.EMBEDDING_DIMENSIONS
    )

    if existing and same_model and not force:
        return existing

    chunks = build_chunks(item)
    if not chunks:
        _set_index_metadata(
            item,
            status='skipped',
            model=settings.GEMINI_EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
            chunks=0,
            message='Item sem conteúdo indexável.',
            indexed_at=timezone.now().isoformat(),
        )
        raise SemanticIndexSkipped('Item sem conteúdo indexável.')

    try:
        embeddings = _embed_documents(chunks, item.title or item.get_type_display())
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        Chunk.objects.bulk_update(chunks, ['embedding'])

        _set_index_metadata(
            item,
            status='done',
            model=settings.GEMINI_EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
            chunks=len(chunks),
            indexed_at=timezone.now().isoformat(),
            message='',
        )
        return len(chunks)
    except Exception as exc:
        _set_index_metadata(
            item,
            status='error',
            model=settings.GEMINI_EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
            chunks=0,
            indexed_at=timezone.now().isoformat(),
            message=str(exc)[:1000],
        )
        raise


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return -1.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return -1.0
    return dot / (left_norm * right_norm)


def semantic_search(
    query: str,
    top_k: int | None = None,
    item_ids: set[int] | None = None,
) -> list[SemanticHit]:
    query_embedding = embed_query(query)
    limit = top_k or settings.SEMANTIC_TOP_K

    qs = (
        Chunk.objects.exclude(embedding=[])
        .select_related('item', 'item__source')
        .order_by('item_id', 'position')
    )
    if item_ids is not None:
        if not item_ids:
            return []
        qs = qs.filter(item_id__in=item_ids)

    hits: list[SemanticHit] = []
    for chunk in qs:
        score = _cosine_similarity(query_embedding, chunk.embedding)
        if score < settings.SEMANTIC_MIN_SCORE:
            continue
        hits.append(SemanticHit(chunk=chunk, score=score))

    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]


def semantic_item_results(
    query: str,
    item_ids: set[int] | None = None,
    max_items: int = 100,
) -> list[dict]:
    hits = semantic_search(
        query,
        top_k=max(settings.SEMANTIC_TOP_K * 3, max_items * 2),
        item_ids=item_ids,
    )

    results: list[dict] = []
    seen_items: set[int] = set()

    for hit in hits:
        item = hit.chunk.item
        if item.pk in seen_items:
            continue
        seen_items.add(item.pk)
        results.append({
            'item': item,
            'score': hit.score,
            'chunk': hit.chunk,
            'excerpt': hit.chunk.text,
        })
        if len(results) >= max_items:
            break

    return results
