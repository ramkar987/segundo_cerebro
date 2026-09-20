# 🧠 Segundo Cérebro V2

Uma reconstrução do conceito de “segundo cérebro” como aplicação web Django, sem Streamlit.

## O que já existe neste primeiro marco

- captura universal: texto, Instagram, YouTube e página web;
- detecção automática da origem;
- biblioteca com pesquisa e filtros por tipo/status/favorito;
- item detalhado com retorno à fonte original;
- Instagram preserva legenda/descrição e hashtags originais separadamente;
- fila persistente de processamento no próprio banco, sem exigir Redis/Celery;
- worker separado (`process_jobs`) para que capturas demoradas não bloqueiem a página;
- estrutura de dados pronta para tags, assuntos, projetos, chunks e relações;
- tela inicial de conexões;
- desenvolvimento com SQLite e produção preparada para PostgreSQL;
- Docker Compose com PostgreSQL + pgvector disponível para o marco semântico.

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
   ├── SQLite (dev simples)
   └── PostgreSQL + pgvector (servidor)
        ↑
Worker process_jobs
   ├── Instagram / YouTube via yt-dlp
   └── Web via Requests + BeautifulSoup
```

## Rodar localmente — modo simples

Requer Python 3.11+.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
python manage.py makemigrations knowledge
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Em outro terminal, com o mesmo ambiente virtual ativo:

```bash
python manage.py process_jobs
```

Abra `http://127.0.0.1:8000/`.

Sem `DATABASE_URL`, o Django usa SQLite automaticamente. Isso é proposital para tornar o primeiro teste muito fácil.

## PostgreSQL + pgvector

Para subir somente o banco local:

```bash
docker compose up -d db
```

Copie `.env.example` para `.env` ou exporte a variável:

```bash
export DATABASE_URL='postgresql://segundo:segundo@localhost:5432/segundo_cerebro'
```

> O container já traz a extensão pgvector disponível. Neste marco os embeddings ainda são armazenados como JSON para a mesma migration funcionar também em SQLite. No marco de busca semântica ativaremos uma coluna vetorial/indexação no PostgreSQL sem mudar a camada de captura.

## Instagram

O Instagram é uma fonte de primeira classe. O worker usa os metadados que `yt-dlp` consegue obter e mantém:

- URL original;
- autor/perfil quando disponível;
- título;
- data quando disponível;
- legenda/descrição;
- hashtags originais;
- metadados da publicação.

A transcrição de áudio será adicionada no marco seguinte. Legenda e transcrição continuarão em campos diferentes.

## Próximos marcos

1. Transcrição de Instagram/YouTube com Whisper/Groq.
2. Resumo, tags e assunto automáticos.
3. Chunking com timestamps/páginas.
4. Embeddings e busca híbrida.
5. RAG com citação de trecho exato.
6. Sugestões automáticas de relações.
7. Grafo interativo.
8. Upload e parsing de PDF.
9. Deploy gratuito/baixo custo.

## Segurança

Não coloque chaves de API no GitHub. Use variáveis de ambiente ou `.env` local, que já está no `.gitignore`.
