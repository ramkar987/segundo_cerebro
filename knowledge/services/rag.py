from __future__ import annotations

import json

import requests
from django.conf import settings

from .semantic import SemanticSearchUnavailable, semantic_search


class RagUnavailable(Exception):
    pass


RAG_SYSTEM_PROMPT = """Você responde perguntas usando EXCLUSIVAMENTE o acervo pessoal fornecido.

Regras obrigatórias:
- Não use conhecimento externo.
- Não complete lacunas por inferência como se fossem fatos do acervo.
- Cada afirmação factual da resposta deve ser sustentada por pelo menos uma fonte fornecida.
- Cite as fontes usando exatamente [1], [2], [3] etc.
- Se o acervo não trouxer informação suficiente, diga claramente que não encontrou suporte suficiente.
- Diferencie quando o conteúdo original apenas afirma algo de quando existe verificação. O acervo pode conter alegações não verificadas.
- Responda em português do Brasil, de forma clara e direta.
"""


def _source_locator(chunk) -> str:
    if chunk.kind == 'transcript' and chunk.start_seconds is not None:
        start = int(chunk.start_seconds)
        minutes, seconds = divmod(start, 60)
        return f'timestamp {minutes}:{seconds:02d}'
    if chunk.kind == 'pdf' and chunk.page:
        return f'página {chunk.page}'
    if (
        chunk.kind == 'content'
        and chunk.page
        and chunk.item.type == 'instagram'
    ):
        return f'slide {chunk.page}'
    return chunk.get_kind_display().lower()


def answer_from_library(question: str) -> dict:
    if not settings.GROQ_API_KEY:
        raise RagUnavailable('GROQ_API_KEY não configurada.')

    try:
        hits = semantic_search(question, top_k=settings.RAG_TOP_K)
    except SemanticSearchUnavailable as exc:
        raise RagUnavailable(str(exc)) from exc

    if not hits:
        return {
            'answer': (
                'Não encontrei trechos semanticamente próximos o suficiente '
                'no acervo para responder com segurança.'
            ),
            'sources': [],
            'model': settings.GROQ_CHAT_MODEL,
        }

    sources = []
    context_blocks = []
    per_item: dict[int, int] = {}

    for hit in hits:
        item_id = hit.chunk.item_id
        count = per_item.get(item_id, 0)
        if count >= settings.RAG_MAX_CHUNKS_PER_ITEM:
            continue
        per_item[item_id] = count + 1

        number = len(sources) + 1
        item = hit.chunk.item
        locator = _source_locator(hit.chunk)
        sources.append({
            'number': number,
            'item': item,
            'chunk': hit.chunk,
            'score': hit.score,
            'locator': locator,
            'excerpt': hit.chunk.text,
        })
        context_blocks.append(
            f'FONTE [{number}]\n'
            f'Título: {item.title or "Sem título"}\n'
            f'Tipo: {item.get_type_display()}\n'
            f'Local: {locator}\n'
            f'Trecho: {hit.chunk.text}'
        )

        if len(sources) >= settings.RAG_TOP_K:
            break

    payload = (
        f'PERGUNTA:\n{question.strip()}\n\n'
        'TRECHOS DO ACERVO:\n\n'
        + '\n\n---\n\n'.join(context_blocks)
    )

    response = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {settings.GROQ_API_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'model': settings.GROQ_CHAT_MODEL,
            'messages': [
                {'role': 'system', 'content': RAG_SYSTEM_PROMPT},
                {'role': 'user', 'content': payload},
            ],
            'reasoning_effort': 'low',
            'temperature': 0.1,
            'max_completion_tokens': 1800,
        },
        timeout=settings.AI_TIMEOUT,
    )

    if response.status_code >= 400:
        raise RagUnavailable(
            f'Groq retornou HTTP {response.status_code}: {response.text[:1000]}'
        )

    body = response.json()
    answer = (
        body.get('choices', [{}])[0]
        .get('message', {})
        .get('content', '')
        .strip()
    )
    if not answer:
        raise RagUnavailable('A IA não retornou uma resposta.')

    return {
        'answer': answer,
        'sources': sources,
        'model': settings.GROQ_CHAT_MODEL,
    }
