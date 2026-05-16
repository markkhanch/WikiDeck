"""
Audio Manager for WikiDeck

Recommended formats:
- Music: MP3 (192 kbps)
- SFX: WAV (16-bit, 44.1 kHz, Mono) ⭐
- Voice: MP3 (128 kbps)
"""

import os
from pathlib import Path
from typing import Optional, Dict

class AudioManager:
    """Manages audio resources."""
    
    AUDIO_DIR = Path(__file__).parent.parent / "assets" / "audio"
    
    PATHS = {
        "music": AUDIO_DIR / "music",  # MP3 (192 kbps)
        "sfx": AUDIO_DIR / "sfx",      # WAV (16-bit, 44.1 kHz)
        "voice": AUDIO_DIR / "voice",  # MP3 (128 kbps)
    }
    
    # Supported audio formats
    SUPPORTED_FORMATS = {".mp3", ".wav", ".flac", ".ogg"}
    
    def __init__(self):
        """Initialize audio manager."""
        self._ensure_directories_exist()
        self._audio_cache: Dict[str, any] = {}
    
    @staticmethod
    def _ensure_directories_exist():
        """Ensure required directories exist."""
        for path in AudioManager.PATHS.values():
            path.mkdir(parents=True, exist_ok=True)
    
    def get_music_files(self) -> list:
        """Get all music files."""
        return self._get_files_from_directory("music")
    
    def get_sfx_files(self) -> list:
        """Get all SFX files."""
        return self._get_files_from_directory("sfx")
    
    def get_voice_files(self) -> list:
        """Get all voice files."""
        return self._get_files_from_directory("voice")
    
    def _get_files_from_directory(self, category: str) -> list:
        """Get all audio files from category."""
        if category not in self.PATHS:
            raise ValueError(f"Unknown category: {category}")
        
        path = self.PATHS[category]
        if not path.exists():
            return []
        
        files = [
            f for f in path.iterdir()
            if f.suffix.lower() in self.SUPPORTED_FORMATS
        ]
        return sorted(files)
    
    def get_file_path(self, category: str, filename: str) -> Optional[Path]:
        """
        Get full path to audio file.
        
        Args:
            category: "music", "sfx", or "voice"
            filename: Filename with extension
        
        Returns:
            Path to file or None if not found
        """
        if category not in self.PATHS:
            raise ValueError(f"Unknown category: {category}")
        
        file_path = self.PATHS[category] / filename
        if file_path.exists() and file_path.suffix.lower() in self.SUPPORTED_FORMATS:
            return file_path
        return None
    
    def list_all_audio(self) -> Dict[str, list]:
        """Get all audio files by category."""
        return {
            "music": self.get_music_files(),
            "sfx": self.get_sfx_files(),
            "voice": self.get_voice_files(),
        }


# Example usage
if __name__ == "__main__":
    manager = AudioManager()
    
    print("Audio files:")
    for category, files in manager.list_all_audio().items():
        print(f"\n{category.upper()}:")
        for f in files:
            print(f"  - {f.name}")
