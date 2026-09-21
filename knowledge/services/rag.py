from __future__ import annotations

import json
import re
import time

import requests
from django.conf import settings

from .groq_http import post_groq
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

Sua prioridade é fidelidade ao material, não completar uma resposta a qualquer custo.

Regras obrigatórias:
- Não use conhecimento externo.
- Não transforme conteúdo adjacente em conselho, estratégia, benefício, consequência ou conclusão.
- Só afirme algo que esteja diretamente sustentado por um trecho fornecido.
- Separe mentalmente três níveis:
  1. AFIRMAÇÃO DA FONTE: algo que o próprio trecho diz.
  2. DEMONSTRAÇÃO DA FONTE: ferramenta, procedimento ou exemplo que o trecho mostra.
  3. LACUNA: algo necessário para responder melhor, mas que o trecho não explica.
- Nunca transforme uma DEMONSTRAÇÃO em uma AFIRMAÇÃO causal. Exemplo: se a fonte diz que pessoas ganham dinheiro com cibersegurança e depois demonstra uma ferramenta, não diga que usar a ferramenta "permite ganhar dinheiro" ou "possibilita oferecer serviços", a menos que isso esteja explícito.
- Não converta "baixo custo" em "forma de ganhar dinheiro".
- Não converta "aprender uma habilidade" em "forma de renda" sem o trecho dizer isso.
- Não converta "anunciar" em "ganhar dinheiro" sem o trecho ligar explicitamente anúncio a receita, vendas ou clientes.
- Não use conectivos causais como "isso pode gerar", "isso permite ganhar", "por isso dá para lucrar", "possibilita oferecer serviços" ou equivalentes, a menos que essa relação esteja explícita no trecho.
- Quando o conteúdo original apenas afirma algo, escreva "a fonte afirma", "o conteúdo diz" ou equivalente.
- Se o acervo sustentar apenas parte da pergunta, responda somente essa parte.
- Quando houver uma lacuna importante, diga claramente: "O trecho não explica..." ou "O acervo não mostra...".
- Se a pergunta pedir "como fazer", "como ganhar dinheiro", "como monetizar", "quanto cobrar", "como conseguir clientes" ou equivalente, e os trechos só mostrarem parte do caminho, TERMINE a resposta explicitando o que falta no acervo. Exemplo: "O trecho não explica como monetizar esse trabalho, encontrar clientes ou definir preço."
- Se houver apenas uma fonte realmente útil, uma resposta curta com uma única fonte é MELHOR do que completar com ideias fracas.
- Cite cada afirmação relevante com [1], [2], [3] etc.
- NÃO use Markdown: não use **, #, tabelas com |, listas com -, ou blocos de código.
- Escreva em português do Brasil, em texto simples, com parágrafos curtos.
- Prefira construções como: "No acervo, encontrei uma fonte que afirma..." e depois "O trecho também mostra..." e, se necessário, "O trecho não explica...".
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


def _parse_json_object(raw: str, provider: str) -> dict:
    raw = (raw or '').strip()
    if not raw:
        raise RagUnavailable(f'{provider} não retornou uma resposta.')

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RagUnavailable(
            f'{provider} retornou JSON inválido: {raw[:800]}'
        ) from exc

    if not isinstance(data, dict):
        raise RagUnavailable(f'{provider} retornou um formato inesperado.')
    return data


def _gemini_chat_json(
    system_prompt: str,
    user_content: str,
    max_tokens: int,
) -> tuple[dict, str]:
    if not settings.GEMINI_API_KEY:
        raise RagUnavailable('Gemini não está configurado como fallback.')

    endpoint = (
        'https://generativelanguage.googleapis.com/v1beta/models/'
        f'{settings.GEMINI_TEXT_MODEL}:generateContent'
    )

    response = None
    for attempt in range(2):
        response = requests.post(
            endpoint,
            headers={
                'x-goog-api-key': settings.GEMINI_API_KEY,
                'Content-Type': 'application/json',
            },
            json={
                'system_instruction': {
                    'parts': [{'text': system_prompt}],
                },
                'contents': [
                    {
                        'role': 'user',
                        'parts': [{'text': user_content}],
                    }
                ],
                'generationConfig': {
                    'temperature': 0.0,
                    'maxOutputTokens': max_tokens,
                    'responseMimeType': 'application/json',
                },
            },
            timeout=settings.AI_TIMEOUT,
        )

        if response.status_code != 429 or attempt >= 1:
            break

        retry_after = response.headers.get('Retry-After')
        try:
            wait_seconds = float(retry_after) if retry_after else 3.0
        except (TypeError, ValueError):
            wait_seconds = 3.0
        time.sleep(max(1.0, min(wait_seconds, 10.0)))

    if response is None or response.status_code >= 400:
        status = response.status_code if response is not None else 'sem resposta'
        detail = response.text[:900] if response is not None else ''
        raise RagUnavailable(
            f'Gemini retornou HTTP {status}: {detail}'
        )

    body = response.json()
    candidates = body.get('candidates') or []
    if not candidates:
        raise RagUnavailable(
            f'Gemini não retornou candidato: {json.dumps(body)[:800]}'
        )

    parts = candidates[0].get('content', {}).get('parts', [])
    raw = ''.join(
        str(part.get('text') or '')
        for part in parts
        if isinstance(part, dict)
    ).strip()

    return (
        _parse_json_object(raw, 'Gemini'),
        f'Gemini · {settings.GEMINI_TEXT_MODEL}',
    )


def _chat_json(
    system_prompt: str,
    user_content: str,
    max_tokens: int,
) -> tuple[dict, str]:
    groq_error = ''

    if settings.GROQ_API_KEY:
        try:
            # Consulta interativa: não fica aguardando vários retries enquanto
            # o worker consome a mesma cota. Se Groq estiver ocupada, cai logo
            # para Gemini.
            response = post_groq(
                {
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
                max_attempts=1,
            )

            if response.status_code < 400:
                raw = (
                    response.json()
                    .get('choices', [{}])[0]
                    .get('message', {})
                    .get('content', '')
                    .strip()
                )
                return (
                    _parse_json_object(raw, 'Groq'),
                    f'Groq · {settings.GROQ_CHAT_MODEL}',
                )

            groq_error = (
                f'Groq HTTP {response.status_code}: {response.text[:700]}'
            )
        except Exception as exc:
            groq_error = f'Groq: {exc}'

    if settings.GEMINI_API_KEY:
        try:
            return _gemini_chat_json(
                system_prompt,
                user_content,
                max_tokens,
            )
        except RagUnavailable as exc:
            if groq_error:
                raise RagUnavailable(
                    f'{groq_error} | Fallback Gemini: {exc}'
                ) from exc
            raise

    if groq_error:
        raise RagUnavailable(groq_error)
    raise RagUnavailable('Nenhum provedor de IA configurado para o RAG.')


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

    data, _provider = _chat_json(
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
    if not settings.GROQ_API_KEY and not settings.GEMINI_API_KEY:
        raise RagUnavailable('Nenhum provedor de IA configurado para o RAG.')

    candidates = _candidate_sources(question)
    relevant = _relevance_gate(question, candidates)

    if not relevant:
        return {
            'answer': (
                'Encontrei conteúdos relacionados ao tema, mas nenhum trecho '
                'responde diretamente à pergunta com segurança.'
            ),
            'sources': [],
            'model': 'Groq/Gemini',
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

    data, provider_model = _chat_json(
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

    # Garante auditabilidade mesmo se o modelo esquecer a marcação no texto.
    cited = {
        int(value)
        for value in re.findall(r'\[(\d+)\]', answer)
    }
    source_numbers = [source['number'] for source in sources]
    missing_citations = [
        number for number in source_numbers if number not in cited
    ]
    if missing_citations:
        answer = answer.rstrip()
        if answer and answer[-1] not in '.!?':
            answer += '.'
        answer += ' ' + ' '.join(
            f'[{number}]' for number in missing_citations
        )

    return {
        'answer': answer,
        'sources': sources,
        'model': provider_model,
    }
