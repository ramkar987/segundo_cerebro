from __future__ import annotations

import json
import re
import unicodedata

import requests
from django.conf import settings
from django.db.models import Q

from ..models import Item, Relation


class RelationDiscoverySkipped(Exception):
    """Descoberta pulada sem invalidar o item."""


ALLOWED_TYPES = {
    Relation.Type.RELATED,
    Relation.Type.COMPLEMENTS,
    Relation.Type.CONTRADICTS,
    Relation.Type.SAME_TOPIC,
    Relation.Type.CONTINUATION,
    Relation.Type.REFERENCE,
}


RELATION_PROMPT = """Você ajuda a organizar relações entre itens de um Segundo Cérebro.
Receberá um item principal e uma lista curta de candidatos.

Escolha SOMENTE relações úteis para navegação futura. Não crie relação apenas porque os itens pertencem a uma categoria ampla parecida.
Use apenas o conteúdo resumido fornecido; não invente informações.

Tipos permitidos:
- related: tratam do mesmo problema/ideia de forma relevante;
- complements: um acrescenta informação útil ao outro;
- contradicts: há conflito explícito entre afirmações dos dois;
- same_topic: tratam claramente do mesmo assunto específico;
- continuation: um parece continuação/aprofundamento do outro;
- reference: um serve como referência prática para compreender/aplicar o outro.

Regras:
- retorne no máximo 5 relações;
- confiança entre 0 e 1;
- só inclua confiança >= 0.65;
- explicação curta e concreta;
- não use "contradicts" sem conflito explícito;
- não trate duas coisas como relacionadas só porque ambas são de Tecnologia/IA/etc.

Retorne SOMENTE JSON válido:
{"relations":[{"target_id":123,"relation_type":"related","confidence":0.82,"explanation":"..."}]}
"""


def _norm(value: str) -> str:
    value = unicodedata.normalize('NFKD', value or '')
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', value.lower()).split())


def _item_profile(item: Item) -> dict:
    topics = list(item.topics.values_list('name', flat=True))
    tags = list(item.tags.values_list('name', flat=True))
    analysis = item.analysis or {}
    return {
        'id': item.id,
        'title': item.title,
        'summary': item.summary,
        'topic': topics[0] if topics else '',
        'subtopic': analysis.get('subtopic') or '',
        'tags': tags,
        'why_keep': analysis.get('why_keep') or '',
    }


def _candidate_score(base: dict, candidate: dict) -> float:
    score = 0.0

    if base['topic'] and _norm(base['topic']) == _norm(candidate['topic']):
        score += 0.30

    if (
        base['subtopic']
        and candidate['subtopic']
        and _norm(base['subtopic']) == _norm(candidate['subtopic'])
    ):
        score += 0.38

    base_tags = {_norm(t) for t in base['tags'] if _norm(t)}
    other_tags = {_norm(t) for t in candidate['tags'] if _norm(t)}
    shared = base_tags & other_tags
    score += min(len(shared) * 0.10, 0.40)

    # Pequeno sinal lexical em resumo/título; não decide sozinho.
    base_words = set(_norm(f"{base['title']} {base['summary']}").split())
    other_words = set(_norm(f"{candidate['title']} {candidate['summary']}").split())
    stop = {
        'a', 'o', 'e', 'de', 'da', 'do', 'das', 'dos', 'em', 'um', 'uma',
        'para', 'por', 'com', 'que', 'como', 'se', 'no', 'na', 'nos', 'nas',
    }
    overlap = (base_words - stop) & (other_words - stop)
    if len(overlap) >= 3:
        score += min(len(overlap) * 0.02, 0.12)

    return min(score, 1.0)


def candidate_items(item: Item, limit: int = 8) -> list[tuple[Item, float]]:
    if not item.analysis:
        return []

    base = _item_profile(item)
    qs = (
        Item.objects.exclude(pk=item.pk)
        .exclude(status=Item.Status.ARCHIVED)
        .exclude(analysis={})
        .prefetch_related('topics', 'tags')
    )

    existing_ids = set()
    for rel in Relation.objects.filter(
        Q(source=item) | Q(target=item)
    ).values('source_id', 'target_id'):
        existing_ids.add(
            rel['target_id'] if rel['source_id'] == item.id else rel['source_id']
        )

    scored = []
    for other in qs.iterator():
        if other.id in existing_ids:
            continue
        profile = _item_profile(other)
        score = _candidate_score(base, profile)
        if score >= 0.35:
            scored.append((other, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def discover_relations(item: Item) -> list[Relation]:
    if not settings.GROQ_API_KEY:
        raise RelationDiscoverySkipped('GROQ_API_KEY não configurada.')

    candidates = candidate_items(item)
    if not candidates:
        return []

    base = _item_profile(item)
    candidate_payload = []
    allowed_ids = set()

    for other, score in candidates:
        profile = _item_profile(other)
        profile['candidate_score'] = round(score, 3)
        candidate_payload.append(profile)
        allowed_ids.add(other.id)

    response = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {settings.GROQ_API_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'model': settings.GROQ_CHAT_MODEL,
            'messages': [
                {'role': 'system', 'content': RELATION_PROMPT},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {'item': base, 'candidates': candidate_payload},
                        ensure_ascii=False,
                    ),
                },
            ],
            'response_format': {'type': 'json_object'},
            'reasoning_effort': 'low',
            'temperature': 0.1,
            'max_completion_tokens': 1200,
        },
        timeout=settings.AI_TIMEOUT,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f'Groq retornou HTTP {response.status_code}: {response.text[:1200]}'
        )

    data = json.loads(response.json()['choices'][0]['message']['content'])
    raw_relations = data.get('relations') or []
    created = []

    if not isinstance(raw_relations, list):
        return created

    for entry in raw_relations[:5]:
        if not isinstance(entry, dict):
            continue

        try:
            target_id = int(entry.get('target_id'))
            confidence = float(entry.get('confidence'))
        except (TypeError, ValueError):
            continue

        relation_type = str(entry.get('relation_type') or '').strip()
        explanation = str(entry.get('explanation') or '').strip()[:1000]

        if target_id not in allowed_ids:
            continue
        if relation_type not in ALLOWED_TYPES:
            continue
        if confidence < 0.65 or confidence > 1:
            continue

        target = next((other for other, _ in candidates if other.id == target_id), None)
        if not target:
            continue

        # Não cria duplicata em orientação oposta.
        duplicate = Relation.objects.filter(
            Q(source=item, target=target) | Q(source=target, target=item)
        ).exists()
        if duplicate:
            continue

        created.append(
            Relation.objects.create(
                source=item,
                target=target,
                relation_type=relation_type,
                origin=Relation.Origin.AI,
                status=Relation.Status.SUGGESTED,
                confidence=confidence,
                explanation=explanation,
            )
        )

    return created
