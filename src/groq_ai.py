from typing import Optional, Dict, List
from groq import Groq

class GroqAI:
    def __init__(self, api_key: str, model: str = "llama-3.1-8b-instant"):
        self.client = Groq(api_key=api_key)
        self.model = model

    def _chat(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()

    def generate_summary(self, text: str) -> str:
        return self._chat(f"Resuma em português de forma objetiva:\n\n{text}")

    def extract_tags(self, text: str, max_tags: int = 10) -> List[str]:
        raw = self._chat(f"Extraia até {max_tags} tags curtas separadas por vírgula:\n\n{text}")
        tags = [t.strip().lower() for t in raw.split(",")]
        return [t for t in tags if t][:max_tags]

    def translate(self, text: str, target_lang: str) -> str:
        return self._chat(f"Traduza para {target_lang}:\n\n{text}")

    def process_transcription(self, transcription: str, translate_to: Optional[str] = None) -> Dict:
        resumo = self.generate_summary(transcription)
        tags = ", ".join(self.extract_tags(transcription))
        traducao = self.translate(transcription, translate_to) if translate_to else None
        return {
            "transricao": transcription,
            "resumo": resumo,
            "tags": tags,
            "traducao": traducao,
            "idioma_original": "pt",
            "idioma_traducao": translate_to,
        }
