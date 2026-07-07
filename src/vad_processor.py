"""Detecção de atividade de voz (VAD) com Silero ou fallback por energia."""

import collections

import numpy as np

from src.audio_capture import SAMPLE_RATE

CHUNK_DURATION = 0.032  # 32 ms


class VADProcessor:
    """Acumula áudio enquanto há fala e emite segmentos ao detectar pausa."""

    def __init__(
        self,
        threshold: float = 0.45,
        min_speech_duration: float = 1.0,
        max_speech_duration: float = 12.0,
        silence_duration: float = 0.7,
        mode: str = "auto",
    ):
        self.threshold = threshold
        self.energy_threshold = 0.015
        self.min_speech_samples = int(min_speech_duration * SAMPLE_RATE)
        self.max_speech_samples = int(max_speech_duration * SAMPLE_RATE)
        self.silence_limit = max(1, round(silence_duration / CHUNK_DURATION))
        self.mode = mode
        self._silero = None
        self._speech_buffer: list[np.ndarray] = []
        self._speech_samples = 0
        self._is_speaking = False
        self._silence_counter = 0
        self._pre_buffer: collections.deque = collections.deque(maxlen=3)

    def _init_silero(self):
        if self._silero is not None:
            return True
        try:
            import torch

            torch.set_num_threads(1)
            try:
                from silero_vad import load_silero_vad

                self._silero = load_silero_vad()
            except ImportError:
                self._silero, _ = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    trust_repo=True,
                )
            self._silero.eval()
            return True
        except Exception:
            self._silero = False
            return False

    def _confidence(self, chunk: np.ndarray) -> float:
        use_silero = self.mode in ("auto", "silero")
        if use_silero and self._init_silero() and self._silero:
            window = 512 if SAMPLE_RATE == 16000 else 256
            data = chunk[:window]
            if len(data) < window:
                data = np.pad(data, (0, window - len(data)))
            import torch

            with torch.inference_mode():
                tensor = torch.from_numpy(data).float()
                return float(self._silero(tensor, SAMPLE_RATE).item())

        rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0
        return min(1.0, rms / max(self.energy_threshold * 2, 1e-6))

    def process_chunk(self, chunk: np.ndarray) -> np.ndarray | None:
        confidence = self._confidence(chunk)
        silero_active = self._silero not in (None, False)
        effective_threshold = self.threshold if silero_active else 0.35

        if confidence >= effective_threshold:
            if not self._is_speaking:
                for pre in self._pre_buffer:
                    self._speech_buffer.append(pre)
                    self._speech_samples += len(pre)
                self._pre_buffer.clear()
                self._is_speaking = True
                self._silence_counter = 0

            self._speech_buffer.append(chunk)
            self._speech_samples += len(chunk)
        elif self._is_speaking:
            self._silence_counter += 1
            self._speech_buffer.append(chunk)
            self._speech_samples += len(chunk)
        else:
            self._pre_buffer.append(chunk)

        if self._speech_samples >= self.max_speech_samples:
            return self._flush()

        if (
            self._is_speaking
            and self._silence_counter >= self.silence_limit
            and self._speech_samples >= self.min_speech_samples
        ):
            return self._flush()

        return None

    def _flush(self) -> np.ndarray | None:
        if not self._speech_buffer:
            self._reset()
            return None
        segment = np.concatenate(self._speech_buffer)
        self._reset()
        return segment

    def _reset(self):
        self._speech_buffer = []
        self._speech_samples = 0
        self._is_speaking = False
        self._silence_counter = 0

    def flush_pending(self) -> np.ndarray | None:
        if self._speech_samples >= self.min_speech_samples:
            return self._flush()
        self._reset()
        return None

    def warmup(self):
        """Pré-carrega Silero VAD para evitar travamento na primeira fala."""
        from src.debug_log import log

        log("Inicializando VAD...")
        dummy = np.zeros(512, dtype=np.float32)
        self._confidence(dummy)
        mode = "Silero" if self._silero not in (None, False) else "energia"
        log(f"VAD pronto ({mode}).")
