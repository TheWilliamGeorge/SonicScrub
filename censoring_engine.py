"""
SonicScrub — Censoring Engine.
Performs surgical muting of the original audio and patches in the
instrumental stem for censored regions, with micro-fades to prevent
audio pops/clicks.
"""

import logging
from pathlib import Path

from pydub import AudioSegment

from lyric_coordinator import WordTiming

logger = logging.getLogger(__name__)

# Duration of the micro-fade in milliseconds, applied at each cut point
# to prevent audio pops/clicks.
MICRO_FADE_MS = 2


class CensoringEngine:
    """
    Creates a clean version of a song by replacing flagged word regions
    in the original audio with the corresponding section of the
    instrumental stem.
    """

    def __init__(self, original_path: str, instrumental_path: str, padding_ms: int = 50):
        self.original_path = original_path
        self.instrumental_path = instrumental_path
        self.padding_ms = padding_ms

        # Load audio files
        self.original: AudioSegment = AudioSegment.from_file(original_path)
        raw_instrumental: AudioSegment = AudioSegment.from_file(instrumental_path)

        # FIX: Force instrumental to match original audio properties
        # This prevents silence caused by mismatched sample rates or channels
        self.instrumental = raw_instrumental.set_frame_rate(self.original.frame_rate) \
                                            .set_channels(self.original.channels) \
                                            .set_sample_width(self.original.sample_width)

        # Ensure instrumental is at least as long as original
        if len(self.instrumental) < len(self.original):
            silence_needed = len(self.original) - len(self.instrumental)
            self.instrumental += AudioSegment.silent(duration=silence_needed, 
                                                     frame_rate=self.original.frame_rate)

        self.result: AudioSegment | None = None

    def apply_censoring(
        self,
        flagged_words: list[WordTiming],
        progress_callback=None,
    ) -> AudioSegment:
        """
        Apply censoring to all flagged words.

        For each flagged word:
        - Calculates [start - padding] and [end + padding] in ms.
        - Replaces that region in the original with the instrumental.
        - Applies a 2ms micro-fade (crossfade) at each boundary.

        Args:
            flagged_words: List of WordTimings to censor.
            progress_callback: Optional callable(status_text: str).

        Returns:
            The censored AudioSegment.
        """
        if not flagged_words:
            logger.info("No words to censor.")
            self.result = self.original
            return self.result

        # Sort words by start time
        flagged_words = sorted(flagged_words, key=lambda w: w.start)

        # Merge overlapping/adjacent regions to avoid double-processing
        regions = self._merge_regions(flagged_words)

        if progress_callback:
            progress_callback(f"Censoring {len(regions)} region(s)...")

        result = self.original
        total = len(regions)

        for i, (start_ms, end_ms) in enumerate(regions):
            if progress_callback and i % 5 == 0:
                progress_callback(f"Censoring region {i + 1}/{total}...")

            result = self._patch_region(result, start_ms, end_ms)

        self.result = result

        if progress_callback:
            progress_callback("Censoring complete!")

        return self.result

    def _merge_regions(self, words: list[WordTiming]) -> list[tuple[int, int]]:
        """
        Convert word timings to (start_ms, end_ms) regions with padding,
        then merge overlapping or adjacent regions.
        """
        if not words:
            return []

        duration_ms = len(self.original)

        # Create padded regions
        raw_regions = []
        for w in words:
            start_ms = max(0, int(w.start * 1000) - self.padding_ms)
            end_ms = min(duration_ms, int(w.end * 1000) + self.padding_ms)
            if start_ms < end_ms:
                raw_regions.append((start_ms, end_ms))

        if not raw_regions:
            return []

        # Sort and merge
        raw_regions.sort()
        merged = [raw_regions[0]]
        for start, end in raw_regions[1:]:
            prev_start, prev_end = merged[-1]
            if start <= prev_end:
                # Overlapping or adjacent — extend
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))

        return merged

    def _patch_region(
        self, audio: AudioSegment, start_ms: int, end_ms: int
    ) -> AudioSegment:
        """
        Replace a region in the audio with the instrumental stem,
        applying micro-fades at the boundaries to prevent clicks.
        """
        fade = MICRO_FADE_MS
        duration_ms = len(audio)

        # Clamp boundaries
        start_ms = max(0, start_ms)
        end_ms = min(duration_ms, end_ms)
        region_len = end_ms - start_ms

        if region_len <= 0:
            return audio

        # Extract sections
        before = audio[:start_ms]
        after = audio[end_ms:]

        # Get the instrumental patch for this region
        inst_patch = self.instrumental[start_ms:end_ms]

        # Ensure instrumental patch is the right length
        if len(inst_patch) < region_len:
            inst_patch += AudioSegment.silent(duration=region_len - len(inst_patch))

        # Apply micro-fades to the original audio at boundaries
        # and to the instrumental patch
        if region_len > fade * 2:
            # Fade out the tail of 'before' and fade in the head of inst_patch
            if len(before) >= fade:
                before_tail = before[-fade:].fade_out(fade)
                before = before[:-fade] + before_tail

            # Fade in the instrumental at the start
            inst_patch = inst_patch.fade_in(fade)
            # Fade out the instrumental at the end
            inst_patch = inst_patch.fade_out(fade)

            # Fade in the head of 'after'
            if len(after) >= fade:
                after_head = after[:fade].fade_in(fade)
                after = after_head + after[fade:]

        # Reassemble
        return before + inst_patch + after

    def export(self, output_path: str, progress_callback=None) -> str:
        """
        Export the censored audio as MP3.

        Args:
            output_path: Path for the output file. If not ending in .mp3,
                         '.mp3' is appended.
            progress_callback: Optional callable(status_text: str).

        Returns:
            The output file path.
        """
        if self.result is None:
            raise RuntimeError("No censored audio to export. Call apply_censoring() first.")

        output_path = str(output_path)
        if not output_path.lower().endswith(".mp3"):
            output_path += ".mp3"

        if progress_callback:
            progress_callback("Exporting clean version as MP3...")

        self.result.export(output_path, format="mp3", bitrate="320k")

        if progress_callback:
            progress_callback(f"Exported: {Path(output_path).name}")

        logger.info("Exported clean audio to: %s", output_path)
        return output_path
