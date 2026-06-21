# 🧠 Segundo Cérebro

Notas pessoais com busca inteligente — e agora também importação de vídeos:
cole um link, o app baixa o áudio, transcreve localmente com Whisper, gera
resumo e tags com IA (Groq) e salva tudo como uma nota pesquisável, igual às
que você escreve manualmente.

## ⚠️ Um arquivo está faltando neste pacote

Não consegui buscar o conteúdo do `downloader.py` do seu repo `transcriber`
(o GitHub bloqueou essa página específica nas minhas tentativas — os outros
3 arquivos, `transcriber.py`, `limits.py` e `formatter.py`, eu consegui ler
e já estão aqui, fiéis ao original).

**Copie o `downloader.py` do seu repo `ramkar987/transcriber` para esta
pasta, sem alterações.** Ele precisa exportar: `download_audio()`,
`extract_metadata()`, `MediaMetadata`, `sanitize_filename()`,
`UnsupportedURLError`, `PrivateOrUnavailableVideoError`,
`LongDurationVideoError`, `DownloadError` — é exatamente o que já está
publicado lá, então é só colar o arquivo.

O app não roda (nem a aba de notas) enquanto esse arquivo não estiver na
pasta, porque o `app.py` importa tudo logo no topo.

## Como rodar

```bash
pip install -r requirements.txt
# também precisa do ffmpeg instalado no sistema:
# Ubuntu/Debian: sudo apt install ffmpeg
# Mac: brew install ffmpeg
streamlit run app.py
```

O app abre em `http://localhost:8501`. As notas ficam em `notas.db`
(SQLite), criado automaticamente. Se você já tinha notas de uma versão
anterior do app, elas são preservadas — o banco recebe uma migração
automática das colunas novas (`tipo`, `fonte_url`, `transcricao_completa`).

## Usando a IA (Groq)

Duas formas de configurar a chave:

1. **Sessão/local**: cole a chave no campo da barra lateral. Não é salva em
   disco, só dura enquanto o navegador está aberto.
2. **Deploy (recomendado p/ Streamlit Cloud)**: crie `.streamlit/secrets.toml`:
   ```toml
   GROQ_API_KEY = "sua_chave_aqui"
   ```
   ou defina a variável de ambiente `GROQ_API_KEY`. Assim ninguém precisa
   digitar nada.

Crie sua chave gratuita em [console.groq.com](https://console.groq.com).

## As 4 abas

- **📝 Minhas notas** — CRUD normal. Notas vindas de vídeo aparecem com 🎥 e
  link para a fonte; a transcrição completa fica num checkbox para não
  poluir a tela.
- **🎥 Importar vídeo** — cole a URL, escolha o modelo Whisper e o idioma,
  opcionalmente marque tradução. A transcrição roda local (sem chave); o
  resumo e as tags usam a Groq, por isso essa aba exige a chave configurada.
- **🔍 Buscar** — TF-IDF + busca por palavra-chave, sem IA. Agora também
  vasculha a transcrição completa dos vídeos, não só o resumo.
- **💬 Perguntar à IA** — pergunta em linguagem natural, a IA responde com
  base nas notas mais relevantes (manuais ou de vídeo) e cita qual usou.

## Decisões de design (e como mudar se quiser outra coisa)

- **O conteúdo da nota de vídeo é o resumo, não a transcrição inteira.**
  Isso mantém a busca e o contexto enviado à IA mais enxutos. A transcrição
  completa fica guardada à parte (coluna `transcricao_completa`) e também
  entra na busca por relevância — só não é o texto principal exibido.
- **Tags são geradas a partir do resumo, não da transcrição crua** — mais
  rápido e barato, e o resumo já concentra os pontos principais.
- **Transcrição é sempre local (Whisper)**, nunca usa a Groq — assim importar
  vídeo não consome cota de IA além do resumo/tags/tradução.

## Estrutura do projeto

- `app.py` — interface Streamlit (4 páginas)
- `db.py` — persistência em SQLite (notas manuais e de vídeo)
- `search.py` — busca por relevância via TF-IDF (sem IA)
- `ai.py` — toda a integração com a Groq (resumo, tradução, tags, Q&A)
- `downloader.py` — baixa áudio do vídeo (yt-dlp) · **copie do seu repo `transcriber`**
- `transcriber.py` — transcrição local com Whisper
- `formatter.py` — formata a transcrição em Markdown
- `limits.py` — limites de tamanho/duração de áudio
- `packages.txt` — dependência de sistema (`ffmpeg`) para deploy no Streamlit Cloud

## Próximos passos possíveis

- Busca semântica de verdade com embeddings locais, em vez de TF-IDF.
- Editar/deletar a transcrição completa de uma nota de vídeo direto na UI.
- Importar vários vídeos de uma vez (lote).
- Mostrar trecho com timestamp clicável na transcrição.

Se quiser que eu implemente algum desses, é só pedir.
