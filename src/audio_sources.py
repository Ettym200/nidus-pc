"""Utilitários para listar e criar capturas de áudio (Windows + Linux)."""

from __future__ import annotations

import sys

CAPTURE_MODES_ALL = [
    ("system", "Todo o sistema"),
    ("application", "Aplicativo específico"),
]


def get_capture_modes() -> list[tuple[str, str]]:
    modes = [CAPTURE_MODES_ALL[0]]
    if is_app_capture_supported():
        modes.append(CAPTURE_MODES_ALL[1])
    return modes


# Compat: lista estática usada por imports antigos
CAPTURE_MODES = CAPTURE_MODES_ALL

try:
    from process_audio_capture import ProcessAudioCapture as _PacEnum

    _APP_LIST_AVAILABLE = _PacEnum.is_supported()
except ImportError:
    _PacEnum = None
    _APP_LIST_AVAILABLE = False


def is_audio_supported() -> bool:
    if sys.platform == "win32":
        try:
            import pyaudiowpatch  # noqa: F401
            return True
        except ImportError:
            return False
    if sys.platform.startswith("linux"):
        try:
            import soundcard  # noqa: F401
            return True
        except ImportError:
            return False
    return False


def is_app_capture_supported() -> bool:
    return sys.platform == "win32" and _APP_LIST_AVAILABLE


def list_output_devices() -> list[str]:
    if sys.platform == "win32":
        from src.audio_capture import list_output_devices as _win

        return _win()
    if sys.platform.startswith("linux"):
        from src.audio_capture_linux import list_output_devices as _linux

        return _linux()
    return []


def list_audio_applications() -> list[dict]:
    """Lista apps que estão reproduzindo áudio agora (Windows)."""
    if not is_app_capture_supported() or _PacEnum is None:
        return []
    try:
        processes = _PacEnum.enumerate_audio_processes()
    except Exception:
        return []

    seen: set[int] = set()
    apps: list[dict] = []
    for proc in processes:
        if proc.pid in seen:
            continue
        seen.add(proc.pid)
        title = (proc.window_title or "").strip()
        if title:
            label = f"{proc.name} — {title}"
        else:
            label = proc.name
        apps.append(
            {
                "pid": proc.pid,
                "name": proc.name,
                "title": title,
                "label": label,
            }
        )
    apps.sort(key=lambda a: a["label"].lower())
    return apps


def create_audio_capture(
    mode: str = "system",
    device: str | None = None,
    target_pid: int | None = None,
):
    """Factory: captura do sistema inteiro ou de um app (Windows)."""
    if mode == "application":
        if not is_app_capture_supported():
            raise ValueError(
                "Captura por aplicativo só está disponível no Windows. "
                "No Linux use 'Todo o sistema'."
            )
        if not target_pid:
            raise ValueError("Selecione um aplicativo para capturar.")
        from src.app_audio_capture import AppAudioCapture

        return AppAudioCapture(target_pid)

    if sys.platform.startswith("linux"):
        from src.audio_capture_linux import AudioCaptureLinux

        return AudioCaptureLinux(device=device)

    from src.audio_capture import AudioCapture

    return AudioCapture(device=device)
