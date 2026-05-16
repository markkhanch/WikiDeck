# Audio Resources

Folder structure for music and sound effects.

## Structure

```
assets/audio/
├── music/       # Background music (BGM)
├── sfx/         # Sound effects (SFX)
└── voice/       # Voice lines
```

## Recommended Formats

### Optimal formats by type

| Type | Format | Bitrate | Description |
|-----|--------|---------|---------|
| **Music** | MP3 | 192 kbps | Optimal quality/size balance |
| **SFX** | **WAV** | Lossless | ⭐ **Recommended** — precise quality and timing |
| **Voice** | MP3 | 128 kbps | Good balance for speech |

### Technical Specifications

**WAV (for SFX):**
- **Bit Depth**: 16-bit
- **Sample Rate**: 44.1 kHz or 48 kHz
- **Channels**: Mono
- **Size**: ~176 KB/sec (acceptable for short sounds)

**MP3 (for music and voice):**
- **Bit Depth**: Lossy (optimized)
- **Sample Rate**: 44.1 kHz
- **Channels**: Stereo (music), Mono (voice)

## Project Recommendation

```
🎵 Music      → MP3 (192 kbps)
🔊 SFX        → WAV (16-bit, 44.1 kHz) ⭐
🎤 Voice      → MP3 (128 kbps)
```

Examples:
```
assets/audio/music/main_theme.mp3
assets/audio/sfx/click.wav                    ← UI clicks
assets/audio/sfx/Taking playing card.mp3      ← Card draw
assets/audio/sfx/success.wav
assets/audio/sfx/error.wav
assets/audio/voice/intro.mp3
```

## Conversion Tools

```bash
# MP3 (requires ffmpeg)
ffmpeg -i input.wav -b:a 192k output.mp3

# WAV from MP3 (for SFX)
ffmpeg -i input.mp3 -ar 44100 -ac 1 output.wav

# WAV optimal parameters
ffmpeg -i input.mp3 -acodec pcm_s16le -ar 44100 -ac 1 output.wav
```
