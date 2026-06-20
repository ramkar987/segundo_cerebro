import streamlit as st
import logging

from src.groq_ai import GroqAI
from src.storage import SegundoCerebroStorage

logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="Segundo Cérebro + Transcriber", page_icon="🧠", layout="wide")

def main():
    st.title("🧠 Segundo Cérebro + Transcriber")
    st.write("Cole a transcrição aqui e use Groq para resumo, tags, tradução e busca.")

    with st.sidebar:
        groq_api_key = st.text_input("Groq API Key", type="password")
        db_path = st.text_input("Path DuckDB", value="./data/segundo_cerebro.duckdb")
        translate_to = st.selectbox("Traduzir para", ["", "en", "es", "fr"], index=0)

        if st.button("Inicializar Database"):
            storage = SegundoCerebroStorage(db_path=db_path)
            storage.initialize_schema()
            storage.close()
            st.success("Database inicializada")

    transcription = st.text_area("Transcrição", height=300)
    titulo = st.text_input("Título", value="Texto transcrito")

    if st.button("Processar") and transcription and groq_api_key:
        groq = GroqAI(api_key=groq_api_key)
        result = groq.process_transcription(transcription, translate_to=translate_to or None)

        st.session_state["result"] = result
        st.subheader("Resumo")
        st.write(result["resumo"])
        st.subheader("Tags")
        st.write(result["tags"])
        if result["traducao"]:
            st.subheader("Tradução")
            st.write(result["traducao"])

        storage = SegundoCerebroStorage(db_path=db_path)
        video_id = storage.insert_video(
            titulo=titulo,
            caminho="transcricao_local",
            transricao=result["transricao"],
            resumo=result["resumo"],
            tags=result["tags"],
            traducao=result["traducao"],
            idioma_original=result["idioma_original"],
            idioma_traducao=result["idioma_traducao"],
        )
        storage.close()
        st.success(f"Salvo com ID {video_id}")

    search = st.text_input("Pesquisar")
    if search:
        storage = SegundoCerebroStorage(db_path=db_path)
        resultados = storage.search_videos(search)
        storage.close()
        st.write(f"{len(resultados)} resultado(s)")
        for item in resultados:
            with st.expander(item["titulo"]):
                st.write(item["resumo"] or "")
                st.write(item["tags"] or "")

if __name__ == "__main__":
    main()
