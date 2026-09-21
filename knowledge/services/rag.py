from __future__ import annotations

import json
import re

import requests
from django.conf import settings

from .semantic import SemanticSearchUnavailable, semantic_search


class RagUnavailable(Exception):
    pass


RELEVANCE_SYSTEM_PROMPT = """Você faz triagem ESTRITA de trechos para um RAG pessoal.

Sua única tarefa é decidir quais trechos respondem DIRETAMENTE à pergunta, sem completar a relação por conhecimento externo.

Regras:
- Marque como relevante somente quando o PRÓPRIO TRECHO contém a informação necessária para responder à pergunta.
- Mesmo tema, mesma área ou palavras parecidas NÃO bastam.
- Exija que a relação entre a ação e o objetivo perguntado esteja explícita no trecho.
- Se a pergunta for "como ganhar dinheiro", "como gerar renda", "como monetizar" ou equivalente:
  * ACEITE somente trechos que relacionem explicitamente uma ação a ganhar dinheiro, renda, receita, lucro, venda, cliente, cobrança, monetização ou equivalente.
  * REJEITE trechos que apenas falem em gastar pouco, investir pouco, anunciar, aprender uma habilidade, usar uma ferramenta, fazer marketing ou criar conteúdo sem dizer que isso gera renda/receita/vendas/clientes.
  * "Anunciar custa R$ 40 por dia" NÃO é evidência de como ganhar dinheiro.
  * "Um site ensina programação" NÃO é evidência de como ganhar dinheiro.
- Se a pergunta pede causa, benefício, risco, comparação, passo a passo ou recomendação, o trecho precisa sustentar exatamente esse tipo de resposta.
- Prefira 1 ou 2 fontes fortes a várias fontes apenas relacionadas.
- Se nenhum trecho responder diretamente, retorne lista vazia.
- Retorne somente JSON válido no formato {"relevant_sources":[1,2]}.
"""


RAG_SYSTEM_PROMPT = """Você responde perguntas usando EXCLUSIVAMENTE os trechos aprovados do acervo pessoal.

Regras obrigatórias:
- Não use conhecimento externo.
- Não transforme conteúdo adjacente em conselho, estratégia, benefício, consequência ou conclusão.
- Só afirme algo que esteja diretamente sustentado por um trecho fornecido.
- Não converta "baixo custo" em "forma de ganhar dinheiro".
- Não converta "aprender uma habilidade" em "forma de renda" sem o trecho dizer isso.
- Não converta "anunciar" em "ganhar dinheiro" sem o trecho ligar explicitamente anúncio a receita, vendas ou clientes.
- Não use conectivos causais como "isso pode gerar", "isso permite ganhar", "por isso dá para lucrar" ou equivalentes, a menos que essa relação esteja explícita no trecho.
- Preserve a modalidade da fonte: se ela diz que "pessoas estão ganhando dinheiro fazendo X" e depois apresenta uma ferramenta, diga exatamente isso; não conclua que usar a ferramenta, por si só, gera renda.
- Quando o conteúdo original apenas afirma algo, escreva "a fonte afirma", "o conteúdo sugere" ou equivalente.
- Se o acervo sustentar apenas uma parte da pergunta, responda somente essa parte e diga que não encontrou suporte para ampliar.
- Se houver apenas uma fonte realmente útil, uma resposta curta com uma única fonte é MELHOR do que completar com ideias fracas.
- Cite cada afirmação relevante com [1], [2], [3] etc.
- NÃO use Markdown: não use **, #, tabelas com |, listas com -, ou blocos de código.
- Escreva em português do Brasil, em texto simples, com parágrafos curtos.
- Evite frases como "estratégias aprovadas". Prefira "No acervo, encontrei..." ou "A fonte afirma...".
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

    # A busca vetorial apenas encontra candidatos. A triagem por IA abaixo
    # decide relevância direta; não descartamos cedo demais um trecho que pode
    # ser semanticamente diferente, mas ainda responder exatamente à pergunta.
    candidates = []
    per_item: dict[int, int] = {}

    for hit in hits:
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
