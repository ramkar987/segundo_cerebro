from __future__ import annotations

import json

import requests
from django.conf import settings

from ..models import Item, Tag, Topic


class AnalysisSkipped(Exception):
    """Análise pulada sem invalidar o item capturado."""


SYSTEM_PROMPT = """Você organiza um Segundo Cérebro pessoal.
Analise somente o material fornecido. Não use conhecimento externo para completar lacunas e não invente fatos.

REGRAS DE PROVENIÊNCIA:
- caption = texto escrito na legenda da publicação;
- transcript = fala transcrita do vídeo;
- content = conteúdo principal para notas/páginas sem vídeo.
Quando caption e transcript existirem, compare-os de forma estrita:
- video_explains: somente informações que aparecem na transcrição e NÃO aparecem na legenda;
- caption_adds: somente informações que aparecem na legenda e NÃO aparecem na transcrição;
- common_points: somente informações realmente presentes nas DUAS fontes.
Nunca coloque em common_points algo que apareça em apenas uma das fontes.
Se uma categoria não tiver conteúdo exclusivo, retorne [].

REGRAS DE CONFIABILIDADE:
- Você está organizando o que A FONTE AFIRMA, não verificando se é verdade.
- Não apresente alegações sobre gratuidade, preços, elegibilidade, benefícios, disponibilidade, segurança ou regras de serviços como fatos confirmados.
- summary deve usar formulações como "O conteúdo apresenta...", "O autor afirma..." ou equivalentes quando houver alegações não verificadas.
- claims_to_verify deve listar afirmações concretas que fariam diferença prática e deveriam ser conferidas na fonte oficial antes de o usuário agir.
- Não crie claims_to_verify para opiniões triviais ou informações sem consequência prática.

ORGANIZAÇÃO:
- topic deve ser uma categoria ampla, reutilizável e estável, idealmente 1 a 3 palavras.
- Não use uma frase específica como assunto. Ex.: prefira "Inteligência Artificial" a "Acesso gratuito a IA com e-mail educacional".
- detalhes específicos devem ir para tags.
- tags devem ser curtas, úteis para busca e sem duplicar desnecessariamente o topic.
- insights devem capturar o que vale lembrar, sem repetir literalmente video_explains/caption_adds/common_points.
- why_keep deve explicar em uma frase por que este item merece existir no Segundo Cérebro.

Responda sempre em português do Brasil.
Retorne SOMENTE um objeto JSON válido, sem Markdown, com exatamente estas chaves:
summary: string;
video_explains: array de strings;
caption_adds: array de strings;
common_points: array de strings;
insights: array de strings;
why_keep: string;
claims_to_verify: array de strings;
topic: string;
tags: array de 3 a 10 strings.

Para conteúdos sem vídeo, use video_explains, caption_adds e common_points como arrays vazios.
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
            'temperature': 0.1,
            'max_completion_tokens': 2000,
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
        'claims_to_verify': _list_of_strings(data.get('claims_to_verify'), limit=8),
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

    # A análise substitui a classificação automática anterior. Projetos e
    # relações manuais continuam intocados.
    item.topics.clear()
    item.tags.clear()

    if data['topic']:
        item.topics.add(_get_or_create_topic(data['topic']))

    for tag_name in data['tags']:
        if tag_name:
            item.tags.add(_get_or_create_tag(tag_name))

    return data
