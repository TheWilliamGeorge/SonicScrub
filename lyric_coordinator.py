"""
SonicScrub — Lyric & Alignment Coordinator.
Fixed version for macOS Intel (x86_64) stability.
"""

import re
import logging
import os
from dataclasses import dataclass

import requests

# Ensure we don't crash from duplicate OpenMP runtimes
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

logger = logging.getLogger(__name__)

@dataclass
class WordTiming:
    """A single word with its start/end timestamp in seconds."""
    word: str
    start: float
    end: float

# --- LRCLIB logic remains the same ---
LRCLIB_BASE = "https://lrclib.net/api"
USER_AGENT = "SonicScrub/1.0 (https://github.com/sonicscrub)"

def _fetch_lyrics(track_name: str, artist_name: str) -> dict | None:
    try:
        resp = requests.get(
            f"{LRCLIB_BASE}/search",
            params={"track_name": track_name, "artist_name": artist_name},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json()
        if results and isinstance(results, list) and len(results) > 0:
            return results[0]
    except Exception as exc:
        logger.warning("LRCLIB fetch failed: %s", exc)
    return None

def _parse_synced_lyrics_to_plain(synced_text: str) -> str:
    lines = []
    for line in synced_text.strip().splitlines():
        cleaned = re.sub(r"\[\d{2}:\d{2}\.\d{2,3}\]\s*", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)

# --- Updated stable-ts logic ---

def _extract_word_timings(result) -> list[WordTiming]:
    words = []
    for segment in result.segments:
        for word in segment.words:
            w_text = word.word.strip()
            if w_text and hasattr(word, "start") and hasattr(word, "end"):
                words.append(WordTiming(
                    word=w_text,
                    start=word.start,
                    end=word.end,
                ))
    return words

def _align_with_stable_ts(
    text: str, vocals_path: str, progress_callback=None
) -> list[WordTiming] | None:
    try:
        import stable_whisper
    except ImportError as exc:
        logger.warning("stable-ts not available: %s", exc)
        return None

    try:
        if progress_callback:
            progress_callback("Loading alignment model (float32 mode)...")

        # FIX: Forced compute_type="float32" to prevent SegFault on Intel Macs
        model = stable_whisper.load_faster_whisper("base", compute_type="float32")

        if progress_callback:
            progress_callback("Performing forced alignment with reference lyrics...")

        # FIX: Added language='en' to resolve the TypeError
        result = model.align(vocals_path, text, language='en')

        words = _extract_word_timings(result)
        return words if words else None

    except Exception as exc:
        logger.error("stable-ts alignment failed: %s", exc, exc_info=True)
        return None

def _transcribe_with_stable_ts(
    vocals_path: str, progress_callback=None
) -> list[WordTiming]:
    # Import inside to prevent early initialization crashes
    import stable_whisper
    import torch

    if progress_callback:
        progress_callback("Waking up AI engine (Compatibility Mode)...")

    # Set threads to 1 for maximum stability during the 'handshake'
    torch.set_num_threads(1)

    try:
        model = stable_whisper.load_faster_whisper(
            "tiny", 
            compute_type="default",  # 'default' is the safest for older Intel Macs
            device="cpu",
            cpu_threads=1,
            num_workers=1
        )

        if progress_callback:
            progress_callback("Transcribing...")

        result = model.transcribe(
            vocals_path,
            language="en",
            regroup=False,
            suppress_silence=True
        )
        
        words = _extract_word_timings(result)
        return words

    except Exception as e:
        logger.error(f"Transcription engine failed: {e}")
        return []

class LyricCoordinator:
    def __init__(self, vocals_path: str, track_name: str = "", artist_name: str = ""):
        self.vocals_path = vocals_path
        self.track_name = track_name
        self.artist_name = artist_name

    def get_word_timings(self, progress_callback=None) -> list[WordTiming]:
        reference_text = None

        if self.track_name and self.artist_name:
            if progress_callback:
                progress_callback(f"Searching LRCLIB for '{self.track_name}'...")

            lrc_data = _fetch_lyrics(self.track_name, self.artist_name)
            if lrc_data:
                synced = lrc_data.get("syncedLyrics")
                plain = lrc_data.get("plainLyrics")
                if synced:
                    reference_text = _parse_synced_lyrics_to_plain(synced)
                elif plain:
                    reference_text = plain

        if reference_text:
            word_timings = _align_with_stable_ts(
                text=reference_text,
                vocals_path=self.vocals_path,
                progress_callback=progress_callback,
            )
            if word_timings:
                return word_timings
            logger.info("Forced alignment failed. Falling back to transcription.")

        return _transcribe_with_stable_ts(
            self.vocals_path, progress_callback=progress_callback
        )