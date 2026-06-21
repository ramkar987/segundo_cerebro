"""
Tudo que envolve a Groq API: resumir transcrições, traduzir, gerar tags e
responder perguntas com base nas notas (RAG simples, sem banco vetorial).

A chave da Groq pode vir de três lugares, nessa ordem de prioridade:
1. Passada diretamente na chamada (ex: o campo da barra lateral do app)
2. st.secrets["GROQ_API_KEY"] (forma recomendada em deploy no Streamlit Cloud)
3. variável de ambiente GROQ_API_KEY (rodando local)
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from groq import Groq

MODELOS_DISPONIVEIS = {
    "Llama 3.3 70B (mais inteligente)": "llama-3.3-70b-versatile",
    "Llama 3.1 8B (mais rápido)": "llama-3.1-8b-instant",
}


class AIServiceError(Exception):
    """Erro genérico do serviço de IA."""


def get_groq_client(api_key: Optional[str] = None) -> Groq:
    if not api_key:
        try:
            import streamlit as st  # type: ignore

            api_key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            api_key = None

    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        raise AIServiceError(
            "Nenhuma chave da Groq configurada (nem na barra lateral, nem em "
            "secrets.toml, nem na variável de ambiente GROQ_API_KEY)."
        )

    return Groq(api_key=api_key)


def _chat(client: Groq, system_prompt: str, user_prompt: str, model: str) -> str:
    resposta = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return (resposta.choices[0].message.content or "").strip()


def summarize_transcript(
    transcript_text: str,
    model: str = "llama-3.3-70b-versatile",
    api_key: Optional[str] = None,
) -> str:
    """Gera um resumo curto e objetivo da transcrição."""
    client = get_groq_client(api_key)
    system_prompt = (
        "Você é um assistente que resume transcrições em português com clareza e objetividade. "
        "Você também deve gerar tags e estrutura para um segundo cérebro."
    )
    user_prompt = (
        "Você vai analisar uma transcrição de vídeo do Instagram ou YouTube.\n\n"
        "Regras:\n"
        "- Responda em português do Brasil.\n"
        "- Não invente fatos.\n"
        "- Seja objetivo e útil para um segundo cérebro.\n"
        "- Se houver pouca informação, sinalize isso com clareza.\n\n"
        "Formato obrigatório:\n"
        "1. RESUMO: 5 bullets curtos, cada um com no máximo 25 palavras.\n"
        "2. TAKEAWAYS: 3 a 5 itens com a estrutura 'Insight | Por que importa'.\n"
        "3. TAGS: 10 a 15 tags separadas por vírgula, em minúsculas, sem hashtags.\n"
        "4. PERGUNTA FUTURA: 1 pergunta para pesquisa posterior.\n\n"
        f"TRANSCRIÇÃO:\n{transcript_text}"
    )
    return _chat(client, system_prompt, user_prompt, model)


def translate_transcript(
    transcript_text: str,
    target_language: str,
    model: str = "llama-3.3-70b-versatile",
    api_key: Optional[str] = None,
) -> str:
    """Traduz a transcrição para o idioma de destino."""
    client = get_groq_client(api_key)
    system_prompt = "Você é um tradutor profissional que preserva sentido, tom e clareza."
    user_prompt = (
        f"Traduza o texto abaixo para {target_language}. "
        "Não adicione explicações, apenas a tradução:\n\n"
        f"{transcript_text}"
    )
    return _chat(client, system_prompt, user_prompt, model)


def generate_tags(
    text: str,
    model: str = "llama-3.1-8b-instant",
    api_key: Optional[str] = None,
    max_tags: int = 6,
) -> List[str]:
    """Gera tags curtas a partir de um texto — idealmente o resumo, não a transcrição crua inteira, para ser mais rápido e mais barato."""
    client = get_groq_client(api_key)
    system_prompt = (
        "Você gera tags curtas (1 a 2 palavras cada) em português para organizar notas "
        "pessoais. Responda APENAS com as tags separadas por vírgula, sem numeração, "
        "sem explicações."
    )
    user_prompt = f"Gere até {max_tags} tags relevantes para o conteúdo abaixo:\n\n{text}"
    resposta = _chat(client, system_prompt, user_prompt, model)
    tags = [t.strip().lower() for t in resposta.split(",") if t.strip()]
    return tags[:max_tags]


def montar_contexto(notas: List[Dict]) -> str:
    blocos = [f"### {n['titulo']}\n{n['conteudo']}" for n in notas]
    return "\n\n".join(blocos)


def perguntar_as_notas(
    pergunta: str,
    notas_relevantes: List[Dict],
    model: str = "llama-3.3-70b-versatile",
    api_key: Optional[str] = None,
) -> str:
    client = get_groq_client(api_key)
    contexto = montar_contexto(notas_relevantes)

    system_prompt = (
        "Você é um assistente que responde com base exclusivamente nas notas pessoais "
        "fornecidas a seguir. Se a resposta não estiver nas notas, diga claramente que não "
        "encontrou essa informação nas notas do usuário — não invente nada. Responda em "
        "português, de forma direta, e cite o título da nota usada entre colchetes, "
        "por exemplo: [Nome da nota]."
    )

    user_prompt = f"NOTAS:\n{contexto}\n\nPERGUNTA: {pergunta}"
    return _chat(client, system_prompt, user_prompt, model)
