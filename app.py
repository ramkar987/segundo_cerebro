"""
Streamlit App - Segundo Cérebro + Transcriber
"""

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
    st.markdown("**Transcreva vídeos, gere resumos com Groq AI, extraia tags, traduzir e pesquisar**")
    
    with st.sidebar:
        st.header("⚙️ Configuraçª¢ons")
        groq_api_key = st.text_input("Groq API Key", type="password", 
                                     help="Obter: https://console.groq.com")
        translate_to = st.selectbox("Traduzir para (opcional)", 
                                    options=["", "en", "es", "fr"], index=0)
        db_path = st.text_input("Path DuckDB", value="./data/segundo_cerebro.duckdb")
        
        if st.button("🗄️ Inicializar Database"):
            try:
                storage = SegundoCerebroStorage(db_path=db_path)
                storage.initialize_schema()
                storage.close()
                st.success("Database inicializada!")
            except Exception as e:
                st.error(f"Erro: {e}")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📹 Upload de Vídeo")
        uploaded_file = st.file_uploader("Selecione um vídeo", 
                                         type=["mp4", "avi", "mov", "mkv"])
        
        processar_btn = st.button("🚀 Transcrever e Processar", 
                                  disabled=uploaded_file is None, type="primary")
        
        if processar_btn and uploaded_file:
            if not groq_api_key:
                st.error("Groq API Key obrigató¦´´ria!")
                return
            
            try:
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                    tmp.write(uploaded_file.read())
                    video_path = Path(tmp.name)
                
                st.info("📝 Transcrevendo vídeo...")
                transcriber = VideoTranscriber()
                trans_result = transcriber.transcribe_video(video_path, language="pt")
                transcription = trans_result["text"]
                st.success(f"✓ Transcripçª£o: {len(transcription)} caracteres")
                
                st.info("🤖 Processando com Groq AI...")
                groq = GroqAI(api_key=groq_api_key)
                translate_lang = translate_to if translate_to else None
                ia_result = groq.process_transcription(transcription, translate_to=translate_lang)
                st.success("✓ Processamento IA completo!")
                
                video_path.unlink()
                
                with st.expander("📊 Resultados"):
                    st.subheader("💡 Resumo")
                    st.info(ia_result["resumo"])
                    st.subheader("🏷️ Tags")
                    st.write(ia_result["tags"])
                    if ia_result["traducao"]:
                        st.subheader("🌐 Traduçª£o")
                        st.write(ia_result["traducao"][:300])
                
                if st.button("💾 Salvar no Segundo Cérebro"):
                    storage = SegundoCerebroStorage(db_path=db_path)
                    video_id = storage.insert_video(
                        titulo=uploaded_file.name,
                        caminho=uploaded_file.name,
                        transricao=ia_result["transricao"],
                        resumo=ia_result["resumo"],
                        tags=ia_result["tags"],
                        traducao=ia_result["traducao"]
                    )
                    storage.close()
                    st.success(f"✓ Salvo com ID: {video_id}")
                    
            except Exception as e:
                st.error(f"Erro: {e}")
                logger.error(f"Erro: {e}", exc_info=True)
    
    with col2:
        st.header("🔍 Pesquisa")
        search_text = st.text_input("Buscar...", placeholder="Ex: machine learning")
        
        if search_text:
            try:
                storage = SegundoCerebroStorage(db_path=db_path)
                resultados = storage.search_videos(search_text)
                storage.close()
                
                st.subheader(f"Encontrados {len(resultados)} vídeos")
                for video in resultados:
                    with st.expander(f"📹 {video['titulo']}"):
                        st.write(video['resumo'][:200] if video['resumo'] else "N/A")
                        st.write(f"🏷️ {video['tags']}")
            except Exception as e:
                st.error(f"Erro: {e}")
    
    st.divider()
    st.header("📚 Todos Ví­deos")
    try:
        storage = SegundoCerebroStorage(db_path=db_path)
        todos = storage.get_all_videos()
        storage.close()
        
        if todos:
            for video in todos:
                st.write(f"📹 {video['titulo']} - {video['tags']}")
        else:
            st.info("N™o há vídeos. Transcreva um para começar!")
    except:
        st.info("Database n™o inicializada.")

if __name__ == "__main__":
    main()
EOFAPP
