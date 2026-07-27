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
    def __init__(self, app_dir: str, version: str, notify, *, debug: bool = False):
        self.app_dir = app_dir
        self.version = version
        self.notify = notify
        self.debug = debug
        self._webview = None
        self.config = load_config(app_dir)
        self.overlay = None
        self.translator = None
        self.capture = None
        self.running = False
        self._thread = None
        self._session_count = 0
        self._monitors = self._get_monitors()
        self._hotkeys_registered = False
        self._region_lock = threading.Lock()
        self._tk_queue: queue.Queue = queue.Queue()
        self._tk_ready = threading.Event()
        self._tk_root = None
        threading.Thread(target=self._tk_thread_main, daemon=True, name="nidus-tk").start()
        self._tk_ready.wait(timeout=10)
        self._register_hotkeys()
        if self.debug:
            self._emit_status(
                "Modo debug",
                "Atalhos globais podem falhar sem admin. Rode sem --debug para uso em jogos.",
            )

    def attach_window(self, window):
        self._webview = window

    def _tk_thread_main(self):
        root = tk.Tk()
        root.withdraw()
        self._tk_root = root
        self._tk_ready.set()

        def pump():
            while True:
                try:
                    task = self._tk_queue.get_nowait()
                    task()
                except queue.Empty:
                    break
            root.after(50, pump)

        root.after(50, pump)
        root.mainloop()

    def _tk_call(self, fn, timeout=120):
        done = threading.Event()
        err = [None]

        def wrapped():
            try:
                fn()
            except Exception as exc:
                err[0] = exc
            finally:
                done.set()

        self._tk_queue.put(wrapped)
        if not done.wait(timeout=timeout):
            raise TimeoutError("Operação Tk expirou")
        if err[0]:
            raise err[0]

    def _hide_webview(self):
        if not self._webview:
            return
        try:
            self._webview.minimize()
        except Exception:
            pass

    def _show_webview(self):
        if not self._webview:
            return
        try:
            self._webview.restore()
        except Exception:
            pass

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

    def _select_region_standalone(self):
        with self._region_lock:
            self._hide_webview()
            try:
                self._emit_status("Selecione a região", "Arraste na tela. ESC cancela.")
                mon = self._selected_monitor()
                result = [None]

                def pick():
                    selector = RegionSelector(self._tk_root, mon)
                    self._tk_root.wait_window(selector)
                    result[0] = selector.result

                self._tk_call(pick)
                if result[0]:
                    self.config["region"] = result[0]
                    save_config(self.app_dir, self.config)
                    self._emit_state()
                    self._emit_status("Região selecionada", self._region_label())
            except Exception as exc:
                self._emit_status("Erro na região", str(exc)[:120])
            finally:
                self._show_webview()

    def select_region(self) -> dict:
        threading.Thread(target=self._select_region_standalone, daemon=True).start()
        return {"ok": True}

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
            self._emit_status("Erro", "Selecione uma região primeiro (F9).")
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
        return (hotkey or "").strip().lower()

    def _register_hotkey(self, hotkey: str, callback):
        hk = self._normalize_hotkey(hotkey)
        if not hk or sys.platform != "win32":
            return
        try:
            keyboard.add_hotkey(hk, callback, suppress=False)
        except Exception as exc:
            from src.debug_log import log
            log(f"Hotkey '{hk}' não registrado: {exc}")

    def _run_hotkey(self, fn):
        threading.Thread(target=fn, daemon=True).start()

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
            lambda: self._run_hotkey(self._select_region_standalone),
        )
        self._register_hotkey(
            self.config.get("hotkey_translate", "f10"),
            lambda: self._run_hotkey(self.translate_toggle),
        )
        self._register_hotkey(
            self.config.get("hotkey_toggle", "f11"),
            lambda: self._run_hotkey(self.toggle_overlay),
        )
        self._hotkeys_registered = True

    def shutdown(self):
        self.running = False
        if sys.platform == "win32":
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
