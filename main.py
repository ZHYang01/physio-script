import multiprocessing
import os
import queue
import sys
import time
from pathlib import Path

# ── Qt platform plugin path (must be set before any Qt imports) ──
# In a frozen .app bundle the plugin is at Contents/Frameworks/PyQt6/...
def _setup_qt_plugins():
    if not getattr(sys, "frozen", False):
        return
    from pathlib import Path
    macos_dir = Path(sys.executable).parent
    contents_dir = macos_dir.parent
    candidates = [
        contents_dir / "Frameworks" / "PyQt6" / "Qt6" / "plugins",
        contents_dir / "Resources" / "PyQt6" / "Qt6" / "plugins",
        macos_dir / "PyQt6" / "Qt6" / "plugins",
    ]
    for p in candidates:
        if (p / "platforms" / "libqcocoa.dylib").exists():
            os.environ["QT_PLUGIN_PATH"] = str(p)
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(p / "platforms")
            return
_setup_qt_plugins()

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QKeySequence, QShortcut, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from audio.recorder import AudioRecorder
from clipboard.manager import ClipboardManager
from config.settings import Settings
from summarization.ollama import OllamaSummarizer
from transcription.whisper import WhisperTranscriber


# ── Theme System ───────────────────────────────────────────────────

class Theme:
    """Color palette and styling that switches between dark and light modes."""

    def __init__(self, dark: bool):
        if dark:
            self.bg = "#0d1117"
            self.card = "#161b22"
            self.border = "#30363d"
            self.text = "#e6edf3"
            self.text_muted = "#8b949e"
            self.accent = "#58a6ff"
            self.accent_hover = "#79c0ff"
            self.green = "#3fb950"
            self.red = "#f85149"
            self.amber = "#d2991d"
            self.record_btn = "#da3633"
            self.record_btn_text = "#ffffff"
            self.panel_header = "#e6edf3"
            self.btn_disabled_bg = "#21262d"
            self.btn_disabled_text = "#484f58"
            self.btn_bg = "#21262d"
            self.btn_text = "#c9d1d9"
            self.btn_hover_bg = "#30363d"
            self.btn_primary_bg = "#238636"
            self.btn_primary_hover = "#2ea043"
            self.btn_primary_text = "#ffffff"
            self.timer_color = "#8b949e"
            self.timer_recording_color = "#f85149"
            self.splitter_handle = "#30363d"
            self.scrollbar_bg = "#161b22"
            self.scrollbar_handle = "#30363d"
            self.selection_bg = "#264f78"
            self.chip_bg = "#161b22"
            self.chip_border = "#30363d"
            self.focus_border = "#58a6ff"
            self.count_color = "#6e7681"
        else:
            self.bg = "#f6f8fa"
            self.card = "#ffffff"
            self.border = "#d0d7de"
            self.text = "#1f2328"
            self.text_muted = "#656d76"
            self.accent = "#0969da"
            self.accent_hover = "#0550ae"
            self.green = "#1a7f37"
            self.red = "#cf222e"
            self.amber = "#9a6700"
            self.record_btn = "#cf222e"
            self.record_btn_text = "#ffffff"
            self.panel_header = "#1f2328"
            self.btn_disabled_bg = "#eaeef2"
            self.btn_disabled_text = "#8c959f"
            self.btn_bg = "#f6f8fa"
            self.btn_text = "#24292f"
            self.btn_hover_bg = "#eaeef2"
            self.btn_primary_bg = "#1f883d"
            self.btn_primary_hover = "#1a7f37"
            self.btn_primary_text = "#ffffff"
            self.timer_color = "#656d76"
            self.timer_recording_color = "#cf222e"
            self.splitter_handle = "#d0d7de"
            self.scrollbar_bg = "#f6f8fa"
            self.scrollbar_handle = "#d0d7de"
            self.selection_bg = "#c2dbff"
            self.chip_bg = "#ffffff"
            self.chip_border = "#d0d7de"
            self.focus_border = "#0969da"
            self.count_color = "#8c959f"

    @property
    def stylesheet(self) -> str:
        return f"""
            QMainWindow {{ background-color: {self.bg}; }}
            QLabel {{ color: {self.text}; }}
            QMenuBar {{
                background-color: {self.card};
                color: {self.text};
                border-bottom: 1px solid {self.border};
            }}
            QPlainTextEdit {{
                border: 1px solid {self.border};
                border-radius: 8px;
                padding: 12px;
                background-color: {self.card};
                color: {self.text};
                font-size: 14px;
                font-family: -apple-system, 'Helvetica Neue', sans-serif;
                line-height: 1.6;
                selection-background-color: {self.selection_bg};
            }}
            QPlainTextEdit:focus {{
                border: 1px solid {self.focus_border};
            }}
            QPlainTextEdit::placeholder {{
                color: {self.text_muted};
            }}
            QPushButton {{
                border: 1px solid {self.border};
                padding: 8px 20px;
                border-radius: 18px;
                font-size: 13px;
                font-weight: 600;
                background-color: {self.btn_bg};
                color: {self.btn_text};
            }}
            QPushButton:hover {{
                background-color: {self.btn_hover_bg};
            }}
            QPushButton:disabled {{
                background-color: {self.btn_disabled_bg};
                color: {self.btn_disabled_text};
                border-color: {self.btn_disabled_bg};
            }}
            QSplitter::handle {{
                background-color: {self.splitter_handle};
                width: 2px;
            }}
            QScrollBar:vertical {{
                background: {self.scrollbar_bg};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {self.scrollbar_handle};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """


def _detect_system_theme() -> bool:
    """Return True for dark mode, False for light mode."""
    try:
        import subprocess
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return True  # default dark


# ── Worker Threads ──────────────────────────────────────────────


class RecordingThread(QThread):
    """Handles continuous recording in chunks."""

    chunk_ready = pyqtSignal(Path)
    error = pyqtSignal(str)

    def __init__(self, recorder: AudioRecorder):
        super().__init__()
        self.recorder = recorder
        self._running = True

    def run(self):
        try:
            self.recorder.start_recording()
        except Exception as e:
            self.error.emit(str(e))
            return
        while self._running:
            time.sleep(Settings.CHUNK_DURATION_SECONDS)
            if self._running:
                chunk = self.recorder._save_chunk()
                if chunk:
                    self.chunk_ready.emit(chunk)
        # Final chunk
        chunk = self.recorder.stop_recording()
        if chunk:
            self.chunk_ready.emit(chunk)

    def stop(self):
        self._running = False


class TranscriptionWorker(QThread):
    """Transcribes audio chunks off the GUI thread, in arrival order.

    Chunks are pushed onto an internal queue and transcribed one at a time so
    the UI never blocks on a network round-trip and the transcript stays ordered.
    """

    text_ready = pyqtSignal(str)
    chunk_done = pyqtSignal()  # emitted after each chunk, success or not
    error = pyqtSignal(str)

    def __init__(self, transcriber: WhisperTranscriber):
        super().__init__()
        self.transcriber = transcriber
        self._queue: "queue.Queue[Path | None]" = queue.Queue()
        self._running = True

    def enqueue(self, chunk: Path):
        self._queue.put(chunk)

    def run(self):
        while self._running:
            try:
                chunk = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if chunk is None:  # sentinel to wake/stop
                break
            try:
                text = self.transcriber.transcribe_file(chunk)
                if text:
                    self.text_ready.emit(text)
            except Exception as e:  # never let the worker die on one bad chunk
                self.error.emit(str(e))
            finally:
                self.chunk_done.emit()

    def stop(self):
        self._running = False
        self._queue.put(None)


class OllamaStatusWorker(QThread):
    """Polls Ollama availability off the GUI thread so the check never blocks the UI."""

    status_changed = pyqtSignal(bool)

    def __init__(self, summarizer: OllamaSummarizer, interval_seconds: int = 8):
        super().__init__()
        self.summarizer = summarizer
        self.interval_seconds = interval_seconds
        self._running = True
        self._last = None

    def run(self):
        while self._running:
            available = self.summarizer.is_available()
            if available != self._last:
                self._last = available
                self.status_changed.emit(available)
            # Sleep in small slices so stop() is responsive
            for _ in range(self.interval_seconds * 4):
                if not self._running:
                    return
                self.msleep(250)

    def stop(self):
        self._running = False


class WhisperPreloadWorker(QThread):
    """Loads the local Whisper model off the GUI thread.

    The first launch downloads the model (~1.6 GB for large-v3-turbo); after
    that it's cached and load is fast. Reports ready/failed so the UI can tell
    the user whether transcription is available.
    """

    ready = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, transcriber: WhisperTranscriber):
        super().__init__()
        self.transcriber = transcriber

    def run(self):
        try:
            if self.transcriber.preload():
                self.ready.emit()
            else:
                self.failed.emit("Could not load the transcription model.")
        except Exception as e:
            self.failed.emit(str(e))


class SummarizationThread(QThread):
    """Generates SOAP note in the background."""

    note_ready = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, summarizer: OllamaSummarizer, transcript: str):
        super().__init__()
        self.summarizer = summarizer
        self.transcript = transcript

    def run(self):
        result = self.summarizer.generate_soap_note(self.transcript)
        if result:
            self.note_ready.emit(result)
        else:
            self.error.emit("Failed to generate SOAP note")


# ── Main Window ──────────────────────────────────────────────────


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Physio Script")
        self.setMinimumSize(1100, 700)

        # Theme
        self.theme = Theme(dark=_detect_system_theme())

        # Core components
        self.recorder = AudioRecorder(
            sample_rate=Settings.SAMPLE_RATE,
            channels=Settings.CHANNELS,
            chunk_duration=Settings.CHUNK_DURATION_SECONDS,
        )
        self.whisper = WhisperTranscriber(
            model_name=Settings.WHISPER_MODEL,
            device=Settings.WHISPER_DEVICE,
            compute_type=Settings.WHISPER_COMPUTE_TYPE,
        )
        self.ollama = OllamaSummarizer(
            base_url=Settings.OLLAMA_BASE_URL,
            model=Settings.OLLAMA_MODEL,
        )
        self.clipboard = ClipboardManager()

        # State
        self.is_recording = False
        self.recording_thread = None
        self.transcription_worker = None
        self.audio_chunks = []
        self.full_transcript = ""
        self.soap_note = ""
        self._chunks_queued = 0
        self._chunks_transcribed = 0
        self._ollama_available = False
        self._whisper_ready = False
        self.whisper_preload_worker = None
        self._recording_start_time = 0.0
        self._recording_timer = QTimer()
        self._recording_timer.timeout.connect(self._update_recording_time)

        self._build_ui()
        self._preload_whisper_model()

    def _build_ui(self):
        t = self.theme
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # ── Top Bar ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        # App title with subtle subtitle
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("Physio Script")
        title.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {t.text};")
        subtitle = QLabel("Voice → SOAP notes · fully on-device")
        subtitle.setStyleSheet(f"font-size: 11px; color: {t.text_muted};")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top_bar.addLayout(title_box)
        top_bar.addSpacing(16)

        # Status chips (dot + label inside a rounded pill)
        self.whisper_dot, self.whisper_status_label, whisper_chip = self._make_status_chip("Transcription")
        self.ollama_dot, self.ollama_status_label, ollama_chip = self._make_status_chip("Ollama")
        top_bar.addWidget(whisper_chip)
        top_bar.addWidget(ollama_chip)
        top_bar.addStretch()

        # Recording timer
        self.timer_label = QLabel("00:00")
        self.timer_label.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {t.timer_color}; "
            "font-family: 'SF Mono', Menlo, monospace;"
        )
        self.timer_label.setVisible(False)
        top_bar.addWidget(self.timer_label)

        # Record button (pill)
        self.record_btn = QPushButton("Start Recording")
        self.record_btn.setFixedSize(160, 40)
        self.record_btn.clicked.connect(self.toggle_recording)
        self._apply_record_btn_style(False)
        top_bar.addWidget(self.record_btn)

        main_layout.addLayout(top_bar)

        # Thin separator line
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {t.border};")
        main_layout.addWidget(sep)

        # ── Splitter: Transcript | SOAP Note ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 4, 0, 0)
        left_layout.setSpacing(6)

        trans_header_row = QHBoxLayout()
        trans_header = QLabel("Transcript")
        trans_header.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {t.panel_header};")
        self.transcript_count = QLabel("")
        self.transcript_count.setStyleSheet(f"font-size: 11px; color: {t.count_color};")
        trans_header_row.addWidget(trans_header)
        trans_header_row.addStretch()
        trans_header_row.addWidget(self.transcript_count)
        left_layout.addLayout(trans_header_row)

        self.transcript_edit = QPlainTextEdit()
        self.transcript_edit.setReadOnly(False)
        self.transcript_edit.textChanged.connect(self._on_transcript_edited)
        self.transcript_edit.setPlaceholderText(
            "Transcript will appear here as you speak...\n\n"
            "Start Recording → speak → Stop → transcript appears automatically.\n"
            "You can edit the text here before generating the SOAP note."
        )
        left_layout.addWidget(self.transcript_edit)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 4, 0, 0)
        right_layout.setSpacing(6)

        soap_header_row = QHBoxLayout()
        soap_header = QLabel("SOAP Note")
        soap_header.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {t.panel_header};")
        self.soap_count = QLabel("")
        self.soap_count.setStyleSheet(f"font-size: 11px; color: {t.count_color};")
        soap_header_row.addWidget(soap_header)
        soap_header_row.addStretch()
        soap_header_row.addWidget(self.soap_count)
        right_layout.addLayout(soap_header_row)

        self.soap_edit = QPlainTextEdit()
        self.soap_edit.textChanged.connect(self._on_soap_edited)
        self.soap_edit.setPlaceholderText(
            "SOAP note will appear here after generation...\n\n"
            "S (Subjective)\n"
            "O (Objective)\n"
            "A (Assessment)\n"
            "P (Plan)"
        )
        right_layout.addWidget(self.soap_edit)
        splitter.addWidget(right_panel)
        splitter.setSizes([500, 500])
        splitter.setHandleWidth(8)
        # Let the panels absorb all extra vertical space (no dead zone at bottom).
        main_layout.addWidget(splitter, stretch=1)

        # ── Bottom Actions ──
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.generate_btn = QPushButton("Generate SOAP Note")
        self.generate_btn.setEnabled(False)
        self.generate_btn.setFixedHeight(36)
        self.generate_btn.clicked.connect(self._generate_soap)
        self._style_primary_btn(self.generate_btn, False)

        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.setEnabled(False)
        self.copy_btn.setFixedHeight(36)
        self.copy_btn.clicked.connect(self._copy_to_clipboard)

        actions_layout.addWidget(self.generate_btn)
        actions_layout.addWidget(self.copy_btn)
        actions_layout.addStretch()

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setFixedHeight(36)
        self.clear_btn.clicked.connect(self._clear_all)
        # Subtle danger styling
        self.clear_btn.setStyleSheet(
            f"QPushButton {{ background-color: transparent; border: 1px solid {t.border}; "
            f"color: {t.text_muted}; border-radius: 18px; padding: 6px 16px; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {t.red}; border-color: {t.red}; }}"
        )
        actions_layout.addWidget(self.clear_btn)

        main_layout.addLayout(actions_layout)

        # ── Footer: status (left) + shortcut hints (right) ──
        footer_sep = QWidget()
        footer_sep.setFixedHeight(1)
        footer_sep.setStyleSheet(f"background-color: {t.border};")
        main_layout.addWidget(footer_sep)

        footer = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"font-size: 12px; color: {t.text_muted};")
        hints = QLabel("⌘R Record   ⌘↩ Generate   ⌘⇧C Copy")
        hints.setStyleSheet(f"font-size: 11px; color: {t.count_color};")
        footer.addWidget(self.status_label)
        footer.addStretch()
        footer.addWidget(hints)
        main_layout.addLayout(footer)

        self._apply_stylesheet()

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+R"), self, self.toggle_recording)
        QShortcut(QKeySequence("Ctrl+Return"), self, self._generate_soap)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, self._copy_to_clipboard)

        # Background status workers
        self.ollama_status_worker = OllamaStatusWorker(self.ollama)
        self.ollama_status_worker.status_changed.connect(self._update_ollama_status)
        self.ollama_status_worker.start()

        self._set_whisper_status("loading")
        self._update_ollama_status(False)

    # ── Recording ──

    @pyqtSlot()
    def toggle_recording(self):
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        if not self._whisper_ready:
            QMessageBox.information(
                self,
                "Transcription Model Loading",
                "The local transcription model is still loading.\n\n"
                "On first launch it downloads once (~1.6 GB); after that it's "
                "instant. You can start recording — transcription will begin as "
                "soon as the model is ready.",
            )

        self.is_recording = True
        self.audio_chunks = []
        self.full_transcript = ""
        self._chunks_queued = 0
        self._chunks_transcribed = 0
        self.transcript_edit.clear()
        self.soap_edit.clear()
        self.generate_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)

        self._apply_record_btn_style(True)
        self.timer_label.setText("00:00")
        self.timer_label.setVisible(True)
        self._recording_start_time = time.time()
        self._recording_timer.start(1000)

        # Pulsing dot
        self._pulse_dot_visible = True
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._pulse_recording_dot)
        self._pulse_timer.start(600)

        self._update_status("Recording", self.theme.red)

        # Background transcription worker
        self._stop_transcription_worker()
        self.transcription_worker = TranscriptionWorker(self.whisper)
        self.transcription_worker.text_ready.connect(self._on_text_ready)
        self.transcription_worker.chunk_done.connect(self._on_chunk_transcribed)
        self.transcription_worker.error.connect(self._on_transcription_error)
        self.transcription_worker.start()

        self.recording_thread = RecordingThread(self.recorder)
        self.recording_thread.chunk_ready.connect(self._on_chunk_ready)
        self.recording_thread.error.connect(self._on_recording_error)
        self.recording_thread.start()

    def _pulse_recording_dot(self):
        if not self.is_recording:
            return
        # Pulse a ● glyph in the button label between solid and dim for a
        # clear "live" indication.
        dot = "●" if self._pulse_dot_visible else "○"
        self.record_btn.setText(f"{dot}  Stop Recording")
        self._pulse_dot_visible = not self._pulse_dot_visible

    def _stop_recording(self):
        self.is_recording = False
        if self.recording_thread:
            self.recording_thread.stop()
            self.recording_thread.wait(5000)

        if hasattr(self, "_pulse_timer") and self._pulse_timer:
            self._pulse_timer.stop()

        self._apply_record_btn_style(False)
        self._recording_timer.stop()
        self.timer_label.setVisible(False)
        self._update_status("Processing transcription...", self.theme.accent)
        # If the mic captured nothing, no chunk signals will ever arrive, so
        # finalize here to surface the problem instead of hanging on "Processing".
        self._maybe_finish_transcription()

    @pyqtSlot(str)
    def _on_recording_error(self, msg: str):
        """A microphone/recording failure — reset the UI and tell the user."""
        self.is_recording = False
        if self.recording_thread:
            self.recording_thread.stop()
        self._stop_transcription_worker()
        self._apply_record_btn_style(False)
        self._update_status("Microphone error. " + msg, self.theme.red)
        QMessageBox.critical(self, "Microphone Error", msg)

    @pyqtSlot(Path)
    def _on_chunk_ready(self, chunk: Path):
        # Hand the chunk to the background worker; never transcribe on the GUI thread.
        self.audio_chunks.append(chunk)
        self._chunks_queued += 1
        if self.transcription_worker:
            self.transcription_worker.enqueue(chunk)

    @pyqtSlot(str)
    def _on_text_ready(self, text: str):
        self.full_transcript += " " + text
        # Only auto-update the display during active recording.
        # After stopping, the user may be editing, so don't overwrite.
        if self.is_recording:
            self.transcript_edit.setPlainText(self.full_transcript.strip())
            cursor = self.transcript_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.transcript_edit.setTextCursor(cursor)

    @pyqtSlot()
    def _on_chunk_transcribed(self):
        self._chunks_transcribed += 1
        self._maybe_finish_transcription()

    @pyqtSlot(str)
    def _on_transcription_error(self, msg: str):
        print(f"Transcription error: {msg}")

    def _maybe_finish_transcription(self):
        """When recording has stopped and every queued chunk is processed, finalize."""
        if self.is_recording:
            return
        if self._chunks_transcribed < self._chunks_queued:
            return
        if self.full_transcript.strip():
            self.generate_btn.setEnabled(True)
            self._style_primary_btn(self.generate_btn, False)
            self._update_status("Recording complete. Ready to generate SOAP note.", self.theme.green)
        elif self._chunks_queued == 0:
            # Mic opened but delivered no audio at all — almost always a
            # macOS microphone-permission issue for this app.
            self._update_status("No audio captured — check microphone permission.", self.theme.red)
            QMessageBox.warning(
                self,
                "No Audio Captured",
                "Recording produced no audio.\n\n"
                "Grant microphone access to Physio Script in:\n"
                "System Settings → Privacy & Security → Microphone\n"
                "then quit and relaunch the app.\n\n"
                "Also check System Settings → Sound → Input that the right "
                "microphone is selected and its level moves when you speak.",
            )
        else:
            self._update_status("No speech detected. Try recording again.", self.theme.red)

    # ── SOAP Generation ──

    def _generate_soap(self):
        transcript_text = self.transcript_edit.toPlainText().strip()
        if not transcript_text:
            return

        if not self._ollama_available:
            QMessageBox.warning(
                self,
                "Ollama Not Running",
                "Please start Ollama and ensure a model is available.\n\n"
                "Run: ollama pull llama3",
            )
            return

        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Generating...")
        self._style_primary_btn(self.generate_btn, True)
        self._update_status("Generating SOAP note...", self.theme.amber)

        self.soap_thread = SummarizationThread(self.ollama, transcript_text)
        self.soap_thread.note_ready.connect(self._on_soap_ready)
        self.soap_thread.error.connect(self._on_soap_error)
        self.soap_thread.start()

    def _on_soap_ready(self, note: str):
        self.soap_note = note
        self.soap_edit.setPlainText(note)
        self.copy_btn.setEnabled(True)
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("Generate SOAP Note")
        self._style_primary_btn(self.generate_btn, False)
        self._update_status("SOAP note generated successfully.", self.theme.green)





    # ── Clipboard ──

    def _copy_to_clipboard(self):
        soap_text = self.soap_edit.toPlainText().strip()
        if soap_text:
            self.clipboard.copy_soap_note(soap_text)
            self._update_status("SOAP note copied to clipboard!", self.theme.green)

    # ── SOAP Error ──

    def _on_soap_error(self, msg: str):
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("Generate SOAP Note")
        self._style_primary_btn(self.generate_btn, False)
        self._update_status("Error generating SOAP note.", self.theme.red)
        QMessageBox.warning(self, "Error", msg)

    # ── Clear ──

    def _stop_transcription_worker(self):
        """Stop and dispose of the background transcription worker, if any."""
        if self.transcription_worker:
            self.transcription_worker.stop()
            self.transcription_worker.wait(5000)
            self.transcription_worker = None

    def _clear_all(self):
        if self.full_transcript.strip() or self.soap_note.strip():
            reply = QMessageBox.question(
                self,
                "Clear All",
                "This will discard the current transcript and SOAP note. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if self.is_recording:
            self._stop_recording()
        self._stop_transcription_worker()
        self.transcript_edit.clear()
        self.soap_edit.clear()
        self.full_transcript = ""
        self.soap_note = ""
        self.audio_chunks = []
        self._chunks_queued = 0
        self._chunks_transcribed = 0
        self.generate_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.timer_label.setVisible(False)
        self._recording_timer.stop()
        self._update_status("Ready", self.theme.text_muted)

    # ── Helpers ──

    @staticmethod
    def _count_text(s: str) -> str:
        s = s.strip()
        if not s:
            return ""
        words = len(s.split())
        return f"{words} word{'s' if words != 1 else ''}"

    @pyqtSlot()
    def _on_transcript_edited(self):
        """Keep self.full_transcript in sync when the user edits the transcript box."""
        self.full_transcript = self.transcript_edit.toPlainText()
        self.transcript_count.setText(self._count_text(self.full_transcript))

    @pyqtSlot()
    def _on_soap_edited(self):
        """Keep self.soap_note in sync when the user edits the SOAP note box."""
        self.soap_note = self.soap_edit.toPlainText()
        self.soap_count.setText(self._count_text(self.soap_note))

    def _update_recording_time(self):
        """Update the recording timer label every second."""
        elapsed = int(time.time() - self._recording_start_time)
        self.timer_label.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        # Pulse between muted and red for visual feedback
        if elapsed % 2 == 0:
            self.timer_label.setStyleSheet(
                f"font-size: 20px; font-weight: 700; color: {self.theme.timer_recording_color}; "
                "font-family: 'SF Mono', Menlo, monospace;"
            )
        else:
            self.timer_label.setStyleSheet(
                f"font-size: 20px; font-weight: 700; color: {self.theme.timer_color}; "
                "font-family: 'SF Mono', Menlo, monospace;"
            )

    def _preload_whisper_model(self):
        """Kick off background loading of the local Whisper model."""
        self.whisper_preload_worker = WhisperPreloadWorker(self.whisper)
        self.whisper_preload_worker.ready.connect(self._on_whisper_ready)
        self.whisper_preload_worker.failed.connect(self._on_whisper_failed)
        self.whisper_preload_worker.start()

    @pyqtSlot()
    def _on_whisper_ready(self):
        self._whisper_ready = True
        self._set_whisper_status("ready")
        print(f"Transcription model ready (local: {self.whisper.model_name}).", flush=True)

    @pyqtSlot(str)
    def _on_whisper_failed(self, msg: str):
        self._whisper_ready = False
        self._set_whisper_status("error")
        print(f"Whisper preload failed: {msg}", flush=True)

    def _set_whisper_status(self, state: str):
        """state: 'loading' | 'ready' | 'error'"""
        t = self.theme
        dot_c = {"loading": t.amber, "ready": t.green, "error": t.red}.get(state, t.amber)
        label = {"loading": "Loading model…", "ready": "Local model", "error": "Model error"}
        self.whisper_dot.setStyleSheet(
            f"border-radius: 4px; border: none; background-color: {dot_c};"
        )
        self.whisper_status_label.setText(label.get(state, "Local model"))

    @pyqtSlot(bool)
    def _update_ollama_status(self, available: bool):
        self._ollama_available = available
        t = self.theme
        dot_c = t.green if available else t.red
        label_text = "Ollama" if available else "Ollama off"
        self.ollama_dot.setStyleSheet(
            f"border-radius: 4px; border: none; background-color: {dot_c};"
        )
        self.ollama_status_label.setText(label_text)

    def _update_status(self, text: str, color: str):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"font-size: 12px; color: {color};")

    def _make_status_chip(self, text: str):
        """Build a rounded status chip: [• label]. Returns (dot, label, chip)."""
        t = self.theme
        chip = QWidget()
        chip.setStyleSheet(
            f"background-color: {t.chip_bg}; border: 1px solid {t.chip_border}; "
            "border-radius: 11px;"
        )
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(10, 4, 12, 4)
        lay.setSpacing(6)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"border-radius: 4px; background-color: {t.text_muted};")
        label = QLabel(text)
        label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {t.text_muted}; border: none;")
        lay.addWidget(dot)
        lay.addWidget(label)
        return dot, label, chip

    def _apply_record_btn_style(self, recording: bool):
        t = self.theme
        if recording:
            self.record_btn.setText("Stop Recording")
            self.record_btn.setStyleSheet(
                f"QPushButton {{ background-color: {t.record_btn}; color: {t.record_btn_text}; "
                f"border-radius: 20px; font-size: 14px; font-weight: 600; border: none; }}"
                f"QPushButton:hover {{ background-color: {t.record_btn}; }}"
            )
        else:
            self.record_btn.setText("Start Recording")
            self.record_btn.setStyleSheet(
                f"QPushButton {{ background-color: {t.btn_primary_bg}; color: {t.btn_primary_text}; "
                f"border-radius: 20px; font-size: 14px; font-weight: 600; border: none; }}"
                f"QPushButton:hover {{ background-color: {t.btn_primary_hover}; }}"
            )

    def _style_primary_btn(self, btn: QPushButton, disabled: bool):
        t = self.theme
        if disabled:
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {t.btn_disabled_bg}; color: {t.btn_disabled_text}; "
                f"border-radius: 18px; font-size: 13px; font-weight: 600; border: 1px solid {t.border}; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {t.btn_primary_bg}; color: {t.btn_primary_text}; "
                f"border-radius: 18px; font-size: 13px; font-weight: 600; border: none; }}"
                f"QPushButton:hover {{ background-color: {t.btn_primary_hover}; }}"
            )

    def _apply_stylesheet(self):
        self.setStyleSheet(self.theme.stylesheet)

    def closeEvent(self, event):
        if self.recording_thread:
            self.recording_thread.stop()
            self.recording_thread.wait(5000)
        self._stop_transcription_worker()
        if self.ollama_status_worker:
            self.ollama_status_worker.stop()
            self.ollama_status_worker.wait(2000)
        if self.whisper_preload_worker and self.whisper_preload_worker.isRunning():
            self.whisper_preload_worker.wait(2000)
        self.recorder.cleanup()
        event.accept()


# ── Entry Point ──────────────────────────────────────────────────


def _selftest() -> int:
    """Headless smoke test for the bundled transcription stack.

    Triggered by setting PHYSIO_SELFTEST=1. Loads the local Whisper model and
    writes OK / FAIL to PHYSIO_SELFTEST_OUT (default /tmp/physio_selftest.txt),
    then exits. Lets us confirm the frozen .app can run transcription without
    needing the GUI.
    """
    import os
    import traceback

    out_path = os.environ.get("PHYSIO_SELFTEST_OUT", "/tmp/physio_selftest.txt")
    try:
        transcriber = WhisperTranscriber(
            model_name=Settings.WHISPER_MODEL,
            device=Settings.WHISPER_DEVICE,
            compute_type=Settings.WHISPER_COMPUTE_TYPE,
        )
        ok = transcriber.preload()
        msg = f"OK: model '{Settings.WHISPER_MODEL}' loaded\n" if ok else "FAIL: preload returned False\n"
        rc = 0 if ok else 1
    except Exception as e:
        msg = "FAIL: " + repr(e) + "\n" + traceback.format_exc()
        rc = 1
    with open(out_path, "w") as f:
        f.write(msg)
    return rc


def main():
    import os
    if os.environ.get("PHYSIO_SELFTEST"):
        sys.exit(_selftest())

    app = QApplication(sys.argv)
    app.setApplicationName("Physio Script")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    # Required for PyInstaller-frozen apps: without this, multiprocessing child
    # processes (spawned indirectly by the ML stack) re-bootstrap the whole app
    # and pile up as resource_tracker processes.
    multiprocessing.freeze_support()
    main()
