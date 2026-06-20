import streamlit as st
from pathlib import Path
import tempfile
import logging

from src.transcriber import VideoTranscriber
from src.groq_ai import GroqAI
from src.storage import SegundoCerebroStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Segundo Cérebro + Transcriber",
    page_icon="🧠",
    layout="wide"
)

def main():
    st.title("🧠 Segundo Cérebro + Transcriber")
    st.markdown("Transcreva vídeos localmente e use o app para resumo, tags, tradução, pesquisa e organização.")

    with st.sidebar:
        st.header("⚙️ Configurações")
        groq_api_key = st.text_input("Groq API Key", type="password", help="https://console.groq.com")
        translate_to = st.selectbox("Traduzir para", ["", "en", "es", "fr"], index=0)
        db_path = st.text_input("Path DuckDB", value="./data/segundo_cerebro.duckdb")

        if st.button("🗄️ Inicializar Database"):
            storage = SegundoCerebroStorage(db_path=db_path)
            storage.initialize_schema()
            storage.close()
            st.success("Database inicializada!")

    col1, col2 = st.columns(2)

    with col1:
        st.header("📝 Texto transcrito")
        transcription = st.text_area("Cole aqui a transcrição do vídeo", height=300)
        titulo = st.text_input("Título", placeholder="Ex: Curso de ML")
        salvar_apenas = st.checkbox("Salvar depois de processar", value=True)

        processar = st.button("🚀 Processar com Groq AI", type="primary", disabled=not transcription or not groq_api_key)

        if processar:
            groq = GroqAI(api_key=groq_api_key)
            ia_result = groq.process_transcription(transcription, translate_to=translate_to or None)

            st.session_state["ia_result"] = ia_result
            st.session_state["titulo"] = titulo

            st.success("Processamento concluído!")

            st.subheader("Resumo")
            st.write(ia_result["resumo"])

            st.subheader("Tags")
            st.write(ia_result["tags"])

            if ia_result["traducao"]:
                st.subheader("Tradução")
                st.write(ia_result["traducao"])

            if salvar_apenas:
                storage = SegundoCerebroStorage(db_path=db_path)
                video_id = storage.insert_video(
                    titulo=titulo or "Texto transcrito",
                    caminho="transcricao_local",
                    transricao=ia_result["transricao"],
                    resumo=ia_result["resumo"],
                    tags=ia_result["tags"],
                    traducao=ia_result["traducao"],
                    idioma_original=ia_result["idioma_original"],
                    idioma_traducao=ia_result["idioma_traducao"]
                )
                storage.close()
                st.success(f"Salvo no banco com ID {video_id}")

    with col2:
        st.header("🔍 Pesquisa")
        search_text = st.text_input("Buscar", placeholder="Ex: machine learning")

        if search_text:
            storage = SegundoCerebroStorage(db_path=db_path)
            resultados = storage.search_videos(search_text)
            storage.close()

            st.write(f"{len(resultados)} resultado(s)")
            for video in resultados:
                with st.expander(video["titulo"]):
                    st.write(video["resumo"] or "")
                    st.write(video["tags"] or "")

        st.divider()
        st.header("📚 Últimos itens")
        try:
            storage = SegundoCerebroStorage(db_path=db_path)
            videos = storage.get_all_videos()
            storage.close()

            for video in videos[:10]:
                st.write(f"• {video['titulo']} | {video['tags']}")
        except Exception:
            st.info("Inicialize o banco para ver os itens.")

if __name__ == "__main__":
    main()
