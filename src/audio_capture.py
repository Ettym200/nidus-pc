"""Captura de áudio do sistema via WASAPI loopback (Windows)."""

import queue
import threading
import time

import numpy as np

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    pyaudio = None

SAMPLE_RATE = 16000
READ_DURATION = 0.032  # 32 ms — alimenta o VAD com baixa latência


def _require_pyaudio():
    if pyaudio is None:
        raise RuntimeError(
            "PyAudioWPatch não instalado. Execute: pip install PyAudioWPatch"
        )


def list_output_devices() -> list[str]:
    """Lista dispositivos de saída WASAPI disponíveis para loopback."""
    _require_pyaudio()
    pa = pyaudio.PyAudio()
    devices = []
    wasapi_idx = None
    try:
        for i in range(pa.get_host_api_count()):
            info = pa.get_host_api_info_by_index(i)
            if "WASAPI" in info["name"]:
                wasapi_idx = info["index"]
                break
        if wasapi_idx is not None:
            for i in range(pa.get_device_count()):
                dev = pa.get_device_info_by_index(i)
                if (
                    dev["hostApi"] == wasapi_idx
                    and dev["maxOutputChannels"] > 0
                    and not dev.get("isLoopbackDevice", False)
                ):
                    devices.append(dev["name"])
    finally:
        pa.terminate()
    return devices


class AudioCapture:
    """Captura áudio do sistema em frames curtos mono 16 kHz."""

    def __init__(self, device: str | None = None):
        _require_pyaudio()
        self.sample_rate = SAMPLE_RATE
        self._device_name = device
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self._pa = pyaudio.PyAudio()
        self._stream = None
        self._running = False
        self._read_thread = None
        self._native_channels = 2
        self._native_rate = 44100
        self._lock = threading.Lock()

    def _get_wasapi_info(self):
        for i in range(self._pa.get_host_api_count()):
            info = self._pa.get_host_api_info_by_index(i)
            if "WASAPI" in info["name"]:
                return info
        return None

    def _find_loopback_device(self):
        wasapi_info = self._get_wasapi_info()
        if wasapi_info is None:
            raise RuntimeError("WASAPI não encontrado neste sistema.")

        default_output = self._pa.get_device_info_by_index(
            wasapi_info["defaultOutputDevice"]
        )
        target_name = self._device_name or default_output["name"]

        for i in range(self._pa.get_device_count()):
            dev = self._pa.get_device_info_by_index(i)
            if dev["hostApi"] == wasapi_info["index"] and dev.get("isLoopbackDevice", False):
                if target_name in dev["name"]:
                    return dev

        for i in range(self._pa.get_device_count()):
            dev = self._pa.get_device_info_by_index(i)
            if dev.get("isLoopbackDevice", False):
                return dev

        raise RuntimeError("Nenhum dispositivo WASAPI loopback encontrado.")

    def _open_stream(self):
        loopback_dev = self._find_loopback_device()
        self._native_channels = loopback_dev["maxInputChannels"]
        self._native_rate = int(loopback_dev["defaultSampleRate"])
        native_chunk = max(1, int(self._native_rate * READ_DURATION))

        self._stream = self._pa.open(
            format=pyaudio.paFloat32,
            channels=self._native_channels,
            rate=self._native_rate,
            input=True,
            input_device_index=loopback_dev["index"],
            frames_per_buffer=native_chunk,
        )

    def _close_stream(self):
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    @staticmethod
    def _resample_to_mono(data: bytes, native_channels: int, native_rate: int) -> np.ndarray:
        audio = np.frombuffer(data, dtype=np.float32)
        if native_channels > 1:
            audio = audio.reshape(-1, native_channels).mean(axis=1)
        if native_rate != SAMPLE_RATE:
            ratio = SAMPLE_RATE / native_rate
            n_out = int(len(audio) * ratio)
            indices = np.arange(n_out) / ratio
            indices = np.clip(indices, 0, len(audio) - 1)
            idx_floor = indices.astype(np.int64)
            idx_ceil = np.minimum(idx_floor + 1, len(audio) - 1)
            frac = (indices - idx_floor).astype(np.float32)
            audio = audio[idx_floor] * (1 - frac) + audio[idx_ceil] * frac
        return audio

    def _read_loop(self):
        native_chunk = max(1, int(self._native_rate * READ_DURATION))
        while self._running:
            try:
                with self._lock:
                    if not self._stream:
                        time.sleep(0.005)
                        continue
                    if self._stream.get_read_available() < native_chunk:
                        time.sleep(0.005)
                        continue
                    data = self._stream.read(native_chunk, exception_on_overflow=False)

                audio = self._resample_to_mono(
                    data, self._native_channels, self._native_rate
                )
                try:
                    self.audio_queue.put_nowait(audio)
                except queue.Full:
                    try:
                        self.audio_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self.audio_queue.put_nowait(audio)
            except Exception:
                time.sleep(0.05)

    def start(self):
        self._open_stream()
        self._running = True
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()

    def stop(self):
        self._running = False
        if self._read_thread:
            self._read_thread.join(timeout=3)
        self._close_stream()

    def get_chunk(self, timeout: float = 0.2) -> np.ndarray | None:
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self.stop()
        if self._pa:
            self._pa.terminate()
            self._pa = None
