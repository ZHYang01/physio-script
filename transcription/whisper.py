import wave
from pathlib import Path
from typing import Optional

import numpy as np


class WhisperTranscriber:
    """Transcribes audio fully locally using faster-whisper (CTranslate2).

    No audio ever leaves the machine. The model is loaded lazily on first use
    (which also triggers the one-time model download) so constructing this
    object is cheap and never blocks app startup.
    """

    def __init__(
        self,
        model_name: str = "large-v3-turbo",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model = None  # lazily constructed faster_whisper.WhisperModel

    @property
    def model(self):
        """Lazily load the Whisper model (downloads on first run, then cached)."""
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def preload(self) -> bool:
        """Force the model to load now. Returns True on success."""
        try:
            _ = self.model
            return True
        except Exception as e:
            print(f"Whisper model load error: {e}")
            return False

    @staticmethod
    def _read_wav_float32(audio_path: Path) -> Optional[np.ndarray]:
        """Read a 16-bit PCM WAV into a mono float32 array in [-1, 1].

        Avoids needing ffmpeg/PyAV at runtime since our recorder writes plain
        16 kHz mono PCM WAV files.
        """
        with wave.open(str(audio_path), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if not raw:
            return None
        if sampwidth != 2:
            # Unexpected format; let the caller fall back / skip.
            raise ValueError(f"Unsupported sample width: {sampwidth * 8}-bit")

        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_channels > 1:
            audio = audio.reshape(-1, n_channels).mean(axis=1)
        return audio

    def transcribe_file(self, audio_path: Path, language: str = "en") -> Optional[str]:
        """
        Transcribe an audio file to text, locally.

        Args:
            audio_path: Path to a WAV file produced by the recorder.
            language: Language code (default: English).

        Returns:
            Transcribed text, or None if there was nothing to transcribe / an error.
        """
        if not audio_path.exists():
            return None

        try:
            audio = self._read_wav_float32(audio_path)
            if audio is None or audio.size == 0:
                return None

            segments, _info = self.model.transcribe(
                audio,
                language=language,
                # Greedy decoding keeps live per-chunk transcription comfortably
                # ahead of the ~5s recording chunks; accuracy loss is minimal for
                # clear consultation speech.
                beam_size=1,
                vad_filter=True,  # skip silence so empty chunks don't hallucinate
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text or None
        except Exception as e:
            print(f"Transcription error: {e}")
            return None

    def transcribe_chunks(self, audio_paths: list[Path], language: str = "en") -> str:
        """Transcribe multiple audio chunks and concatenate results."""
        transcripts = []
        for path in audio_paths:
            text = self.transcribe_file(path, language)
            if text:
                transcripts.append(text)
        return " ".join(transcripts)
