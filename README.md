# 🧠 Segundo Cérebro V2

Uma reconstrução do conceito de “segundo cérebro” como aplicação web Django, sem Streamlit.

## O que já existe

- captura universal: texto, Instagram, YouTube e página web;
- detecção automática e normalização da origem;
- biblioteca com pesquisa e filtros por tipo/status/favorito;
- item detalhado com retorno à fonte original;
- Instagram preserva legenda, hashtags e metadados separadamente;
- transcrição opcional de Instagram/YouTube via Groq Whisper;
- análise automática com IA: essência, diferenças legenda/fala, insights, assunto e tags;
- timestamps da fala armazenados como chunks pesquisáveis;
- fila persistente de processamento no próprio banco, sem exigir Redis/Celery;
- worker separado (`process_jobs`) para não bloquear a página;
- estrutura pronta para tags, assuntos, projetos, chunks e relações;
- tela inicial de conexões;
- SQLite para desenvolvimento e PostgreSQL + pgvector preparado para produção.

## Rodar localmente

Requer Python 3.11+.

```bash
python -m venv .venv
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Em outro terminal:

```bash
python manage.py process_jobs
```

Abra `http://127.0.0.1:8000/`.

Sem `DATABASE_URL`, o Django usa SQLite automaticamente.

## Transcrição de Instagram e YouTube

Crie um arquivo `.env` na raiz do projeto:

```env
GROQ_API_KEY=sua-chave-aqui
GROQ_WHISPER_MODEL=whisper-large-v3-turbo
TRANSCRIBE_MEDIA=1
TRANSCRIPTION_LANGUAGE=pt
GROQ_CHAT_MODEL=openai/gpt-oss-20b
ANALYZE_CONTENT=1
```

Novas capturas de Instagram/YouTube serão transcritas automaticamente pelo worker.

Para completar mídias que já estavam cadastradas antes da transcrição existir:

```bash
python manage.py transcribe_media
```

Para um item específico:

```bash
python manage.py transcribe_media --item 3
```

Para retranscrever:

```bash
python manage.py transcribe_media --item 3 --force
```

Para analisar com IA os itens já cadastrados:

```bash
python manage.py analyze_content
```

Ou um item específico:

```bash
python manage.py analyze_content --item 3
```

Legenda e transcrição ficam em campos diferentes. Os segmentos da transcrição guardam início e fim em segundos para futuras citações exatas.

A configuração padrão limita o arquivo enviado à transcrição a 24 MB para permanecer abaixo do limite do tier gratuito.

## PostgreSQL + pgvector

Para subir somente o banco local:

```bash
docker compose up -d db
```

No `.env`:

```env
DATABASE_URL=postgresql://segundo:segundo@localhost:5432/segundo_cerebro
```

O container já traz pgvector. Neste estágio os embeddings continuam como JSON para manter compatibilidade com SQLite; a coluna vetorial será ativada no marco de busca semântica.

## Arquitetura

```text
Navegador
   ↓
Django + HTML/HTMX
   ├── Captura universal
   ├── Biblioteca/filtros
   ├── Item
   └── Conexões
        ↓
Banco
   ├── SQLite
   └── PostgreSQL + pgvector
        ↑
Worker process_jobs
   ├── Instagram / YouTube via yt-dlp
   ├── transcrição Groq / Whisper
   └── Web via Requests + BeautifulSoup
```

## Próximos marcos

1. Chunking também de legenda, web e PDF.
3. Embeddings e busca híbrida.
4. RAG com citação de trecho exato.
5. Sugestões automáticas de relações.
6. Grafo interativo.
7. Upload e parsing de PDF.
8. Deploy gratuito/baixo custo.

## Segurança

Não coloque chaves de API no GitHub. O arquivo `.env` está no `.gitignore`.
