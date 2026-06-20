cat > src/transcriber.py << 'EOF'
"""Transcriber de vídeos (Whisper)"""
import subprocess
from pathlib import Path
from typing import Dict
import whisper
from config.settings import settings

class VideoTranscriber:
    def __init__(self):
        self.model = whisper.load_model(settings.transcriber_model, device=settings.transcriber_device)
    
    def transcribe_video(self, video_path: Path, language: str = "pt") -> Dict:
        audio_path = video_path.with_suffix(".wav")
        
        subprocess.run([
            "ffmpeg", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            "-y", str(audio_path)
        ], check=True, capture_output=True)
        
        result = self.model.transcribe(str(audio_path), language=language)
        audio_path.unlink()
        
        result["video_name"] = video_path.name
        return result
EOF
