"""
SonicScrub — Main CustomTkinter GUI.
A modern desktop interface for reviewing and censoring profanity in songs.
"""

import os
import threading
import logging
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from profanity_list import DEFAULT_PROFANITY
from audio_processor import AudioProcessor
from lyric_coordinator import LyricCoordinator, WordTiming
from censoring_engine import CensoringEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Theme configuration
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT = "#6C63FF"
ACCENT_HOVER = "#5A52E0"
BG_DARK = "#1A1A2E"
BG_CARD = "#16213E"
BG_SURFACE = "#0F3460"
TEXT_PRIMARY = "#E8E8E8"
TEXT_SECONDARY = "#A0A0B0"
TEXT_MUTED = "#6C6C80"
DANGER = "#E94560"
SUCCESS = "#2ECC71"


# ---------------------------------------------------------------------------
# Word row widget
# ---------------------------------------------------------------------------

class WordRow(ctk.CTkFrame):
    """A single row in the word review list."""

    def __init__(self, master, word_timing: WordTiming, is_profanity: bool, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.word_timing = word_timing

        self.grid_columnconfigure(1, weight=1)

        # Checkbox
        self.var = ctk.BooleanVar(value=is_profanity)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self.var,
            width=24,
            checkbox_width=20,
            checkbox_height=20,
            fg_color=DANGER if is_profanity else ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._on_toggle,
        )
        self.checkbox.grid(row=0, column=0, padx=(8, 4), pady=2)

        # Word label
        self.word_label = ctk.CTkLabel(
            self,
            text=word_timing.word,
            font=ctk.CTkFont(size=14, weight="bold" if is_profanity else "normal"),
            text_color=DANGER if is_profanity else TEXT_PRIMARY,
            anchor="w",
        )
        self.word_label.grid(row=0, column=1, padx=4, pady=2, sticky="w")

        # Timestamp label
        self.time_label = ctk.CTkLabel(
            self,
            text=f"{word_timing.start:.2f}s → {word_timing.end:.2f}s",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            anchor="e",
        )
        self.time_label.grid(row=0, column=2, padx=(4, 12), pady=2, sticky="e")

    def _on_toggle(self):
        """Update styling when checkbox is toggled."""
        checked = self.var.get()
        self.checkbox.configure(fg_color=DANGER if checked else ACCENT)
        self.word_label.configure(
            text_color=DANGER if checked else TEXT_PRIMARY,
            font=ctk.CTkFont(size=14, weight="bold" if checked else "normal"),
        )

    @property
    def is_checked(self) -> bool:
        return self.var.get()

    def set_checked(self, value: bool):
        self.var.set(value)
        self._on_toggle()


# ---------------------------------------------------------------------------
# Main app window
# ---------------------------------------------------------------------------

class SonicScrubApp(ctk.CTk):
    """Main SonicScrub application window."""

    def __init__(self):
        super().__init__()

        self.title("SonicScrub")
        self.geometry("800x900")
        self.minsize(650, 700)

        # State
        self._input_path: str | None = None
        self._vocals_path: str | None = None
        self._instrumental_path: str | None = None
        self._word_timings: list[WordTiming] = []
        self._word_rows: list[WordRow] = []
        self._processing = False

        self._build_ui()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        self.configure(fg_color=BG_DARK)

        # Main container
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ---- Header ----
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=70)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header,
            text="🎵  SonicScrub",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title_label.grid(row=0, column=0, padx=20, pady=(16, 2), sticky="w")

        subtitle_label = ctk.CTkLabel(
            header,
            text="Create clean versions of your music",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SECONDARY,
        )
        subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="w")

        # ---- File selection ----
        file_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12)
        file_frame.grid(row=1, column=0, padx=16, pady=(12, 6), sticky="ew")
        file_frame.grid_columnconfigure(1, weight=1)

        select_btn = ctk.CTkButton(
            file_frame,
            text="Select Audio File",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            corner_radius=8,
            height=36,
            command=self._on_select_file,
        )
        select_btn.grid(row=0, column=0, padx=12, pady=12)

        self._file_label = ctk.CTkLabel(
            file_frame,
            text="No file selected",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self._file_label.grid(row=0, column=1, padx=8, pady=12, sticky="w")

        # Metadata row
        meta_frame = ctk.CTkFrame(file_frame, fg_color="transparent")
        meta_frame.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew")
        meta_frame.grid_columnconfigure(1, weight=1)
        meta_frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            meta_frame, text="Track:", font=ctk.CTkFont(size=12),
            text_color=TEXT_SECONDARY,
        ).grid(row=0, column=0, padx=(0, 4))

        self._track_entry = ctk.CTkEntry(
            meta_frame, placeholder_text="Song name", height=30,
            font=ctk.CTkFont(size=12),
        )
        self._track_entry.grid(row=0, column=1, padx=(0, 12), sticky="ew")

        ctk.CTkLabel(
            meta_frame, text="Artist:", font=ctk.CTkFont(size=12),
            text_color=TEXT_SECONDARY,
        ).grid(row=0, column=2, padx=(0, 4))

        self._artist_entry = ctk.CTkEntry(
            meta_frame, placeholder_text="Artist name", height=30,
            font=ctk.CTkFont(size=12),
        )
        self._artist_entry.grid(row=0, column=3, sticky="ew")

        # ---- Progress section ----
        progress_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12)
        progress_frame.grid(row=2, column=0, padx=16, pady=6, sticky="ew")
        progress_frame.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            progress_frame,
            text="Ready — select an audio file to begin.",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self._status_label.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")

        self._progress_bar = ctk.CTkProgressBar(
            progress_frame, fg_color=BG_SURFACE, progress_color=ACCENT, height=6,
        )
        self._progress_bar.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="ew")
        self._progress_bar.set(0)

        # Process button
        self._process_btn = ctk.CTkButton(
            progress_frame,
            text="▶  Process Song",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            corner_radius=8,
            height=36,
            command=self._on_process,
            state="disabled",
        )
        self._process_btn.grid(row=0, column=1, rowspan=2, padx=12, pady=10)

        # ---- Word review panel ----
        review_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12)
        review_frame.grid(row=3, column=0, padx=16, pady=6, sticky="nsew")
        review_frame.grid_rowconfigure(1, weight=1)
        review_frame.grid_columnconfigure(0, weight=1)

        review_header = ctk.CTkFrame(review_frame, fg_color="transparent")
        review_header.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")
        review_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            review_header,
            text="Word Review",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self._word_count_label = ctk.CTkLabel(
            review_header,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            anchor="e",
        )
        self._word_count_label.grid(row=0, column=1, padx=4)

        self._scrollable = ctk.CTkScrollableFrame(
            review_frame,
            fg_color=BG_DARK,
            corner_radius=8,
            scrollbar_button_color=BG_SURFACE,
        )
        self._scrollable.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")
        self._scrollable.grid_columnconfigure(0, weight=1)

        # Placeholder text
        self._placeholder = ctk.CTkLabel(
            self._scrollable,
            text="Words will appear here after processing.\n\n"
                 "Check/uncheck any word to flag it for censoring.\n"
                 "Profanity from the default list is auto-flagged.",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_MUTED,
            justify="center",
        )
        self._placeholder.grid(row=0, column=0, pady=60)

        # ---- Controls bar ----
        controls_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12)
        controls_frame.grid(row=4, column=0, padx=16, pady=(6, 12), sticky="ew")
        controls_frame.grid_columnconfigure(2, weight=1)

        # Padding input
        pad_label = ctk.CTkLabel(
            controls_frame, text="Padding (ms):",
            font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY,
        )
        pad_label.grid(row=0, column=0, padx=(12, 4), pady=12)

        self._padding_entry = ctk.CTkEntry(
            controls_frame, width=70, height=30, font=ctk.CTkFont(size=12),
            justify="center",
        )
        self._padding_entry.insert(0, "50")
        self._padding_entry.grid(row=0, column=1, padx=(0, 12), pady=12)

        # Quick-action buttons
        btn_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=2, pady=12)

        self._select_all_btn = ctk.CTkButton(
            btn_frame, text="Select All Profanity",
            font=ctk.CTkFont(size=11), fg_color=BG_SURFACE,
            hover_color=ACCENT_HOVER, corner_radius=6, height=30, width=140,
            command=self._on_select_all_profanity, state="disabled",
        )
        self._select_all_btn.grid(row=0, column=0, padx=4)

        self._deselect_all_btn = ctk.CTkButton(
            btn_frame, text="Deselect All",
            font=ctk.CTkFont(size=11), fg_color=BG_SURFACE,
            hover_color=ACCENT_HOVER, corner_radius=6, height=30, width=100,
            command=self._on_deselect_all, state="disabled",
        )
        self._deselect_all_btn.grid(row=0, column=1, padx=4)

        # Export button
        self._export_btn = ctk.CTkButton(
            controls_frame,
            text="💾  Export Clean Version",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=SUCCESS,
            hover_color="#27AE60",
            corner_radius=8,
            height=40,
            width=200,
            command=self._on_export,
            state="disabled",
        )
        self._export_btn.grid(row=0, column=3, padx=12, pady=12)

    # -----------------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------------

    def _on_select_file(self):
        """Open a file dialog to select an audio file."""
        path = filedialog.askopenfilename(
            title="Select an audio file",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.flac *.m4a *.ogg"),
                ("MP3", "*.mp3"),
                ("WAV", "*.wav"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._input_path = path
            name = Path(path).name
            self._file_label.configure(text=name, text_color=TEXT_PRIMARY)
            self._process_btn.configure(state="normal")

            # Try to auto-fill track/artist from filename
            stem = Path(path).stem
            parts = stem.split(" - ", 1)
            if len(parts) == 2:
                self._artist_entry.delete(0, "end")
                self._artist_entry.insert(0, parts[0].strip())
                self._track_entry.delete(0, "end")
                self._track_entry.insert(0, parts[1].strip())

            self._set_status("File loaded. Click 'Process Song' to begin.", SUCCESS)

    def _on_process(self):
        """Start the full processing pipeline in a background thread."""
        if self._processing or not self._input_path:
            return

        self._processing = True
        self._process_btn.configure(state="disabled", text="⏳  Processing...")
        self._export_btn.configure(state="disabled")
        self._progress_bar.set(0)

        thread = threading.Thread(target=self._run_pipeline, daemon=True)
        thread.start()

    def _on_select_all_profanity(self):
        """Check all words that match the default profanity list."""
        for row in self._word_rows:
            word_lower = row.word_timing.word.lower().strip(".,!?;:'\"")
            if word_lower in DEFAULT_PROFANITY:
                row.set_checked(True)
        self._update_word_count()

    def _on_deselect_all(self):
        """Uncheck all words."""
        for row in self._word_rows:
            row.set_checked(False)
        self._update_word_count()

    def _on_export(self):
        """Export the clean version in a background thread."""
        if self._processing:
            return

        self._processing = True
        self._export_btn.configure(state="disabled", text="⏳  Exporting...")

        thread = threading.Thread(target=self._run_export, daemon=True)
        thread.start()

    # -----------------------------------------------------------------------
    # Pipeline (runs in background thread)
    # -----------------------------------------------------------------------

    def _run_pipeline(self):
        """Full processing pipeline: separate → align → populate review."""
        try:
            # Step 1: Stem separation
            self._update_status("Separating stems with Demucs HT...")
            self._update_progress(0.05)

            processor = AudioProcessor(self._input_path)
            vocals, instrumental = processor.separate(
                progress_callback=lambda msg: self._update_status(msg)
            )
            self._vocals_path = vocals
            self._instrumental_path = instrumental
            self._update_progress(0.4)

            # Step 2: Lyric alignment
            self._update_status("Aligning lyrics for word-level timestamps...")
            track = self._get_entry_text(self._track_entry)
            artist = self._get_entry_text(self._artist_entry)

            coordinator = LyricCoordinator(
                vocals_path=vocals,
                track_name=track,
                artist_name=artist,
            )
            self._word_timings = coordinator.get_word_timings(
                progress_callback=lambda msg: self._update_status(msg)
            )
            self._update_progress(0.85)

            # Step 3: Populate review panel
            self._update_status("Populating word review panel...")
            self.after(0, self._populate_word_list)
            self._update_progress(1.0)

            self._update_status(
                f"Done! {len(self._word_timings)} words found. "
                "Review and adjust, then export.",
            )

        except Exception as exc:
            logger.error("Pipeline error: %s", exc, exc_info=True)
            self._update_status(f"Error: {exc}")
        finally:
            self._processing = False
            self.after(0, lambda: self._process_btn.configure(
                state="normal", text="▶  Process Song"
            ))

    def _run_export(self):
        """Export pipeline (runs in background thread)."""
        try:
            # Gather flagged words
            flagged = [
                row.word_timing for row in self._word_rows if row.is_checked
            ]

            if not flagged:
                self._update_status("No words flagged for censoring. Nothing to export.")
                return

            # Get padding
            try:
                padding_ms = int(self._get_entry_text(self._padding_entry) or "50")
            except ValueError:
                padding_ms = 50

            self._update_status(f"Censoring {len(flagged)} word(s) with {padding_ms}ms padding...")
            self._update_progress(0.1)

            engine = CensoringEngine(
                original_path=self._input_path,
                instrumental_path=self._instrumental_path,
                padding_ms=padding_ms,
            )

            engine.apply_censoring(
                flagged, progress_callback=lambda msg: self._update_status(msg)
            )
            self._update_progress(0.7)

            # Build output path
            input_p = Path(self._input_path)
            output_name = f"{input_p.stem}_Clean.mp3"
            output_path = str(input_p.parent / output_name)

            engine.export(output_path, progress_callback=lambda msg: self._update_status(msg))
            self._update_progress(1.0)
            self._update_status(f"✅ Exported: {output_name}", color=SUCCESS)

        except Exception as exc:
            logger.error("Export error: %s", exc, exc_info=True)
            self._update_status(f"Error: {exc}")
        finally:
            self._processing = False
            self.after(0, lambda: self._export_btn.configure(
                state="normal", text="💾  Export Clean Version"
            ))

    # -----------------------------------------------------------------------
    # Word list management
    # -----------------------------------------------------------------------

    def _populate_word_list(self):
        """Clear and re-populate the scrollable word review list."""
        # Clear existing rows
        for row in self._word_rows:
            row.destroy()
        self._word_rows.clear()

        # Hide placeholder
        self._placeholder.grid_forget()

        for i, wt in enumerate(self._word_timings):
            word_lower = wt.word.lower().strip(".,!?;:'\"")
            is_prof = word_lower in DEFAULT_PROFANITY

            row = WordRow(self._scrollable, word_timing=wt, is_profanity=is_prof)
            row.grid(row=i, column=0, sticky="ew", pady=1)
            self._word_rows.append(row)

        # Enable controls
        self._export_btn.configure(state="normal")
        self._select_all_btn.configure(state="normal")
        self._deselect_all_btn.configure(state="normal")

        self._update_word_count()

    def _update_word_count(self):
        """Update the word count label."""
        total = len(self._word_rows)
        flagged = sum(1 for r in self._word_rows if r.is_checked)
        self._word_count_label.configure(
            text=f"{flagged} flagged / {total} total",
            text_color=DANGER if flagged > 0 else TEXT_MUTED,
        )

    # -----------------------------------------------------------------------
    # Helpers (thread-safe GUI updates)
    # -----------------------------------------------------------------------

    def _update_status(self, text: str, color: str = TEXT_SECONDARY):
        """Thread-safe status label update."""
        self.after(0, lambda: self._set_status(text, color))

    def _set_status(self, text: str, color: str = TEXT_SECONDARY):
        """Update status label (must be called from main thread)."""
        self._status_label.configure(text=text, text_color=color)

    def _update_progress(self, value: float):
        """Thread-safe progress bar update (0.0 to 1.0)."""
        self.after(0, lambda: self._progress_bar.set(min(1.0, max(0.0, value))))

    def _get_entry_text(self, entry: ctk.CTkEntry) -> str:
        """Thread-safe entry text retrieval."""
        # CTkEntry.get() is safe to call from threads in most cases,
        # but wrap defensively.
        try:
            return entry.get().strip()
        except Exception:
            return ""
