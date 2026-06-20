from pathlib import Path
from typing import Dict, Optional
import subprocess

class VideoTranscriber:
    def __init__(self, model_name: str = "base", device: str = "cpu"):
        self.model_name = model_name
        self.device = device

    def extract_audio(self, video_path: Path, output_path: Optional[Path] = None) -> Path:
        if output_path is None:
            output_path = video_path.with_suffix(".wav")
        cmd = ["ffmpeg", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-y", str(output_path)]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def transcribe_video(self, video_path: Path, language: str = "pt") -> Dict:
        video_path = Path(video_path)
        audio_path = self.extract_audio(video_path)
        result = {"text": "", "language": language, "video_name": video_path.name, "video_path": str(video_path)}
        if audio_path.exists():
            audio_path.unlink()
        return result
