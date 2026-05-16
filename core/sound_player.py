"""
Sound Player for WikiDeck

Audio playback management via Pygame
"""

import pygame
from pathlib import Path
from typing import Optional

class SoundPlayer:
    """Manages game audio playback."""
    
    AUDIO_DIR = Path(__file__).parent.parent / "assets" / "audio"
    
    # Sound category paths
    SOUND_PATHS = {
        "music": AUDIO_DIR / "music",
        "sfx": AUDIO_DIR / "sfx",
        "voice": AUDIO_DIR / "voice",
    }
    
    def __init__(self):
        """Initialize sound player."""
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._ensure_directories_exist()
        
        # Initialize mixer if not already initialized
        if not pygame.mixer.get_init():
            pygame.mixer.init()
    
    @staticmethod
    def _ensure_directories_exist():
        """Ensure required directories exist."""
        for path in SoundPlayer.SOUND_PATHS.values():
            path.mkdir(parents=True, exist_ok=True)
    
    def play_sfx(self, filename: str) -> None:
        """
        Play a sound effect.
        
        Args:
            filename: Filename in sfx folder (e.g., "click.wav")
        """
        self._play_sound("sfx", filename)
    
    def play_music(self, filename: str, loops: int = -1) -> None:
        """
        Play background music.
        
        Args:
            filename: Filename in music folder
            loops: Number of loops (-1 = infinite)
        """
        try:
            path = self.SOUND_PATHS["music"] / filename
            if path.exists():
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play(loops)
        except pygame.error as e:
            print(f"❌ Error loading music {filename}: {e}")
    
    def stop_music(self) -> None:
        """Stop background music."""
        pygame.mixer.music.stop()
    
    def _play_sound(self, category: str, filename: str) -> None:
        """
        Internal method for sound playback.
        
        Args:
            category: Sound category (sfx, voice, etc.)
            filename: Filename
        """
        if category not in self.SOUND_PATHS:
            print(f"❌ Unknown category: {category}")
            return
        
        try:
            # Use cache for loaded sounds
            cache_key = f"{category}_{filename}"
            
            if cache_key not in self._sounds:
                path = self.SOUND_PATHS[category] / filename
                if not path.exists():
                    print(f"❌ File not found: {path}")
                    return
                
                self._sounds[cache_key] = pygame.mixer.Sound(str(path))
            
            # Play sound on first available channel
            self._sounds[cache_key].play()
            
        except pygame.error as e:
            print(f"❌ Error playing {category}/{filename}: {e}")
    
    def set_volume(self, category: str, volume: float) -> None:
        """
        Set volume for a category.
        
        Args:
            category: Category (sfx, music, voice)
            volume: Volume from 0.0 to 1.0
        """
        volume = max(0.0, min(1.0, volume))
        
        if category == "music":
            pygame.mixer.music.set_volume(volume)
        elif category == "sfx":
            # Set volume for all sfx channels
            for key, sound in self._sounds.items():
                if key.startswith("sfx_"):
                    sound.set_volume(volume)
    
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
        if category not in self.SOUND_PATHS:
            return []
        
        path = self.SOUND_PATHS[category]
        if not path.exists():
            return []
        
        supported = {".mp3", ".wav", ".flac", ".ogg"}
        files = [f for f in path.iterdir() if f.suffix.lower() in supported]
        return sorted(files)


# Global sound player instance
_sound_player: Optional[SoundPlayer] = None


def get_sound_player() -> SoundPlayer:
    """Get or create global sound player instance."""
    global _sound_player
    if _sound_player is None:
        _sound_player = SoundPlayer()
    return _sound_player


def play_click() -> None:
    """Quick way to play a click sound."""
    get_sound_player().play_sfx("click.wav")
