# 🧠 Segundo Cérebro

Notas pessoais com busca inteligente, importação de vídeos (transcrição local
+ resumo/tags/tradução por IA) e backup manual em JSON.

## Como rodar

```bash
pip install -r requirements.txt
# precisa do ffmpeg instalado no sistema:
# Ubuntu/Debian: sudo apt install ffmpeg
# Mac: brew install ffmpeg
streamlit run app.py
```

O app abre em `http://localhost:8501`. As notas ficam em `notas.db`
(SQLite), criado automaticamente — schema migra sozinho a cada nova versão,
então notas antigas não se perdem ao atualizar o código.

## Usando a IA (Groq)

Duas formas de configurar a chave, e o app agora detecta as duas
corretamente (a barra lateral mostra "✅ IA disponível" com a origem usada):

1. **Sessão/local**: cole a chave no campo da barra lateral. Não é salva em
   disco, só dura enquanto o navegador está aberto.
2. **Deploy (recomendado p/ Streamlit Cloud)**: em *App settings → Secrets*:
   ```toml
   GROQ_API_KEY = "sua_chave_aqui"
   ```
   Nesse caso pode deixar o campo da barra lateral em branco.

Crie sua chave gratuita em [console.groq.com](https://console.groq.com).

> **Nota:** o prompt usado pela IA (em `ai.py`) foi ajustado manualmente —
> qualquer atualização futura nesse arquivo deve preservar essas mudanças,
> não sobrescrever com uma versão genérica.

## As 4 abas

- **📝 Minhas notas** — CRUD normal, com paginação (10 por página) para
  quando a lista crescer. Notas de vídeo aparecem com 🎥, link pra fonte e
  opção de ver a transcrição completa. Tem um expander de backup
  (exportar/importar `.json`) logo no topo.
- **🎥 Importar vídeo** — cole a URL, escolha modelo Whisper e idioma,
  opcionalmente marque tradução. Se a URL já tiver sido importada antes, o
  app avisa e bloqueia reimportação acidental (dá pra forçar se quiser
  atualizar o resumo). Transcrição roda local (sem chave); resumo e tags
  usam a Groq.
- **🔍 Buscar** — TF-IDF + busca por palavra-chave, sem IA. Também vasculha
  a transcrição completa dos vídeos.
- **💬 Perguntar à IA** — pergunta em linguagem natural, com base nas notas
  mais relevantes, cita qual nota usou.

## Estrutura do projeto

- `app.py` — interface Streamlit (4 páginas + paginação + detecção de chave)
- `db.py` — persistência em SQLite: notas manuais e de vídeo, checagem de
  vídeo duplicado (`buscar_nota_por_fonte_url`), export/import de backup
- `search.py` — busca por relevância via TF-IDF (sem IA)
- `ai.py` — toda a integração com a Groq (resumo, tradução, tags, Q&A) —
  **prompt customizado manualmente, não regenerar do zero**
- `downloader.py` — baixa áudio do vídeo via `yt-dlp`. Reescrito do zero
  (não foi possível recuperar o original do repo `transcriber` por bloqueio
  do GitHub); funciona, mas pode ter pequenas diferenças de comportamento
  do original
- `transcriber.py` — transcrição local com Whisper
- `formatter.py` — formata a transcrição em Markdown
- `limits.py` — limites de tamanho/duração de áudio
- `packages.txt` — dependência de sistema (`ffmpeg`) para deploy no Streamlit Cloud

## Persistência no Streamlit Cloud — atenção

O `notas.db` vive no disco do container e **é apagado** quando o app dorme
por inatividade e é "acordado" de novo, quando você dá `git push`, ou num
reboot manual. Use o backup em JSON (aba "Minhas notas") regularmente,
principalmente depois de importar vídeos.

## Limitações conhecidas

- A detecção de vídeo duplicado compara a URL exata — `youtube.com/watch?v=X`
  e `youtu.be/X` do mesmo vídeo não são reconhecidos como iguais. Avise se
  quiser que eu normalize isso.
- Busca é por TF-IDF (estatística de palavras), não embeddings — não
  encontra sinônimos.
- SQLite local não é multiusuário nem persistente em serverless — ok para
  uso pessoal, não para produção com vários usuários simultâneos.

## Próximos passos possíveis

- Embeddings locais para busca semântica de verdade.
- Normalizar URLs de vídeo antes de checar duplicado.
- Editar a transcrição completa de uma nota direto na UI.
- Importar vários vídeos de uma vez (lote).

Se quiser que eu implemente algum desses, é só pedir.
