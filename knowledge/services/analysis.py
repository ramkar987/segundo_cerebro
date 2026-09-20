from __future__ import annotations

import json

import requests
from django.conf import settings

from ..models import Item, Tag, Topic


class AnalysisSkipped(Exception):
    """Análise pulada sem invalidar o item capturado."""


SYSTEM_PROMPT = """Você organiza um Segundo Cérebro pessoal.
Analise apenas o conteúdo fornecido, sem inventar fatos.
Quando houver legenda e transcrição, trate-as como fontes diferentes:
- não suponha que dizem a mesma coisa;
- identifique o que aparece apenas na fala, apenas na legenda e em ambas.
Responda sempre em português do Brasil.
Retorne somente um objeto JSON válido, sem Markdown, com exatamente estas chaves:
summary: string curto e informativo;
video_explains: array de strings;
caption_adds: array de strings;
common_points: array de strings;
insights: array de strings;
why_keep: string;
topic: string curto;
tags: array de 3 a 10 strings curtas.
Para conteúdos sem vídeo, use video_explains e caption_adds como arrays vazios e use insights para os pontos principais.
Evite repetir a mesma informação em várias seções.
"""


def _text(value) -> str:
    return (value or '').strip()


def _list_of_strings(value, limit: int = 10) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = _text(str(item))
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _analysis_payload(item: Item) -> dict:
    source = item.source
    return {
        'type': item.type,
        'title': item.title,
        'content': item.content,
        'caption': source.caption,
        'transcript': source.transcript,
        'source_author': item.source_author,
        'source_url': item.source_url,
    }


def _call_groq(item: Item) -> dict:
    if not settings.GROQ_API_KEY:
        raise AnalysisSkipped('GROQ_API_KEY não configurada.')
    if not settings.ANALYZE_CONTENT:
        raise AnalysisSkipped('ANALYZE_CONTENT está desativado.')

    payload = _analysis_payload(item)
    if not any(_text(payload[key]) for key in ('content', 'caption', 'transcript')):
        raise AnalysisSkipped('Item sem conteúdo suficiente para análise.')

    response = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {settings.GROQ_API_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'model': settings.GROQ_CHAT_MODEL,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': json.dumps(payload, ensure_ascii=False),
                },
            ],
            'response_format': {'type': 'json_object'},
            'reasoning_effort': 'low',
            'temperature': 0.2,
            'max_completion_tokens': 1800,
        },
        timeout=settings.AI_TIMEOUT,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f'Groq retornou HTTP {response.status_code}: {response.text[:1200]}'
        )

    body = response.json()
    raw = body['choices'][0]['message']['content']
    data = json.loads(raw)

    return {
        'summary': _text(data.get('summary')),
        'video_explains': _list_of_strings(data.get('video_explains')),
        'caption_adds': _list_of_strings(data.get('caption_adds')),
        'common_points': _list_of_strings(data.get('common_points')),
        'insights': _list_of_strings(data.get('insights')),
        'why_keep': _text(data.get('why_keep')),
        'topic': _text(data.get('topic'))[:120],
        'tags': [t[:80] for t in _list_of_strings(data.get('tags'), limit=10)],
        'model': settings.GROQ_CHAT_MODEL,
    }


def _get_or_create_topic(name: str):
    existing = Topic.objects.filter(name__iexact=name).first()
    return existing or Topic.objects.create(name=name)


def _get_or_create_tag(name: str):
    existing = Tag.objects.filter(name__iexact=name).first()
    return existing or Tag.objects.create(name=name)


def analyze_item(item: Item) -> dict:
    data = _call_groq(item)

    item.summary = data['summary']
    item.analysis = data
    item.save(update_fields=['summary', 'analysis', 'updated_at'])

    if data['topic']:
        item.topics.add(_get_or_create_topic(data['topic']))

    for tag_name in data['tags']:
        if tag_name:
            item.tags.add(_get_or_create_tag(tag_name))

    return data
