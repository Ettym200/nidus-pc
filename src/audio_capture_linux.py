"""Captura de áudio do sistema no Linux (PulseAudio / PipeWire monitor)."""

from __future__ import annotations

import queue
import subprocess
import threading
import time

import numpy as np

from src.audio_constants import READ_DURATION, SAMPLE_RATE

try:
    import soundcard as sc
except ImportError:
    sc = None


def _require_soundcard():
    if sc is None:
        raise RuntimeError(
            "Pacote 'SoundCard' não instalado. No Linux: pip install SoundCard"
        )


def list_output_devices() -> list[str]:
    """Lista saídas/monitores disponíveis para loopback."""
    _require_soundcard()
    names: list[str] = []
    try:
        for sp in sc.all_speakers():
            label = (sp.name or "").strip()
            if label and label not in names:
                names.append(label)
    except Exception:
        pass
    return names


def _pick_loopback_mic(device: str | None):
    """Retorna um Microphone SoundCard em modo loopback da saída escolhida."""
    _require_soundcard()
    speakers = list(sc.all_speakers())
    if not speakers:
        raise RuntimeError(
            "Nenhuma saída de áudio encontrada. Verifique PulseAudio/PipeWire."
        )

    target = None
    if device:
        for sp in speakers:
            if device in (sp.name or ""):
                target = sp
                break
    if target is None:
        try:
            target = sc.default_speaker()
        except Exception:
            target = speakers[0]

    # include_loopback captura o que está saindo pelos speakers
    return sc.get_microphone(id=str(target.name), include_loopback=True)


class AudioCaptureLinux:
    """Captura áudio do sistema (monitor) em frames curtos mono 16 kHz."""

    def __init__(self, device: str | None = None):
        _require_soundcard()
        self.sample_rate = SAMPLE_RATE
        self._device_name = device
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self._running = False
        self._read_thread: threading.Thread | None = None
        self._mic = None
        self._recorder = None

    def _open_stream(self):
        self._mic = _pick_loopback_mic(self._device_name)
        # recorder context is managed manually for long-running capture
        self._recorder = self._mic.recorder(samplerate=SAMPLE_RATE, channels=1)
        self._recorder.__enter__()

    def _close_stream(self):
        if self._recorder is not None:
            try:
                self._recorder.__exit__(None, None, None)
            except Exception:
                pass
            self._recorder = None
        self._mic = None

    def _read_loop(self):
        frames = max(1, int(SAMPLE_RATE * READ_DURATION))
        while self._running:
            try:
                if self._recorder is None:
                    time.sleep(0.01)
                    continue
                data = self._recorder.record(numframes=frames)
                if data is None or len(data) == 0:
                    time.sleep(0.005)
                    continue
                audio = np.asarray(data, dtype=np.float32).reshape(-1)
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
            self._read_thread = None
        self._close_stream()

    def get_chunk(self, timeout: float = 0.2) -> np.ndarray | None:
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self.stop()


def pulse_monitor_hint() -> str:
    """Dica rápida se o usuário não tiver monitor configurado."""
    try:
        out = subprocess.run(
            ["pactl", "list", "short", "sources"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode == 0 and ".monitor" in (out.stdout or ""):
            return ""
    except Exception:
        pass
    return (
        "Nenhum monitor Pulse/PipeWire detectado. "
        "Instale pipewire/pulseaudio e toque algum áudio no sistema."
    )
