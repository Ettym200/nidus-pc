"""Utilitários para listar e criar capturas de áudio."""

from __future__ import annotations

import sys

CAPTURE_MODES = [
    ("system", "Todo o sistema"),
    ("application", "Aplicativo específico"),
]

try:
    from process_audio_capture import ProcessAudioCapture as _PacEnum

    _APP_LIST_AVAILABLE = _PacEnum.is_supported()
except ImportError:
    _PacEnum = None
    _APP_LIST_AVAILABLE = False


def is_app_capture_supported() -> bool:
    return sys.platform == "win32" and _APP_LIST_AVAILABLE


def list_audio_applications() -> list[dict]:
    """Lista apps que estão reproduzindo áudio agora."""
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
    """Factory: captura do sistema inteiro ou de um app."""
    if mode == "application":
        if not target_pid:
            raise ValueError("Selecione um aplicativo para capturar.")
        from src.app_audio_capture import AppAudioCapture

        return AppAudioCapture(target_pid)

    from src.audio_capture import AudioCapture

    return AudioCapture(device=device)
