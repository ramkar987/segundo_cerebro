"""
Integração opcional com a Groq API.

Usada apenas na aba "Perguntar à IA": pega as notas mais relevantes
(achadas pelo search.py) e pede para um modelo da Groq responder a
pergunta do usuário com base SOMENTE nelas — um RAG simples, sem
banco vetorial.
"""

from typing import Dict, List

from groq import Groq

MODELOS_DISPONIVEIS = {
    "Llama 3.3 70B (mais inteligente)": "llama-3.3-70b-versatile",
    "Llama 3.1 8B (mais rápido)": "llama-3.1-8b-instant",
}


def montar_contexto(notas: List[Dict]) -> str:
    blocos = [f"### {n['titulo']}\n{n['conteudo']}" for n in notas]
    return "\n\n".join(blocos)


def perguntar_as_notas(api_key: str, pergunta: str, notas_relevantes: List[Dict], modelo: str) -> str:
    client = Groq(api_key=api_key)
    contexto = montar_contexto(notas_relevantes)

    system_prompt = (
        "Você é um assistente que responde com base exclusivamente nas notas pessoais "
        "fornecidas a seguir. Se a resposta não estiver nas notas, diga claramente que não "
        "encontrou essa informação nas notas do usuário — não invente nada. Responda em "
        "português, de forma direta, e cite o título da nota usada entre colchetes, "
        "por exemplo: [Nome da nota]."
    )
    user_prompt = f"NOTAS:\n{contexto}\n\nPERGUNTA: {pergunta}"

    resposta = client.chat.completions.create(
        model=modelo,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=1000,
    )
    return resposta.choices[0].message.content
