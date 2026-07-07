"""Captura de áudio de um aplicativo específico (Windows)."""

import queue
import threading

import numpy as np

from src.audio_capture import SAMPLE_RATE, READ_DURATION
from src.debug_log import log

PROC_SAMPLE_RATE = 48000
PROC_CHANNELS = 2
CHUNK_SAMPLES = int(SAMPLE_RATE * READ_DURATION)


class AppAudioCapture:
    """Captura áudio de um único processo via proc-tap / WASAPI loopback."""

    def __init__(self, pid: int):
        self._pid = pid
        self.sample_rate = SAMPLE_RATE
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self._buffer = np.array([], dtype=np.float32)
        self._capture = None
        self._running = False
        self._read_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _pcm_to_mono_16k(pcm: bytes) -> np.ndarray:
        audio = np.frombuffer(pcm, dtype=np.float32)
        if len(audio) == 0:
            return np.array([], dtype=np.float32)
        if len(audio) >= PROC_CHANNELS and len(audio) % PROC_CHANNELS == 0:
            audio = audio.reshape(-1, PROC_CHANNELS).mean(axis=1)
        if PROC_SAMPLE_RATE != SAMPLE_RATE:
            ratio = SAMPLE_RATE / PROC_SAMPLE_RATE
            n_out = int(len(audio) * ratio)
            if n_out <= 0:
                return np.array([], dtype=np.float32)
            indices = np.arange(n_out) / ratio
            indices = np.clip(indices, 0, len(audio) - 1)
            idx_floor = indices.astype(np.int64)
            idx_ceil = np.minimum(idx_floor + 1, len(audio) - 1)
            frac = (indices - idx_floor).astype(np.float32)
            audio = audio[idx_floor] * (1 - frac) + audio[idx_ceil] * frac
        return audio.astype(np.float32)

    def _enqueue_chunks(self, mono: np.ndarray):
        if len(mono) == 0:
            return
        with self._lock:
            self._buffer = np.concatenate([self._buffer, mono])
            while len(self._buffer) >= CHUNK_SAMPLES:
                chunk = self._buffer[:CHUNK_SAMPLES].copy()
                self._buffer = self._buffer[CHUNK_SAMPLES:]
                try:
                    self.audio_queue.put_nowait(chunk)
                except queue.Full:
                    try:
                        self.audio_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self.audio_queue.put_nowait(chunk)

    def _read_loop(self):
        """Lê áudio via polling — mais estável que callback nativo."""
        while self._running and self._capture is not None:
            try:
                pcm = self._capture.read(timeout=0.15)
                if not pcm:
                    continue
                mono = self._pcm_to_mono_16k(pcm)
                self._enqueue_chunks(mono)
            except Exception as exc:
                log(f"Erro ao ler áudio do app: {exc}")

    def start(self):
        from proctap import ProcessAudioCapture

        log(f"Capturando áudio do PID {self._pid}...")
        self._capture = ProcessAudioCapture(self._pid)
        self._running = True
        self._capture.start()
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()

    def stop(self):
        self._running = False
        if self._read_thread:
            self._read_thread.join(timeout=3)
            self._read_thread = None
        if self._capture:
            try:
                self._capture.close()
            except Exception:
                pass
            self._capture = None
        with self._lock:
            self._buffer = np.array([], dtype=np.float32)

    def get_chunk(self, timeout: float = 0.2) -> np.ndarray | None:
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self.stop()
