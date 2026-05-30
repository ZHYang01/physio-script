import multiprocessing
import queue
import sys
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QTextCursor
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
        self.setWindowTitle("Physio Script - Voice to Clinical Notes")
        self.setMinimumSize(1100, 750)

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

        self._build_ui()
        self._preload_whisper_model()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # ── Top Bar: Status + Record Button ──
        top_bar = QHBoxLayout()

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #555;")
        top_bar.addWidget(self.status_label)

        top_bar.addStretch()

        # Local transcription model status
        self.whisper_status = QLabel()
        self._set_whisper_status("loading")
        top_bar.addWidget(self.whisper_status)

        # Ollama status indicator (polled in the background)
        self.ollama_status = QLabel()
        self._update_ollama_status(False)
        top_bar.addWidget(self.ollama_status)

        self.ollama_status_worker = OllamaStatusWorker(self.ollama)
        self.ollama_status_worker.status_changed.connect(self._update_ollama_status)
        self.ollama_status_worker.start()

        # Record / Stop button
        self.record_btn = QPushButton("●  Start Recording")
        self.record_btn.setFixedSize(200, 44)
        self.record_btn.setStyleSheet(self._record_btn_style(False))
        self.record_btn.clicked.connect(self.toggle_recording)
        top_bar.addWidget(self.record_btn)

        main_layout.addLayout(top_bar)

        # ── Splitter: Transcript | SOAP Note ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Live Transcript
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Live Transcript"))

        self.transcript_edit = QPlainTextEdit()
        self.transcript_edit.setReadOnly(True)
        self.transcript_edit.setPlaceholderText(
            "Transcript will appear here as you speak...\n\n"
            "1. Click 'Start Recording' to begin\n"
            "2. Speak with your patient\n"
            "3. Click 'Stop Recording' when done\n"
            "4. Transcript will be transcribed automatically"
        )
        self.transcript_edit.setStyleSheet("font-size: 13px; line-height: 1.5;")
        left_layout.addWidget(self.transcript_edit)

        self.transcript_progress = QProgressBar()
        self.transcript_progress.setVisible(False)
        left_layout.addWidget(self.transcript_progress)

        splitter.addWidget(left_panel)

        # Right: SOAP Note
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("SOAP Note"))

        self.soap_edit = QPlainTextEdit()
        self.soap_edit.setReadOnly(True)
        self.soap_edit.setPlaceholderText(
            "SOAP note will appear here after transcription...\n\n"
            "Generated notes follow the format:\n"
            "S (Subjective) - Patient's complaints & history\n"
            "O (Objective) - Clinical findings & measurements\n"
            "A (Assessment) - Clinical reasoning & diagnosis\n"
            "P (Plan) - Treatment plan & exercises"
        )
        self.soap_edit.setStyleSheet("font-size: 13px; line-height: 1.5;")
        right_layout.addWidget(self.soap_edit)

        splitter.addWidget(right_panel)
        splitter.setSizes([500, 500])
        main_layout.addWidget(splitter)

        # ── Bottom Actions ──
        actions_layout = QHBoxLayout()

        # Generate SOAP button
        self.generate_btn = QPushButton("Generate SOAP Note")
        self.generate_btn.setEnabled(False)
        self.generate_btn.setFixedHeight(40)
        self.generate_btn.clicked.connect(self._generate_soap)
        actions_layout.addWidget(self.generate_btn)

        # Copy to clipboard
        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.setEnabled(False)
        self.copy_btn.setFixedHeight(40)
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        actions_layout.addWidget(self.copy_btn)

        actions_layout.addStretch()

        # Clear button
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setFixedHeight(40)
        self.clear_btn.clicked.connect(self._clear_all)
        actions_layout.addWidget(self.clear_btn)

        main_layout.addLayout(actions_layout)

        self._apply_stylesheet()

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
            # Don't hard-block: recording is still useful; chunks queue up and
            # transcribe once the model finishes loading.

        self.is_recording = True
        self.audio_chunks = []
        self.full_transcript = ""
        self._chunks_queued = 0
        self._chunks_transcribed = 0
        self.transcript_edit.clear()
        self.soap_edit.clear()
        self.generate_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)

        self.record_btn.setText("■  Stop Recording")
        self.record_btn.setStyleSheet(self._record_btn_style(True))
        self.status_label.setText("Recording...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #c0392b;")

        # Background transcription worker (one per recording session)
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

    def _stop_recording(self):
        self.is_recording = False
        if self.recording_thread:
            self.recording_thread.stop()
            self.recording_thread.wait(5000)

        self.record_btn.setText("●  Start Recording")
        self.record_btn.setStyleSheet(self._record_btn_style(False))
        self.status_label.setText("Processing transcription...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2980b9;")
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
        self.record_btn.setText("●  Start Recording")
        self.record_btn.setStyleSheet(self._record_btn_style(False))
        self.status_label.setText("Microphone error.")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #c0392b;")
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
        self.transcript_edit.setPlainText(self.full_transcript.strip())
        # Auto-scroll to bottom
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
            self.status_label.setText("Recording complete. Ready to generate SOAP note.")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #27ae60;"
            )
        elif self._chunks_queued == 0:
            # Mic opened but delivered no audio at all — almost always a
            # macOS microphone-permission issue for this app.
            self.status_label.setText("No audio captured — check microphone permission.")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #c0392b;"
            )
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
            self.status_label.setText("No speech detected. Try recording again.")
            self.status_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #c0392b;"
            )

    # ── SOAP Generation ──

    def _generate_soap(self):
        if not self.full_transcript.strip():
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
        self.status_label.setText("Generating SOAP note...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #8e44ad;")

        self.soap_thread = SummarizationThread(self.ollama, self.full_transcript.strip())
        self.soap_thread.note_ready.connect(self._on_soap_ready)
        self.soap_thread.error.connect(self._on_soap_error)
        self.soap_thread.start()

    def _on_soap_ready(self, note: str):
        self.soap_note = note
        self.soap_edit.setPlainText(note)
        self.copy_btn.setEnabled(True)
        self.generate_btn.setEnabled(True)
        self.status_label.setText("SOAP note generated successfully.")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #27ae60;")

    def _on_soap_error(self, msg: str):
        self.status_label.setText("Error generating SOAP note.")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #c0392b;")
        self.generate_btn.setEnabled(True)
        QMessageBox.warning(self, "Error", msg)

    # ── Clipboard ──

    def _copy_to_clipboard(self):
        if self.soap_note:
            success = self.clipboard.copy_soap_note(self.soap_note)
            if success:
                self.status_label.setText("SOAP note copied to clipboard!")
                self.status_label.setStyleSheet(
                    "font-size: 14px; font-weight: bold; color: #27ae60;"
                )





    # ── Clear ──

    def _stop_transcription_worker(self):
        """Stop and dispose of the background transcription worker, if any."""
        if self.transcription_worker:
            self.transcription_worker.stop()
            self.transcription_worker.wait(5000)
            self.transcription_worker = None

    def _clear_all(self):
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
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #555;")

    # ── Helpers ──

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
        styles = {
            "loading": ("Transcription: loading…", "#f39c12"),
            "ready": ("Transcription: local ✓", "#27ae60"),
            "error": ("Transcription: error", "#c0392b"),
        }
        text, color = styles.get(state, styles["loading"])
        self.whisper_status.setText(text)
        self.whisper_status.setStyleSheet(
            f"font-size: 12px; color: {color}; margin-right: 12px;"
        )

    @pyqtSlot(bool)
    def _update_ollama_status(self, available: bool):
        self._ollama_available = available
        if available:
            self.ollama_status.setText("Ollama: Connected")
            self.ollama_status.setStyleSheet(
                "font-size: 12px; color: #27ae60; margin-right: 10px;"
            )
        else:
            self.ollama_status.setText("Ollama: Disconnected")
            self.ollama_status.setStyleSheet(
                "font-size: 12px; color: #c0392b; margin-right: 10px;"
            )

    @staticmethod
    def _record_btn_style(recording: bool) -> str:
        if recording:
            return (
                "QPushButton { background-color: #c0392b; color: white; font-weight: bold; "
                "border-radius: 6px; font-size: 14px; }"
                "QPushButton:hover { background-color: #e74c3c; }"
            )
        return (
            "QPushButton { background-color: #27ae60; color: white; font-weight: bold; "
            "border-radius: 6px; font-size: 14px; }"
            "QPushButton:hover { background-color: #2ecc71; }"
        )

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f6fa; }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dcdde1;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
                background: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLabel { font-size: 13px; color: #2d3436; }
            QPlainTextEdit {
                border: 1px solid #dcdde1;
                border-radius: 6px;
                padding: 8px;
                background: white;
                color: #2d3436;
                selection-background-color: #74b9ff;
                selection-color: white;
            }
            QLineEdit, QComboBox { color: #2d3436; }
            QLineEdit {
                border: 1px solid #dcdde1;
                border-radius: 4px;
                padding: 6px;
                background: white;
            }
            QComboBox {
                border: 1px solid #dcdde1;
                border-radius: 4px;
                padding: 6px;
                background: white;
            }
            QPushButton {
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:disabled {
                background-color: #b2bec3;
                color: #dfe6e9;
            }
            QProgressBar {
                border: 1px solid #dcdde1;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #0984e3;
                border-radius: 3px;
            }
        """)

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
