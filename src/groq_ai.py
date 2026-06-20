cat > src/groq_ai.py << 'EOF'
"""Groq AI processor"""
from typing import Optional, Dict, List
from groq import Groq
from config.settings import settings

class GroqAI:
    def __init__(self, api_key: Optional[str] = None):
        self.client = Groq(api_key=api_key or settings.groq_api_key)
        self.model = settings.groq_model
    
    def generate_summary(self, text: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": f"Resuma: {text}"}]
        )
        return response.messages[0].content.strip()
    
    def extract_tags(self, text: str) -> List[str]:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": f"Extraia tags: {text}"}]
        )
        tags = [t.strip().lower() for t in response.messages[0].content.split(",")]
        return [t for t in tags if t][:10]
    
    def translate(self, text: str, target_lang: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": f"Traduza para {target_lang}: {text}"}]
        )
        return response.messages[0].content.strip()
    
    def process_transcription(self, transcription: str, translate_to: Optional[str] = None) -> Dict:
        result = {
            "transricao": transcription,
            "resumo": self.generate_summary(transcription),
            "tags": ", ".join(self.extract_tags(transcription)),
            "traducao": self.translate(transcription, translate_to) if translate_to else None,
            "idioma_original": "pt",
            "idioma_traducao": translate_to
        }
        return result
EOF
