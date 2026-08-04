"""Registro de atalhos globais (Windows: keyboard, Linux: pynput)."""

from __future__ import annotations

import sys
import threading

from src.debug_log import log

_lock = threading.Lock()
_windows_ready = False
_linux_hotkeys = None  # pynput GlobalHotKeys


def _normalize(hotkey: str) -> str:
    return (hotkey or "").strip().lower()


def _pynput_combo(hotkey: str) -> str | None:
    hk = _normalize(hotkey)
    if not hk:
        return None
    # f9 -> <f9> ; ctrl+shift+a -> <ctrl>+<shift>+a
    parts = []
    for part in hk.replace(" ", "").split("+"):
        if not part:
            continue
        if len(part) == 1:
            parts.append(part)
        else:
            parts.append(f"<{part}>")
    return "+".join(parts) if parts else None


def clear_hotkeys():
    global _windows_ready, _linux_hotkeys
    with _lock:
        if sys.platform == "win32":
            try:
                import keyboard

                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
            _windows_ready = False
        else:
            if _linux_hotkeys is not None:
                try:
                    _linux_hotkeys.stop()
                except Exception:
                    pass
                _linux_hotkeys = None


def register_hotkeys(bindings: dict[str, callable]):
    """
    bindings: { 'f9': callback, 'f10': callback, ... }
    """
    clear_hotkeys()
    clean = { _normalize(k): v for k, v in bindings.items() if _normalize(k) and callable(v) }
    if not clean:
        return

    if sys.platform == "win32":
        try:
            import keyboard
        except ImportError:
            log("Pacote keyboard não instalado — atalhos desativados.")
            return
        for hk, cb in clean.items():
            try:
                keyboard.add_hotkey(hk, cb, suppress=False)
            except Exception as exc:
                log(f"Hotkey '{hk}' não registrado: {exc}")
        global _windows_ready
        _windows_ready = True
        return

    # Linux / outros: pynput
    try:
        from pynput import keyboard as pk
    except ImportError:
        log("Pacote pynput não instalado — atalhos desativados no Linux.")
        return

    mapping = {}
    for hk, cb in clean.items():
        combo = _pynput_combo(hk)
        if not combo:
            continue
        mapping[combo] = cb

    if not mapping:
        return

    global _linux_hotkeys
    try:
        _linux_hotkeys = pk.GlobalHotKeys(mapping)
        _linux_hotkeys.daemon = True
        _linux_hotkeys.start()
    except Exception as exc:
        log(f"Falha ao registrar atalhos no Linux: {exc}")
        _linux_hotkeys = None
