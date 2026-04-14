import os
# Prevent Intel Mac openMP crash
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


import tempfile
import logging
import hashlib
from pathlib import Path
from pydub import AudioSegment
from audio_separator.separator import Separator



logger = logging.getLogger(__name__)

class AudioProcessor:
    """Handles stem separation of audio files with local caching."""

    MODEL_NAME = "htdemucs.yaml"
    CACHE_DIR = Path.home() / ".sonicscrub_cache"

    def __init__(self, input_path: str, output_dir: str | None = None):
        # Force the input path to be absolute
        self.input_path = Path(input_path).resolve()
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        self.file_hash = self._generate_file_hash()
        self.song_cache_dir = self.CACHE_DIR / self.file_hash
        self.song_cache_dir.mkdir(parents=True, exist_ok=True)

        if output_dir:
            self.output_dir = Path(output_dir).resolve()
        else:
            self.output_dir = self.song_cache_dir
            
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _generate_file_hash(self) -> str:
        hash_md5 = hashlib.md5()
        with open(self.input_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def separate(self, progress_callback=None) -> tuple[str, str]:
        # Define the exact absolute path for our final Instrumental file
        instrumental_path = self.output_dir / f"{self.input_path.stem}_Instrumental.wav"

        # 1. CACHE CHECK
        # Look for the vocals file that Demucs generates
        vocal_glob = list(self.output_dir.glob("*(Vocals)*.wav"))
        
        if vocal_glob and instrumental_path.exists():
            if progress_callback:
                progress_callback("Using cached stems found on disk...")
            logger.info("Cache hit! Vocals: %s | Instrumental: %s", vocal_glob[0], instrumental_path)
            # Return ABSOLUTE paths as strings
            return str(vocal_glob[0].resolve()), str(instrumental_path.resolve())

        # 2. RUN SEPARATION
        if progress_callback:
            progress_callback("Initialising audio separator...")

        separator = Separator(output_dir=str(self.output_dir), output_format="wav")
        separator.load_model(model_filename=self.MODEL_NAME)

        if progress_callback:
            progress_callback("Separating stems (this may take a few minutes)...")

        # separator.separate() returns relative filenames (e.g. "Song_(Vocals).wav")
        output_filenames = separator.separate(str(self.input_path))
        
        # Force them into absolute paths immediately
        full_paths = [self.output_dir / Path(f).name for f in output_filenames]
        
        # 3. IDENTIFY STEMS
        vocals_path = None
        other_stems = []

        for fpath in full_paths:
            if "vocal" in fpath.name.lower():
                vocals_path = fpath
            elif "instrumental" not in fpath.name.lower():
                other_stems.append(fpath)

        if vocals_path is None or not vocals_path.exists():
            raise FileNotFoundError(f"Could not locate Vocals stem in {self.output_dir}")

        # 4. BUILD THE INSTRUMENTAL
        if progress_callback:
            progress_callback("Merging non-vocal stems into Instrumental track...")
            
        combined = None
        for s in other_stems:
            if not s.exists():
                logger.warning(f"Expected stem missing: {s}")
                continue
                
            stem_audio = AudioSegment.from_file(str(s))
            if combined is None:
                combined = stem_audio
            else:
                combined = combined.overlay(stem_audio)

        if combined is None:
            raise RuntimeError("Failed to combine stems. No non-vocal audio found.")

        # Export the combined file so it's ready for the Cache next time
        combined.export(str(instrumental_path), format="wav")
        logger.info("Successfully merged instrumental to: %s", instrumental_path)

        if progress_callback:
            progress_callback("Stem separation complete!")

        # Guarantee absolute paths are returned to the Lyric Coordinator
        return str(vocals_path.resolve()), str(instrumental_path.resolve())