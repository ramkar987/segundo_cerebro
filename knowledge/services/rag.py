from __future__ import annotations

import json
import re

import requests
from django.conf import settings

from .semantic import SemanticSearchUnavailable, semantic_search


class RagUnavailable(Exception):
    pass


RELEVANCE_SYSTEM_PROMPT = """Você faz triagem de trechos para um RAG pessoal.

Sua única tarefa é decidir quais trechos respondem DIRETAMENTE à pergunta.

Regras:
- Marque como relevante apenas o trecho que contenha informação que realmente ajude a responder à pergunta.
- Não aceite um trecho só porque pertence ao mesmo tema geral.
- Não suponha formas de ganhar dinheiro, benefícios, consequências, usos ou conclusões que o trecho não diga.
- Se a pergunta for sobre "formas de ganhar dinheiro", um trecho sobre aprender programação NÃO é suficiente, a menos que o próprio trecho relacione explicitamente programação com renda, trabalho, clientes, venda, monetização ou equivalente.
- Prefira poucos trechos fortes a muitos trechos vagamente relacionados.
- Se nenhum trecho responder diretamente, retorne lista vazia.
- Retorne somente JSON válido no formato {"relevant_sources":[1,2]}.
"""


RAG_SYSTEM_PROMPT = """Você responde perguntas usando EXCLUSIVAMENTE os trechos aprovados do acervo pessoal.

Regras obrigatórias:
- Não use conhecimento externo.
- Não transforme conteúdo adjacente em conselho, estratégia, benefício ou conclusão.
- Só afirme algo que esteja diretamente sustentado por um trecho fornecido.
- Quando o conteúdo original apenas afirma algo, deixe claro que é uma afirmação da fonte.
- Se os trechos não forem suficientes para responder por completo, diga exatamente o que o acervo sustenta e o que não sustenta.
- Cite cada afirmação relevante com [1], [2], [3] etc.
- NÃO use Markdown: não use **, #, tabelas com |, listas com -, ou blocos de código.
- Escreva em português do Brasil, em texto simples, com parágrafos curtos.
- Retorne somente JSON válido no formato:
  {"answer":"texto da resposta com citações [1]","used_sources":[1]}
- used_sources deve conter somente números realmente citados na resposta.
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


def _chat_json(system_prompt: str, user_content: str, max_tokens: int) -> dict:
    response = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {settings.GROQ_API_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'model': settings.GROQ_CHAT_MODEL,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content},
            ],
            'response_format': {'type': 'json_object'},
            'reasoning_effort': 'low',
            'temperature': 0.0,
            'max_completion_tokens': max_tokens,
        },
        timeout=settings.AI_TIMEOUT,
    )

    if response.status_code >= 400:
        raise RagUnavailable(
            f'Groq retornou HTTP {response.status_code}: {response.text[:1000]}'
        )

    raw = (
        response.json()
        .get('choices', [{}])[0]
        .get('message', {})
        .get('content', '')
        .strip()
    )
    if not raw:
        raise RagUnavailable('A IA não retornou uma resposta.')

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RagUnavailable(
            f'A IA retornou JSON inválido: {raw[:800]}'
        ) from exc

    if not isinstance(data, dict):
        raise RagUnavailable('A IA retornou um formato inesperado.')
    return data


def _candidate_sources(question: str) -> list[dict]:
    try:
        hits = semantic_search(
            question,
            top_k=settings.RAG_CANDIDATE_TOP_K,
        )
    except SemanticSearchUnavailable as exc:
        raise RagUnavailable(str(exc)) from exc

    if not hits:
        return []

    # Mantém candidatos próximos do melhor resultado. Isso remove a cauda
    # semântica antes mesmo da triagem por IA.
    best_score = hits[0].score
    floor = max(
        settings.SEMANTIC_MIN_SCORE,
        best_score - settings.RAG_RELATIVE_SCORE_DROP,
    )

    candidates = []
    per_item: dict[int, int] = {}

    for hit in hits:
        if hit.score < floor:
            continue

        item_id = hit.chunk.item_id
        count = per_item.get(item_id, 0)
        if count >= settings.RAG_MAX_CHUNKS_PER_ITEM:
            continue
        per_item[item_id] = count + 1

        number = len(candidates) + 1
        item = hit.chunk.item
        candidates.append({
            'number': number,
            'item': item,
            'chunk': hit.chunk,
            'score': hit.score,
            'locator': _source_locator(hit.chunk),
            'excerpt': hit.chunk.text,
        })

        if len(candidates) >= settings.RAG_CANDIDATE_TOP_K:
            break

    return candidates


def _relevance_gate(question: str, candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []

    blocks = []
    for source in candidates:
        blocks.append(
            f'FONTE [{source["number"]}]\n'
            f'Título: {source["item"].title or "Sem título"}\n'
            f'Trecho: {source["excerpt"]}'
        )

    payload = (
        f'PERGUNTA:\n{question.strip()}\n\n'
        'TRECHOS CANDIDATOS:\n\n'
        + '\n\n---\n\n'.join(blocks)
    )

    data = _chat_json(
        RELEVANCE_SYSTEM_PROMPT,
        payload,
        max_tokens=350,
    )

    raw_ids = data.get('relevant_sources') or []
    allowed = set()
    for value in raw_ids:
        try:
            allowed.add(int(value))
        except (TypeError, ValueError):
            continue

    return [
        source
        for source in candidates
        if source['number'] in allowed
    ][:settings.RAG_TOP_K]


def answer_from_library(question: str) -> dict:
    if not settings.GROQ_API_KEY:
        raise RagUnavailable('GROQ_API_KEY não configurada.')

    candidates = _candidate_sources(question)
    relevant = _relevance_gate(question, candidates)

    if not relevant:
        return {
            'answer': (
                'Encontrei conteúdos relacionados ao tema, mas nenhum trecho '
                'responde diretamente à pergunta com segurança.'
            ),
            'sources': [],
            'model': settings.GROQ_CHAT_MODEL,
        }

    # Renumera somente as fontes aprovadas.
    sources = []
    context_blocks = []
    for number, source in enumerate(relevant, start=1):
        copied = dict(source)
        copied['number'] = number
        sources.append(copied)
        context_blocks.append(
            f'FONTE [{number}]\n'
            f'Título: {source["item"].title or "Sem título"}\n'
            f'Tipo: {source["item"].get_type_display()}\n'
            f'Local: {source["locator"]}\n'
            f'Trecho: {source["excerpt"]}'
        )

    payload = (
        f'PERGUNTA:\n{question.strip()}\n\n'
        'TRECHOS APROVADOS:\n\n'
        + '\n\n---\n\n'.join(context_blocks)
    )

    data = _chat_json(
        RAG_SYSTEM_PROMPT,
        payload,
        max_tokens=1200,
    )

    answer = str(data.get('answer') or '').strip()
    if not answer:
        raise RagUnavailable('A IA não retornou texto de resposta.')

    raw_used = data.get('used_sources') or []
    used = set()
    for value in raw_used:
        try:
            used.add(int(value))
        except (TypeError, ValueError):
            continue

    # Também considera citações realmente presentes, caso o modelo esqueça
    # de preencher used_sources corretamente.
    for match in re.findall(r'\[(\d+)\]', answer):
        used.add(int(match))

    if used:
        sources = [
            source
            for source in sources
            if source['number'] in used
        ]

    return {
        'answer': answer,
        'sources': sources,
        'model': settings.GROQ_CHAT_MODEL,
    }
