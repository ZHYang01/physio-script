import tempfile
import wave
from pathlib import Path
from typing import Optional

import pyaudio


class AudioRecorder:
    """Records audio from the microphone in chunks."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration: int = 5,
        chunk_callback=None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration = chunk_duration
        self.chunk_callback = chunk_callback

        self.audio = pyaudio.PyAudio()
        self.stream: Optional[pyaudio.Stream] = None
        self.is_recording = False
        self._buffer: list = []
        self._cleaned = False
        self._temp_dir = Path(tempfile.mkdtemp(prefix="physio_script_"))

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for PyAudio stream - stores audio data."""
        if self.is_recording:
            self._buffer.append(in_data)
        return (None, pyaudio.paContinue)

    def start_recording(self):
        """Start recording audio from the microphone.

        Raises RuntimeError with a human-readable message if no input device is
        available or the OS denies microphone access, so the UI can show it.
        """
        if self.is_recording:
            return

        # Make sure there's actually an input device before opening a stream.
        try:
            self.audio.get_default_input_device_info()
        except Exception:
            raise RuntimeError(
                "No microphone input device was found.\n\n"
                "Connect/enable a microphone in System Settings → Sound → Input, "
                "then try again."
            )

        self._buffer = []
        try:
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=1024,
                stream_callback=self._audio_callback,
            )
            self.stream.start_stream()
        except Exception as e:
            self.is_recording = False
            raise RuntimeError(
                "Could not start the microphone.\n\n"
                "If this is the packaged app, grant it microphone access in\n"
                "System Settings → Privacy & Security → Microphone, then relaunch.\n\n"
                f"(details: {e})"
            )

        self.is_recording = True

    def stop_recording(self) -> Optional[Path]:
        """Stop recording and return the path to the last audio chunk."""
        if not self.is_recording:
            return None

        self.is_recording = False

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        return self._save_chunk()

    def _save_chunk(self) -> Optional[Path]:
        """Save the current buffer to a WAV file."""
        # Swap the buffer out atomically so the audio callback keeps filling a
        # fresh list while we write this one — avoids losing frames mid-write.
        buffer = self._buffer
        self._buffer = []
        if not buffer:
            return None

        chunk_path = self._temp_dir / f"chunk_{len(list(self._temp_dir.glob('*.wav'))):04d}.wav"

        with wave.open(str(chunk_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(buffer))

        return chunk_path

    def get_all_chunks(self) -> list[Path]:
        """Get all saved audio chunks."""
        return sorted(self._temp_dir.glob("*.wav"))

    def cleanup(self):
        """Clean up temporary files and PyAudio. Safe to call more than once."""
        if self._cleaned:
            return
        self._cleaned = True

        if self.stream:
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        try:
            self.audio.terminate()
        except Exception:
            pass

        # Clean up temp files
        import shutil
        if self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            pass
