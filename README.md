# 🧠 Segundo Cérebro

Um app de notas pessoais com busca inteligente. Funciona 100% sem IA (busca
por palavra-chave e por relevância via TF-IDF); com uma chave gratuita da
Groq, ganha também a aba "Perguntar à IA", que responde perguntas com base
no conteúdo das suas próprias notas.

## Como rodar

```bash
pip install -r requirements.txt
streamlit run app.py
```

O app abre em `http://localhost:8501`. As notas ficam salvas em
`notas.db` (SQLite), no mesmo diretório do projeto — esse arquivo é criado
automaticamente na primeira execução.

## Usando a parte de IA (opcional)

1. Crie uma chave gratuita em [console.groq.com](https://console.groq.com).
2. Cole a chave no campo da barra lateral do app.
3. Vá na aba "💬 Perguntar à IA" e faça perguntas como
   *"o que eu decidi sobre o projeto X em março?"*.

A chave fica só na sessão do navegador (não é salva em disco). Sem ela, as
abas "Minhas notas" e "Buscar" funcionam normalmente.

## Estrutura do projeto

- `app.py` — interface Streamlit (as 3 páginas: notas, busca, IA)
- `db.py` — persistência em SQLite (CRUD de notas)
- `search.py` — busca por relevância via TF-IDF (sem IA, sem API)
- `groq_client.py` — chamada à API da Groq para responder perguntas com base
  nas notas (RAG simples, sem banco vetorial)

## Próximos passos possíveis

- Busca semântica de verdade com embeddings (ex: `sentence-transformers`
  rodando localmente), em vez de TF-IDF.
- Transcrição de notas de voz com o Whisper da Groq.
- Exportar notas para Markdown ou backup em `.zip`.
- Editor de texto rico (Markdown) em vez de texto puro.
- Grafo de notas relacionadas (estilo Obsidian), ligando notas por tags ou
  por similaridade.

Se quiser que eu implemente algum desses, é só pedir.
