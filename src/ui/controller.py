import queue
import sys
import threading
import tkinter as tk

import keyboard
import mss

from src.capture import ScreenCapture
from src.overlay import OVERLAY_STYLE_OPTIONS, Overlay
from src.translator import KNOWN_PROVIDERS, Translator
from src.ui.config_store import LANGUAGES, load_config, save_config
from src.ui.region_selector import RegionSelector


class NidusController:
    OVERLAY_IDS = [sid for sid, _label in OVERLAY_STYLE_OPTIONS]

    def __init__(self, app_dir: str, version: str, notify, *, debug: bool = False):
        self.app_dir = app_dir
        self.version = version
        self.notify = notify
        self.debug = debug
        self.window = None
        self.config = load_config(app_dir)
        self._tk = None
        self._tk_ready = threading.Event()
        self._actions: queue.Queue = queue.Queue()
        self.overlay = None
        self.translator = None
        self.capture = None
        self.running = False
        self._thread = None
        self._session_count = 0
        self._monitors = self._get_monitors()
        self._hotkeys_registered = False
        threading.Thread(target=self._run_tk_loop, daemon=True).start()
        self._tk_ready.wait(timeout=5)
        self._register_hotkeys()
        if self.debug:
            self._emit_status(
                "Modo debug",
                "Atalhos globais podem falhar sem admin. Use os botões ou rode sem --debug.",
            )

    def _run_tk_loop(self):
        self._tk = tk.Tk()
        self._tk.withdraw()
        self._tk_ready.set()
        self._poll_actions()
        self._tk.mainloop()

    def _poll_actions(self):
        while True:
            try:
                fn = self._actions.get_nowait()
                fn()
            except queue.Empty:
                break
            except Exception as exc:
                self._emit_status("Erro", str(exc)[:120])
        if self._tk:
            self._tk.after(30, self._poll_actions)

    def _dispatch(self, fn):
        self._actions.put(fn)

    def attach_window(self, window):
        self.window = window

    def _get_monitors(self) -> list[dict]:
        with mss.mss() as sct:
            return list(sct.monitors[1:])

    def _selected_monitor(self) -> dict:
        idx = int(self.config.get("monitor_index", 0) or 0)
        if not self._monitors:
            return {"left": 0, "top": 0, "width": 1920, "height": 1080}
        return self._monitors[min(idx, len(self._monitors) - 1)]

    def _region_label(self) -> str:
        region = self.config.get("region")
        if not region:
            return "Nenhuma selecionada"
        w = region["x2"] - region["x1"]
        h = region["y2"] - region["y1"]
        return f"{w} × {h} px"

    def _provider_label(self) -> str:
        if not self.config.get("api_key"):
            return "Sem chave configurada"
        model = self.config.get("model") or "padrão"
        return f"{self.config.get('api_provider', 'openrouter')} · {model}"

    def get_state(self) -> dict:
        mon = self._selected_monitor()
        return {
            "version": self.version,
            "config": self.config,
            "providers": list(KNOWN_PROVIDERS.keys()),
            "languages": LANGUAGES,
            "overlay_styles": [{"id": sid, "label": label} for sid, label in OVERLAY_STYLE_OPTIONS],
            "monitors": [
                {"index": i, "width": m["width"], "height": m["height"]}
                for i, m in enumerate(self._monitors)
            ],
            "game": {
                "running": self.running,
                "mode": self.config.get("mode", "once"),
                "region_label": self._region_label(),
                "session_count": self._session_count,
                "monitor_index": self.config.get("monitor_index", 0),
                "monitor_width": mon["width"],
                "monitor_height": mon["height"],
                "has_api_key": bool(self.config.get("api_key")),
                "provider_label": self._provider_label(),
            },
        }

    def patch_config(self, patch: dict) -> dict:
        if not patch:
            return {"ok": True}
        self.config.update(patch)
        save_config(self.app_dir, self.config)
        self._apply_overlay_style()
        self._register_hotkeys()
        self._emit_state()
        return {"ok": True}

    def _emit_state(self):
        self.notify("state", self.get_state())

    def _emit_status(self, title: str, detail: str = ""):
        self.notify("status", {"title": title, "detail": detail})

    def _ensure_overlay(self) -> Overlay:
        style = self.config.get("overlay_style", "transparent")
        if not self.overlay:
            self.overlay = Overlay(style=style)
        else:
            self.overlay.set_style(style)
        return self.overlay

    def _apply_overlay_style(self):
        if self.overlay:
            self.overlay.set_style(self.config.get("overlay_style", "transparent"))

    def select_region(self) -> dict:
        done = threading.Event()

        def work():
            try:
                self._select_region_ui()
            finally:
                done.set()

        self._dispatch(work)
        done.wait(timeout=120)
        return {"ok": True}

    def _select_region_ui(self):
        if not self._tk:
            return
        if self.window:
            try:
                self.window.minimize()
            except Exception:
                pass
        mon = self._selected_monitor()
        selector = RegionSelector(self._tk, mon)
        self._tk.wait_window(selector)
        if self.window:
            try:
                self.window.restore()
            except Exception:
                pass
        if selector.result:
            self.config["region"] = selector.result
            save_config(self.app_dir, self.config)
            self._emit_state()
            self._emit_status("Região selecionada", self._region_label())

    def toggle_overlay(self) -> dict:
        if not self.overlay:
            return {"ok": False}
        if self.overlay._visible:
            self.overlay.hide()
        else:
            self.overlay._root.after(0, self.overlay._root.deiconify)
            self.overlay._visible = True
        return {"ok": True}

    def translate_toggle(self) -> dict:
        if self.running:
            self._stop()
        else:
            self._start()
        return {"ok": True}

    def _start(self):
        if not self.config.get("api_key"):
            self._emit_status("Erro", "Configure a API Key nas configurações (⚙).")
            self._emit_state()
            return
        if not self.config.get("region"):
            self._emit_status("Erro", "Selecione uma região primeiro.")
            self._emit_state()
            return

        self._ensure_overlay()
        self.translator = Translator(
            api_key=self.config["api_key"],
            provider=self.config["api_provider"],
            target_language=self.config["target_language"],
            custom_base_url=self.config.get("custom_base_url", ""),
            model=self.config.get("model", ""),
        )
        self.capture = ScreenCapture(
            self.config["region"],
            float(self.config.get("capture_interval", 1.5)),
        )

        mode = self.config.get("mode", "once")
        if mode == "once":
            self._emit_status("Traduzindo...", "")
            self._thread = threading.Thread(target=self._translate_once, daemon=True)
        else:
            self.running = True
            self._emit_status("Rodando...", "Modo contínuo ativo")
            self._thread = threading.Thread(target=self._loop, daemon=True)
        self._emit_state()
        self._thread.start()

    def _stop(self):
        self.running = False
        self._emit_status("Parado", "")
        self._emit_state()

    def _translate_once(self):
        try:
            frame, _ = next(self.capture.stream())
            translation = self.translator.translate(frame)
            if translation:
                self.overlay.show(translation)
                self._session_count += 1
                preview = translation if len(translation) <= 80 else translation[:80] + "..."
                self._emit_status("Tradução concluída!", f'"{preview}"')
            else:
                self._emit_status("Nenhum texto encontrado.", "")
        except Exception as exc:
            self._emit_status("Erro", str(exc)[:120])
        finally:
            self._emit_state()

    def _loop(self):
        last_translation = ""
        for frame, changed in self.capture.stream():
            if not self.running:
                break
            if not changed:
                continue
            try:
                translation = self.translator.translate(frame)
                if translation and translation != last_translation:
                    last_translation = translation
                    self.overlay.show(translation)
                    self._session_count += 1
                    preview = translation if len(translation) <= 80 else translation[:80] + "..."
                    self._emit_status("Traduzindo...", f'"{preview}"')
            except Exception as exc:
                self._emit_status("Erro", str(exc)[:120])
        self._emit_state()

    def _normalize_hotkey(self, hotkey: str) -> str:
        hk = (hotkey or "").strip().lower()
        if hk.startswith("mouse:"):
            return hk
        return hk

    def _register_hotkey(self, hotkey: str, callback):
        hk = self._normalize_hotkey(hotkey)
        if not hk or sys.platform != "win32":
            return
        try:
            keyboard.add_hotkey(hk, callback, suppress=False)
        except Exception as exc:
            from src.debug_log import log
            log(f"Hotkey '{hk}' não registrado: {exc}")

    def _register_hotkeys(self):
        if sys.platform != "win32":
            return
        if self._hotkeys_registered:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
        self._register_hotkey(
            self.config.get("hotkey_region", "f9"),
            lambda: self._dispatch(self._select_region_ui),
        )
        self._register_hotkey(
            self.config.get("hotkey_translate", "f10"),
            lambda: self._dispatch(self.translate_toggle),
        )
        self._register_hotkey(
            self.config.get("hotkey_toggle", "f11"),
            lambda: self._dispatch(self.toggle_overlay),
        )
        self._hotkeys_registered = True

    def shutdown(self):
        self.running = False
        if sys.platform == "win32":
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
