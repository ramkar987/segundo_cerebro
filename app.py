from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from ai import (
    MODELOS_DISPONIVEIS,
    AIServiceError,
    generate_tags,
    perguntar_as_notas,
    summarize_transcript,
    translate_transcript,
)
from db import (
    adicionar_nota,
    adicionar_nota_video,
    atualizar_nota,
    buscar_por_palavra_chave,
    excluir_nota,
    exportar_notas,
    importar_notas,
    init_db,
    listar_notas,
)
from downloader import (
    DownloadError,
    LongDurationVideoError,
    PrivateOrUnavailableVideoError,
    UnsupportedURLError,
    download_audio,
)
from limits import AudioLimits, file_size_mb, should_block_audio_size, should_warn_audio_size
from search import buscar_por_relevancia
from transcriber import TranscriptionError, transcribe_audio

st.set_page_config(page_title="Segundo Cérebro", page_icon="🧠", layout="wide")

init_db()

# ---------------------------------------------------------------------------
# Barra lateral: navegação + configuração opcional da IA
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🧠 Segundo Cérebro")
    pagina = st.radio(
        "Navegação",
        ["📝 Minhas notas", "🎥 Importar vídeo", "🔍 Buscar", "💬 Perguntar à IA"],
        label_visibility="collapsed",
    )

    st.divider()
    st.subheader("IA (opcional)")
    groq_key = st.text_input(
        "Chave da API Groq",
        type="password",
        help=(
            "Crie uma chave gratuita em console.groq.com. Se preferir, deixe em "
            "branco e configure GROQ_API_KEY em secrets.toml ou variável de ambiente."
        ),
    )
    modelo_label = st.selectbox("Modelo Groq", list(MODELOS_DISPONIVEIS.keys()))
    st.caption(
        "Notas e busca funcionam sem chave. Importar vídeo transcreve localmente "
        "(sem chave), mas o resumo e as tags usam IA."
    )

api_key = groq_key or None
modelo_groq = MODELOS_DISPONIVEIS[modelo_label]

# ---------------------------------------------------------------------------
# Página: Minhas notas (CRUD)
# ---------------------------------------------------------------------------
if pagina == "📝 Minhas notas":
    st.header("Minhas notas")

    with st.expander("➕ Nova nota"):
        with st.form("form_nova_nota", clear_on_submit=True):
            titulo = st.text_input("Título")
            conteudo = st.text_area("Conteúdo", height=150)
            tags = st.text_input("Tags (separadas por vírgula)")
            enviar = st.form_submit_button("Salvar nota")
            if enviar:
                if titulo.strip() and conteudo.strip():
                    adicionar_nota(titulo.strip(), conteudo.strip(), tags.strip())
                    st.success("Nota salva!")
                    st.rerun()
                else:
                    st.warning("Preencha pelo menos o título e o conteúdo.")

    with st.expander("💾 Backup (exportar / importar)"):
        st.caption(
            "No Streamlit Cloud, as notas podem ser perdidas quando o app reinicia "
            "(dorme por inatividade, novo deploy, reboot manual). Exporte um backup "
            "de vez em quando e importe de volta se isso acontecer."
        )

        col_exp, col_imp = st.columns(2)

        with col_exp:
            notas_atuais = listar_notas()
            if notas_atuais:
                st.download_button(
                    "📥 Exportar notas (.json)",
                    data=exportar_notas(),
                    file_name=f"segundo_cerebro_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                    mime="application/json",
                )
            else:
                st.caption("Nenhuma nota para exportar ainda.")

        with col_imp:
            arquivo_backup = st.file_uploader("📤 Importar backup (.json)", type="json", key="upload_backup")
            if arquivo_backup is not None and st.button("Confirmar importação"):
                try:
                    conteudo_backup = arquivo_backup.read().decode("utf-8")
                    importadas, ignoradas = importar_notas(conteudo_backup)
                    st.success(f"{importadas} nota(s) importada(s), {ignoradas} ignorada(s) (já existiam).")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao importar: {e}")

    notas = listar_notas()
    st.caption(f"{len(notas)} nota(s) salva(s)")

    for nota in notas:
        icone = "🎥" if nota.get("tipo") == "video" else "📝"
        rotulo = f"{icone} **{nota['titulo']}**  ·  {nota['tags'] or 'sem tags'}"
        with st.expander(rotulo):
            st.write(nota["conteudo"])
            st.caption(f"Atualizado em {nota['atualizado_em'][:16].replace('T', ' ')}")

            if nota.get("fonte_url"):
                st.markdown(f"🔗 [Vídeo original]({nota['fonte_url']})")

            if nota.get("transcricao_completa"):
                if st.checkbox("📄 Ver transcrição completa", key=f"ver_transcricao_{nota['id']}"):
                    st.text_area(
                        "Transcrição",
                        value=nota["transcricao_completa"],
                        height=250,
                        label_visibility="collapsed",
                        key=f"transcricao_{nota['id']}",
                    )

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🗑️ Excluir", key=f"del_{nota['id']}"):
                    excluir_nota(nota["id"])
                    st.rerun()
            with col2:
                editar = st.toggle("✏️ Editar", key=f"edit_toggle_{nota['id']}")

            if editar:
                novo_titulo = st.text_input("Título", value=nota["titulo"], key=f"titulo_{nota['id']}")
                novo_conteudo = st.text_area(
                    "Conteúdo", value=nota["conteudo"], key=f"conteudo_{nota['id']}", height=150
                )
                novas_tags = st.text_input("Tags", value=nota["tags"], key=f"tags_{nota['id']}")
                if st.button("Salvar alterações", key=f"save_{nota['id']}"):
                    atualizar_nota(nota["id"], novo_titulo.strip(), novo_conteudo.strip(), novas_tags.strip())
                    st.success("Atualizado!")
                    st.rerun()

# ---------------------------------------------------------------------------
# Página: Importar vídeo (baixa, transcreve local, resume/tageia com IA)
# ---------------------------------------------------------------------------
elif pagina == "🎥 Importar vídeo":
    st.header("Importar vídeo")
    st.caption(
        "Cole o link de um vídeo (YouTube, Instagram...). O áudio é baixado e "
        "transcrito localmente com Whisper; o resumo, as tags e a tradução usam a IA da Groq."
    )

    if not api_key:
        st.info(
            "Essa página precisa de uma chave da Groq (resumo e tags usam IA). "
            "Adicione na barra lateral, ou configure GROQ_API_KEY em secrets.toml / "
            "variável de ambiente."
        )

    url = st.text_input("URL do vídeo", placeholder="https://youtube.com/watch?v=...")

    col1, col2 = st.columns(2)
    with col1:
        whisper_model = st.selectbox("Modelo Whisper (transcrição)", ["base", "small", "medium"], index=0)
        idioma_audio = st.selectbox("Idioma do áudio", ["auto", "pt", "en", "es", "fr", "de", "it"], index=0)
    with col2:
        gerar_traducao = st.checkbox("Também gerar tradução")
        idioma_traducao = st.text_input("Traduzir para", value="inglês", disabled=not gerar_traducao)

    processar = st.button("▶️ Processar e salvar como nota", type="primary", disabled=not api_key)

    if processar:
        if not url.strip():
            st.error("Cole uma URL válida.")
        else:
            limits = AudioLimits()
            try:
                with st.status("Processando vídeo...", expanded=True) as status:
                    st.write("⬇️ Baixando áudio...")
                    with tempfile.TemporaryDirectory() as tmpdir:
                        audio_path, metadata = download_audio(url.strip(), Path(tmpdir) / "audio")

                        audio_mb = file_size_mb(audio_path)
                        if should_block_audio_size(audio_mb, limits):
                            st.error(f"Áudio muito grande ({audio_mb:.1f} MB). Limite: {limits.block_mb:.0f} MB.")
                            st.stop()
                        if should_warn_audio_size(audio_mb, limits):
                            st.warning(f"Áudio grande ({audio_mb:.1f} MB) — a transcrição pode demorar mais.")

                        st.write("🎙️ Transcrevendo com Whisper (local)...")
                        segments = transcribe_audio(
                            audio_path=audio_path,
                            model_name=whisper_model,
                            language=None if idioma_audio == "auto" else idioma_audio,
                        )
                        transcript_text = "\n".join(seg.text for seg in segments)

                        st.write("📝 Gerando resumo com IA...")
                        resumo = summarize_transcript(transcript_text, model=modelo_groq, api_key=api_key)

                        st.write("🏷️ Gerando tags com IA...")
                        tags = generate_tags(resumo, api_key=api_key)

                        traducao = ""
                        if gerar_traducao:
                            st.write(f"🌐 Traduzindo para {idioma_traducao}...")
                            traducao = translate_transcript(
                                transcript_text, idioma_traducao, model=modelo_groq, api_key=api_key
                            )

                        conteudo_nota = f"**Fonte:** {url.strip()}\n\n## Resumo\n{resumo}"
                        if traducao:
                            conteudo_nota += f"\n\n## Tradução ({idioma_traducao})\n{traducao}"

                        adicionar_nota_video(
                            titulo=metadata.title,
                            conteudo=conteudo_nota,
                            tags=", ".join(tags),
                            fonte_url=url.strip(),
                            transcricao_completa=transcript_text,
                        )

                        status.update(label="✅ Vídeo importado como nota!", state="complete", expanded=False)

                st.success(f'Nota "{metadata.title}" salva! Tags: {", ".join(tags)}')
                with st.expander("📄 Ver resumo gerado"):
                    st.markdown(resumo)

            except UnsupportedURLError as exc:
                st.error(f"🚫 URL inválida ou não suportada: {exc}")
            except PrivateOrUnavailableVideoError as exc:
                st.error(f"🔒 Vídeo privado ou indisponível: {exc}")
            except LongDurationVideoError as exc:
                st.warning(f"⏱️ Vídeo muito longo: {exc}")
            except DownloadError as exc:
                st.error(f"⬇️ Falha no download: {exc}")
            except TranscriptionError as exc:
                st.error(f"🎙️ Falha na transcrição: {exc}")
            except AIServiceError as exc:
                st.error(f"🤖 Falha na IA: {exc}")

# ---------------------------------------------------------------------------
# Página: Buscar (sem IA — funciona sempre)
# ---------------------------------------------------------------------------
elif pagina == "🔍 Buscar":
    st.header("Buscar nas suas notas")
    consulta = st.text_input("O que você está procurando?")

    if consulta:
        notas = listar_notas()
        resultados = buscar_por_relevancia(notas, consulta, top_k=10)

        if not resultados:
            st.info("Nenhum resultado por relevância — tentando busca por palavra-chave.")
            resultados = [dict(r, relevancia=None) for r in buscar_por_palavra_chave(consulta)]

        if not resultados:
            st.warning("Nenhuma nota encontrada.")
        else:
            for r in resultados:
                icone = "🎥" if r.get("tipo") == "video" else "📝"
                selo = f" · relevância {r['relevancia']:.2f}" if r.get("relevancia") else ""
                with st.expander(f"{icone} **{r['titulo']}**{selo}"):
                    st.write(r["conteudo"])
                    if r.get("fonte_url"):
                        st.markdown(f"🔗 [Vídeo original]({r['fonte_url']})")

# ---------------------------------------------------------------------------
# Página: Perguntar à IA (requer chave da Groq)
# ---------------------------------------------------------------------------
elif pagina == "💬 Perguntar à IA":
    st.header("Pergunte às suas notas")

    if not api_key:
        st.info(
            "Adicione sua chave da Groq na barra lateral (ou configure GROQ_API_KEY em "
            "secrets.toml / variável de ambiente) para usar essa funcionalidade. "
            "É grátis: crie a sua em https://console.groq.com"
        )
    else:
        pergunta = st.text_input(
            "O que você quer saber?",
            placeholder="Ex: o que o vídeo sobre produtividade falava sobre Pomodoro?",
        )
        if pergunta:
            notas = listar_notas()
            relevantes = buscar_por_relevancia(notas, pergunta, top_k=5)

            if not relevantes:
                st.warning("Não encontrei notas relacionadas a essa pergunta.")
            else:
                with st.spinner("Pensando..."):
                    try:
                        resposta = perguntar_as_notas(pergunta, relevantes, model=modelo_groq, api_key=api_key)
                        st.markdown(resposta)
                        with st.expander("📎 Notas usadas como contexto"):
                            for n in relevantes:
                                icone = "🎥" if n.get("tipo") == "video" else "📝"
                                st.markdown(f"- {icone} **{n['titulo']}**")
                    except AIServiceError as e:
                        st.error(f"Erro ao consultar a IA: {e}")
