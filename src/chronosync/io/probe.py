"""Lightweight media probing: metadata only, no audio decode."""

from __future__ import annotations

from pathlib import Path

from chronosync.models.audio import AudioTrack


def probe(path: str | Path) -> AudioTrack:
    """Read static metadata of an audio file without decoding it.

    Uses libsndfile via ``soundfile`` when installed (WAV / BWF / RF64 /
    FLAC / OGG / ...); falls back to the stdlib ``wave`` module for plain
    PCM WAV files. Raises ``FileNotFoundError`` for missing files and lets
    backend errors propagate for unreadable ones.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")

    try:
        import soundfile as sf
    except ImportError:  # pragma: no cover - exercised only without soundfile
        sf = None

    if sf is not None:
        info = sf.info(str(path))
        return AudioTrack(
            name=path.name,
            path=str(path),
            sample_rate=int(info.samplerate),
            channels=int(info.channels),
            frames=int(info.frames),
            duration_seconds=float(info.frames) / info.samplerate,
            format=str(info.format),
            subtype=str(info.subtype),
        )

    # Fallback: stdlib `wave` handles plain PCM WAV (16/24/32-bit int).
    import wave

    with wave.open(str(path), "rb") as wav:
        sample_rate = int(wav.getframerate())
        channels = int(wav.getnchannels())
        frames = int(wav.getnframes())
        return AudioTrack(
            name=path.name,
            path=str(path),
            sample_rate=sample_rate,
            channels=channels,
            frames=frames,
            duration_seconds=frames / sample_rate,
            format="WAV",
            subtype=f"PCM_{wav.getsampwidth() * 8}",
        )
