"""
Sound Player for WikiDeck

Audio playback management via Pygame. Reads volumes from settings_service so
the player and the settings UI stay in sync.
"""

import pygame
from pathlib import Path
from typing import Optional

# Constant used by main.py to control menu music in/out of battles.
MENU_MUSIC_FILE = "menu song.wav"


def _read_volumes() -> tuple[float, float, float]:
    """Return (master, music, sfx) volumes from settings; fall back to 1.0."""
    try:
        from data.settings_service import get_float
        master = float(get_float("audio.master_volume"))
        music = float(get_float("audio.music_volume"))
        sfx = float(get_float("audio.sfx_volume"))
    except Exception:
        return 1.0, 1.0, 1.0
    clamp = lambda v: max(0.0, min(1.0, v))
    return clamp(master), clamp(music), clamp(sfx)


def _read_menu_music_enabled() -> bool:
    try:
        from data.settings_service import get_bool
        return bool(get_bool("audio.menu_music_enabled"))
    except Exception:
        return True


class SoundPlayer:
    """Manages game audio playback."""

    AUDIO_DIR = Path(__file__).parent.parent / "assets" / "audio"

    SOUND_PATHS = {
        "music": AUDIO_DIR / "music",
        "sfx": AUDIO_DIR / "sfx",
        "voice": AUDIO_DIR / "voice",
    }

    def __init__(self):
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._current_music: Optional[str] = None
        self._ensure_directories_exist()
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
            except pygame.error as exc:
                print(f"[audio] mixer init failed: {exc}", flush=True)

    @staticmethod
    def _ensure_directories_exist():
        for path in SoundPlayer.SOUND_PATHS.values():
            path.mkdir(parents=True, exist_ok=True)

    # ---- SFX ----

    def play_sfx(self, filename: str) -> None:
        self._play_sound("sfx", filename)

    def _play_sound(self, category: str, filename: str) -> None:
        if category not in self.SOUND_PATHS:
            print(f"[audio] unknown category: {category}", flush=True)
            return
        try:
            cache_key = f"{category}_{filename}"
            if cache_key not in self._sounds:
                path = self.SOUND_PATHS[category] / filename
                if not path.exists():
                    print(f"[audio] file not found: {path}", flush=True)
                    return
                self._sounds[cache_key] = pygame.mixer.Sound(str(path))
                # Apply current volume on first load.
                if category == "sfx":
                    master, _, sfx_vol = _read_volumes()
                    self._sounds[cache_key].set_volume(master * sfx_vol)
            self._sounds[cache_key].play()
        except pygame.error as e:
            print(f"[audio] error playing {category}/{filename}: {e}", flush=True)

    # ---- Music ----

    def play_music(self, filename: str, loops: int = -1) -> None:
        try:
            path = self.SOUND_PATHS["music"] / filename
            if not path.exists():
                print(f"[audio] music file not found: {path}", flush=True)
                return
            pygame.mixer.music.load(str(path))
            master, music_vol, _ = _read_volumes()
            pygame.mixer.music.set_volume(master * music_vol)
            pygame.mixer.music.play(loops)
            self._current_music = filename
        except pygame.error as e:
            print(f"[audio] error loading music {filename}: {e}", flush=True)

    def stop_music(self) -> None:
        try:
            pygame.mixer.music.stop()
        except pygame.error:
            pass
        self._current_music = None

    def is_music_playing(self) -> bool:
        try:
            return bool(pygame.mixer.music.get_busy())
        except pygame.error:
            return False

    # ---- Menu music helpers ----

    def start_menu_music(self) -> None:
        """Start (or resume) the menu loop, unless user disabled it."""
        if not _read_menu_music_enabled():
            self.stop_music()
            return
        if self.is_music_playing() and self._current_music == MENU_MUSIC_FILE:
            return
        self.play_music(MENU_MUSIC_FILE, loops=-1)

    def stop_menu_music(self) -> None:
        self.stop_music()

    # ---- Volume control (live re-apply) ----

    def apply_volumes(self) -> None:
        """Re-read volumes from settings and apply to mixer + cached sounds."""
        master, music_vol, sfx_vol = _read_volumes()
        try:
            pygame.mixer.music.set_volume(master * music_vol)
        except pygame.error:
            pass
        for key, sound in self._sounds.items():
            if key.startswith("sfx_"):
                try:
                    sound.set_volume(master * sfx_vol)
                except pygame.error:
                    pass

    def set_volume(self, category: str, volume: float) -> None:
        """Legacy direct-set kept for compatibility. Prefer apply_volumes()."""
        volume = max(0.0, min(1.0, volume))
        if category == "music":
            try:
                pygame.mixer.music.set_volume(volume)
            except pygame.error:
                pass
        elif category == "sfx":
            for key, sound in self._sounds.items():
                if key.startswith("sfx_"):
                    sound.set_volume(volume)

    # ---- Asset discovery (unchanged API) ----

    def get_music_files(self) -> list:
        return self._get_files_from_directory("music")

    def get_sfx_files(self) -> list:
        return self._get_files_from_directory("sfx")

    def get_voice_files(self) -> list:
        return self._get_files_from_directory("voice")

    def _get_files_from_directory(self, category: str) -> list:
        if category not in self.SOUND_PATHS:
            return []
        path = self.SOUND_PATHS[category]
        if not path.exists():
            return []
        supported = {".mp3", ".wav", ".flac", ".ogg"}
        return sorted(f for f in path.iterdir() if f.suffix.lower() in supported)


# Global instance.
_sound_player: Optional[SoundPlayer] = None


def get_sound_player() -> SoundPlayer:
    global _sound_player
    if _sound_player is None:
        _sound_player = SoundPlayer()
    return _sound_player


def play_click() -> None:
    get_sound_player().play_sfx("click.wav")


# Convenience module-level helpers used by main.py and settings UI.

def start_menu_music() -> None:
    get_sound_player().start_menu_music()


def stop_menu_music() -> None:
    get_sound_player().stop_menu_music()


def apply_audio_settings() -> None:
    """Re-apply all volume settings. Call after any audio.* setting changes.

    Also toggles menu music if `audio.menu_music_enabled` changed: starts it
    if currently silent and enabled, stops it if disabled.
    """
    player = get_sound_player()
    player.apply_volumes()
    if _read_menu_music_enabled():
        if not player.is_music_playing():
            player.start_menu_music()
    else:
        player.stop_music()
