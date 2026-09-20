# 🧠 Segundo Cérebro V2

Aplicação web em Django para capturar, organizar, analisar e relacionar conteúdos pessoais: notas, páginas web, Instagram e YouTube.

A ideia é reduzir o atrito entre **“vi algo interessante”** e **“isso entrou no meu acervo de conhecimento de forma pesquisável e conectada”**.

## O que já existe

### Captura

- captura universal: texto, Instagram, YouTube e páginas web;
- detecção automática da origem;
- normalização de URLs e remoção de parâmetros de rastreamento comuns;
- detecção de duplicados;
- aviso visual quando um conteúdo já está guardado;
- botão **Guardar + outro** para capturas sequenciais;
- **captura em lote de até 100 links**, um por linha;
- lotes aceitam Instagram, YouTube e páginas web misturados;
- listas numeradas ou com marcadores também são aceitas;
- links duplicados no lote são ignorados automaticamente;
- acompanhamento ao vivo do lote enquanto ele estiver processando;
- registro no item indicando se a captura foi **individual** ou **em lote**.

### Instagram

- preserva legenda, hashtags, autor, data e metadados separadamente;
- Reels/vídeos usam extração de mídia e transcrição;
- posts e carrosséis de imagens usam Instaloader;
- OCR visual de slides;
- OCR tenta primeiro **Groq Vision**;
- em erro ou rate limit da Groq, usa **Gemini 3.5 Flash-Lite** como contingência quando configurado;
- leitura slide a slide para reduzir consumo de tokens e facilitar recuperação parcial;
- comparação **Slides × Legenda**;
- opção de reprocessar a leitura visual quando necessário.

### YouTube e áudio

- extração de metadados e legendas com yt-dlp;
- transcrição opcional via Groq Whisper;
- modelo padrão: `whisper-large-v3-turbo`;
- transcrição armazenada separadamente da descrição/legenda;
- segmentos com timestamps são armazenados como chunks.

### Análise com IA

- essência/resumo;
- assunto;
- subassunto;
- tags;
- insights;
- motivo para guardar;
- afirmações que valem conferência;
- comparação legenda × fala ou slides × legenda;
- validação de evidência para reduzir conteúdo inventado pela análise.

### Biblioteca

- busca textual;
- filtros por tipo;
- filtros por status;
- filtro de favoritos;
- acesso ao material original;
- retorno à fonte original;
- cards recentes com status atualizado enquanto o processamento acontece.

### Relações e conexões

- descoberta automática de relações entre conteúdos;
- relações sugeridas pela IA;
- tipos como:
  - relacionado;
  - complementa;
  - contradiz;
  - mesmo assunto;
  - continuação;
  - referência;
- confirmar ou rejeitar sugestões;
- relações confirmadas podem ser reconsideradas depois;
- ações de relações confirmadas ficam em menu discreto;
- tela de Conexões com estatísticas e relações confirmadas.

O **grafo visual interativo** ainda é um próximo passo.

### Interface

- modo claro e modo escuro;
- preferência do tema salva no navegador;
- acompanha automaticamente a preferência do sistema na primeira utilização;
- barra de progresso do processamento;
- atualização automática do andamento;
- interface responsiva para telas menores.

### Processamento

- fila persistente usando o próprio banco;
- worker separado com `python manage.py process_jobs`;
- não exige Redis/Celery nesta fase;
- apenas **um worker** pode ficar ativo por vez;
- jobs interrompidos podem voltar para a fila ao reiniciar o worker;
- processamento de relações é tratado como enriquecimento e não invalida um conteúdo já processado.

## Rodar localmente

Requer Python 3.11+.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Em outro terminal:

```powershell
.venv\Scripts\Activate.ps1
python manage.py process_jobs
```

Abra:

```text
http://127.0.0.1:8000/
```

Sem `DATABASE_URL`, o Django usa SQLite automaticamente.

## Inicializadores e manutenção

Os scripts ficam organizados por sistema operacional:

```text
scripts/
├── common/
│   ├── backup_segundo_cerebro.py
│   └── restaurar_segundo_cerebro.py
├── windows/
│   ├── Segundo Cerebro.bat
│   ├── iniciar_segundo_cerebro.ps1
│   ├── Backup Segundo Cerebro.bat
│   ├── backup_segundo_cerebro.ps1
│   ├── Restaurar Segundo Cerebro.bat
│   ├── restaurar_segundo_cerebro.ps1
│   └── instalar_atalhos_desktop.ps1
└── linux/
    ├── iniciar_segundo_cerebro.sh
    ├── backup_segundo_cerebro.sh
    ├── restaurar_segundo_cerebro.sh
    └── instalar_atalhos_desktop.sh
```

### Windows

Para instalar ou atualizar os atalhos da Área de Trabalho:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\instalar_atalhos_desktop.ps1
```

Isso cria:

- `Segundo Cerebro.bat`;
- `Backup Segundo Cerebro.bat`;
- `Restaurar Segundo Cerebro.bat`.

O inicializador abre servidor e worker em duas abas do Windows Terminal quando `wt.exe` estiver disponível e só abre o navegador quando o Django estiver respondendo.

Os scripts não possuem nome de usuário fixo. Por padrão procuram o projeto em:

```text
%USERPROFILE%\segundo_cerebro
```

Se estiver em outro local, pode ser usada a variável:

```text
SEGUNDO_CEREBRO_DIR
```

### Linux / Zorin OS

```bash
cd ~/segundo_cerebro
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
chmod +x scripts/linux/*.sh
bash scripts/linux/instalar_atalhos_desktop.sh
```

O inicializador tenta usar `gnome-terminal` com duas abas — site e worker — e usa `x-terminal-emulator` como alternativa.

O navegador é aberto com `xdg-open` somente depois que o Django estiver respondendo.

A restauração usa `zenity` quando disponível; sem ele, solicita o caminho do ZIP pelo terminal.

## Backup e restauração

Os backups locais são gravados em:

```text
~/Segundo Cerebro Backups
```

Cada ZIP contém:

- cópia consistente do `db.sqlite3`;
- pasta `media/`, quando existir;
- arquivo de orientação.

São mantidos os 30 backups mais recentes.

O `.env` **não entra no backup**, pois pode conter chaves de API. Guarde uma cópia dele separadamente em local seguro.

## Configuração por ambiente

Crie um arquivo `.env` na raiz do projeto.

Exemplo:

```env
DJANGO_SECRET_KEY=troque-por-uma-chave-grande
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

GROQ_API_KEY=
GROQ_WHISPER_MODEL=whisper-large-v3-turbo
TRANSCRIBE_MEDIA=1
TRANSCRIPTION_LANGUAGE=pt

GROQ_VISION_MODEL=qwen/qwen3.8-27b
GEMINI_API_KEY=
GEMINI_VISION_MODEL=gemini-3.5-flash-lite
ANALYZE_IMAGES=1
MAX_INSTAGRAM_IMAGES=20

GROQ_CHAT_MODEL=openai/gpt-oss-20b
ANALYZE_CONTENT=1
```

Nunca coloque chaves reais no GitHub.

## Estratégia de IA

O fluxo atual é dividido por função:

```text
Vídeo / áudio
└── Groq Whisper

Análise textual
└── Groq Chat / GPT-OSS

Instagram imagem / carrossel
├── Groq Vision
└── Gemini Vision como fallback
```

No OCR de carrosséis, os slides são enviados individualmente. Isso reduz o impacto de rate limits e permite preservar resultados parciais quando apenas um slide falha.

## Comandos úteis

Transcrever mídias já cadastradas:

```bash
python manage.py transcribe_media
```

Item específico:

```bash
python manage.py transcribe_media --item 3
```

Forçar nova transcrição:

```bash
python manage.py transcribe_media --item 3 --force
```

Analisar conteúdos já cadastrados:

```bash
python manage.py analyze_content
```

Item específico:

```bash
python manage.py analyze_content --item 3
```

## PostgreSQL + pgvector

Para subir somente o banco local:

```bash
docker compose up -d db
```

No `.env`:

```env
DATABASE_URL=postgresql://segundo:segundo@localhost:5432/segundo_cerebro
```

O container já usa uma imagem com pgvector.

Nesta fase, embeddings continuam armazenados como JSON para manter compatibilidade com SQLite. A coluna vetorial entra junto com a busca semântica.

## Arquitetura atual

```text
Navegador
   ↓
Django
   ├── Captura universal
   ├── Captura em lote
   ├── Biblioteca
   ├── Item detalhado
   └── Conexões
        ↓
SQLite / PostgreSQL
        ↑
Worker process_jobs
   ├── Instagram vídeo / YouTube
   │    ├── yt-dlp
   │    └── Groq Whisper
   ├── Instagram imagem / carrossel
   │    ├── Instaloader
   │    ├── Groq Vision
   │    └── Gemini Vision fallback
   ├── Web
   │    └── Requests + BeautifulSoup
   ├── Análise textual
   │    └── Groq Chat
   └── Descoberta de relações
```

## Dados locais

Por padrão:

- código → GitHub;
- banco pessoal → `db.sqlite3`;
- arquivos locais → `media/`;
- segredos/chaves → `.env`.

O banco, mídia e `.env` ficam fora do Git através do `.gitignore`.

## Próximos marcos

1. Grafo interativo de conexões.
2. Chunking também de legenda, páginas web e PDFs.
3. Embeddings e busca híbrida.
4. Busca semântica.
5. RAG com citação de trecho exato.
6. Upload e parsing de PDF/documentos.
7. Melhorias de histórico, manutenção e reprocessamento em lote.
8. Deploy gratuito ou de baixo custo.

## Segurança

- não coloque chaves de API no GitHub;
- `.env` está no `.gitignore`;
- `db.sqlite3` está no `.gitignore`;
- `media/` está no `.gitignore`;
- o lock do worker `.process_jobs.lock` também não é versionado.
