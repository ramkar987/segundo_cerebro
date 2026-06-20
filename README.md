cat > README.md << 'EOF'
# Segundo Cérebro + Transcriber (Streamlit + Groq)

Transcreva vídeos, gere resumos com Groq AI, extraia tags, traduzir e pesquisar.

## Instalação

```bash
pip install -r requirements.txt
cp .env.example .env
# Edite .env com GROQ_API_KEY
streamlit run app.py
```

## Obter Groq API

https://console.groq.com

## Usar

1. `streamlit run app.py`
2. Upload vídeo
3. Digite Groq API Key
4. Transcrever e Processar
5. Salvar no Segundo Cérebro
EOF
