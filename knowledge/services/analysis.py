from __future__ import annotations

import json
import re
import unicodedata

import requests
from django.conf import settings

from ..models import Item, Tag, Topic


class AnalysisSkipped(Exception):
    """Análise pulada sem invalidar o item capturado."""


BROAD_TOPICS = [
    'Inteligência Artificial',
    'Tecnologia',
    'Programação',
    'Dados',
    'Finanças',
    'Saúde',
    'Educação',
    'Trabalho',
    'Produtividade',
    'Jurídico',
    'Viagens',
    'Casa',
    'Veículos',
    'Família',
    'Entretenimento',
    'Outros',
]


SYSTEM_PROMPT = """Você organiza um Segundo Cérebro pessoal.
Analise somente o material fornecido. Não use conhecimento externo para completar lacunas e não invente fatos.

REGRAS DE PROVENIÊNCIA:
- caption = texto semântico da legenda, já sem hashtags decorativas;
- transcript = fala transcrita do vídeo;
- visual_text = texto extraído dos slides/imagens de um post ou carrossel;
- content = conteúdo principal para notas/páginas que não sejam vídeo nem carrossel.

Quando caption e transcript existirem, compare-os de forma estrita:
- video_explains: somente informações que aparecem na transcrição e NÃO aparecem semanticamente na legenda;
- caption_adds: somente informações que aparecem semanticamente na legenda e NÃO aparecem na transcrição;
- common_points: somente ideias realmente expressas nas DUAS fontes.

Quando caption e visual_text existirem e transcript estiver vazio, use as MESMAS chaves, mas:
- video_explains: somente informações presentes nos slides/imagens e NÃO na legenda;
- caption_adds: somente informações presentes na legenda e NÃO nos slides/imagens;
- common_points: somente ideias realmente expressas nas DUAS fontes.

Não transforme uma ideia presente só em uma das fontes em "ponto em comum" por inferência.
Se uma categoria não tiver conteúdo real, retorne [].
Não trate hashtags, emojis ou palavras-chave soltas como conteúdo adicional da legenda.

REGRAS DE CONFIABILIDADE:
- Você está organizando o que A FONTE AFIRMA, não verificando se é verdade.
- Não apresente alegações sobre gratuidade, preços, elegibilidade, benefícios, disponibilidade, segurança ou regras de serviços como fatos confirmados.
- summary deve usar formulações como "O conteúdo apresenta...", "O autor afirma..." ou equivalentes quando houver alegações não verificadas.
- claims_to_verify deve conter apenas alegações concretas feitas pela fonte que fariam diferença prática e deveriam ser verificadas antes de agir.
- insights deve conter apenas ideias gerais, procedimentos ou aprendizados diretamente sustentados pelo material; NÃO use insights para repetir alegações que exigem verificação, especialmente gratuidade, preço, elegibilidade, prazo, benefício ou disponibilidade. Essas alegações pertencem SOMENTE a claims_to_verify.
- NÃO acrescente riscos, conselhos, implicações legais, segurança, ética ou termos de serviço se isso não estiver explicitamente no material.
- Para CADA insight e claim_to_verify forneça evidence: um pequeno trecho LITERAL copiado de caption, transcript ou content que sustente aquele ponto.
- Se não houver um trecho literal que sustente o ponto, NÃO inclua o ponto.
- why_keep é meta-organização: explique por que vale manter o item, sem validar a veracidade das alegações.

ORGANIZAÇÃO:
- Escolha a categoria MAIS ESPECÍFICA entre as categorias amplas disponíveis. Se o conteúdo for principalmente sobre ferramentas, modelos, serviços ou uso de IA, use "Inteligência Artificial", e não "Tecnologia".
- topic DEVE ser exatamente uma destas categorias:
  Inteligência Artificial, Tecnologia, Programação, Dados, Finanças, Saúde, Educação, Trabalho, Produtividade, Jurídico, Viagens, Casa, Veículos, Família, Entretenimento, Outros.
- subtopic deve ser curto, específico e reutilizável, com 1 a 4 palavras. Ex.: "Benefícios educacionais".
- detalhes ainda mais específicos vão para tags.
- tags devem ser curtas, úteis para busca e sem duplicar desnecessariamente topic/subtopic.
- video_explains: no máximo 6 itens.
- caption_adds: no máximo 4 itens.
- common_points: no máximo 4 itens.
- insights: no máximo 4 itens.
- claims_to_verify: no máximo 6 itens.
- why_keep: uma frase.

Responda sempre em português do Brasil.
Retorne SOMENTE um objeto JSON válido, sem Markdown, com exatamente estas chaves:
summary: string;
video_explains: array de strings;
caption_adds: array de strings;
common_points: array de strings;
insights: array de objetos {"text": string, "evidence": string};
why_keep: string;
claims_to_verify: array de objetos {"text": string, "evidence": string};
topic: string;
subtopic: string;
tags: array de 3 a 10 strings.

Para conteúdos sem vídeo e sem visual_text, use video_explains, caption_adds e common_points como arrays vazios.
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


def _semantic_caption(raw: str) -> str:
    """Remove hashtags/linhas decorativas só para a análise, preservando o original no banco."""
    cleaned_lines = []
    for raw_line in (raw or '').splitlines():
        line = re.sub(r'(?<!\w)#[\wÀ-ÿ_]+', '', raw_line)
        line = ' '.join(line.split()).strip()
        if not line:
            continue
        if not re.search(r'[A-Za-zÀ-ÿ0-9]', line):
            continue
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)


def _normalize_for_evidence(value: str) -> str:
    value = unicodedata.normalize('NFKD', value or '')
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    return ' '.join(value.split())


def _validated_points(value, source_text: str, limit: int) -> list[str]:
    """Aceita apenas pontos cuja evidência literal aparece no material de origem."""
    if not isinstance(value, list):
        return []

    source_norm = _normalize_for_evidence(source_text)
    result = []

    for entry in value:
        if not isinstance(entry, dict):
            continue

        text = _text(entry.get('text'))
        evidence = _text(entry.get('evidence'))
        evidence_norm = _normalize_for_evidence(evidence)

        # Exige uma evidência minimamente informativa e realmente presente na fonte.
        if not text or len(evidence_norm) < 8:
            continue
        if evidence_norm not in source_norm:
            continue
        if text not in result:
            result.append(text)
        if len(result) >= limit:
            break

    return result


def _analysis_payload(item: Item) -> dict:
    source = item.source
    metadata = source.metadata or {}
    media_kind = metadata.get('media_kind') or ''
    visual_text = (
        item.content
        if item.type == Item.Type.INSTAGRAM
        and media_kind in {'image', 'carousel'}
        else ''
    )
    content = '' if visual_text else item.content

    return {
        'type': item.type,
        'title': item.title,
        'content': content,
        'caption': _semantic_caption(source.caption),
        'transcript': source.transcript,
        'visual_text': visual_text,
        'source_author': item.source_author,
        'source_url': item.source_url,
    }


def _safe_topic(value: str) -> str:
    requested = _text(value)
    for topic in BROAD_TOPICS:
        if requested.casefold() == topic.casefold():
            return topic
    return 'Outros'


def _call_groq(item: Item) -> dict:
    if not settings.GROQ_API_KEY:
        raise AnalysisSkipped('GROQ_API_KEY não configurada.')
    if not settings.ANALYZE_CONTENT:
        raise AnalysisSkipped('ANALYZE_CONTENT está desativado.')

    payload = _analysis_payload(item)
    if not any(
        _text(payload[key])
        for key in ('content', 'caption', 'transcript', 'visual_text')
    ):
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

    source_text = '\n'.join(
        part for part in (
            payload.get('content', ''),
            payload.get('caption', ''),
            payload.get('transcript', ''),
            payload.get('visual_text', ''),
        )
        if part
    )

    return {
        'summary': _text(data.get('summary')),
        'video_explains': _list_of_strings(data.get('video_explains'), limit=6),
        'caption_adds': _list_of_strings(data.get('caption_adds'), limit=4),
        'common_points': _list_of_strings(data.get('common_points'), limit=4),
        'insights': _validated_points(data.get('insights'), source_text, limit=4),
        'why_keep': _text(data.get('why_keep')),
        'claims_to_verify': _validated_points(
            data.get('claims_to_verify'), source_text, limit=6
        ),
        'topic': _safe_topic(data.get('topic')),
        'subtopic': _text(data.get('subtopic'))[:80],
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

    item.topics.add(_get_or_create_topic(data['topic']))

    for tag_name in data['tags']:
        if tag_name:
            item.tags.add(_get_or_create_tag(tag_name))

    return data
