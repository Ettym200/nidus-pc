import base64
import io
import queue
import sys
import threading
import traceback
import tkinter as tk

import keyboard
import mss
from PIL import Image

from src.audio_pipeline import AudioPipeline
from src.capture import ScreenCapture
from src.debug_log import log
from src.overlay import OVERLAY_STYLE_OPTIONS, Overlay
from src.speech_to_text import COMPUTE_OPTIONS, WHISPER_MODELS
from src.translator import KNOWN_PROVIDERS, Translator
from src.ui.config_store import (
    AUDIO_SOURCE_LANGS,
    AUDIO_SOURCE_MAP,
    INTERVIEW_TYPES,
    LANGUAGES,
    load_config,
    save_config,
)
from src.ui.region_selector import RegionSelector

try:
    from src.audio_capture import list_output_devices
    from src.audio_sources import (
        CAPTURE_MODES,
        is_app_capture_supported,
        list_audio_applications,
    )

    AUDIO_AVAILABLE = sys.platform == "win32"
except ImportError:
    AUDIO_AVAILABLE = False
    CAPTURE_MODES = []
    list_output_devices = lambda: []
    list_audio_applications = lambda: []
    is_app_capture_supported = lambda: False


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

        self._audio_pipeline = None
        self._audio_running = False
        self._interview_pipeline = None
        self._interview_running = False
        self._interview_history: list[dict] = []
        self._text_busy = False
        self._uga_busy = False

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

    def _make_translator(self, target_language: str | None = None) -> Translator:
        return Translator(
            api_key=self.config["api_key"],
            provider=self.config["api_provider"],
            target_language=target_language or self.config["target_language"],
            custom_base_url=self.config.get("custom_base_url", ""),
            model=self.config.get("model", ""),
        )

    def get_state(self) -> dict:
        mon = self._selected_monitor()
        src_code = self.config.get("audio_source_language", "auto")
        src_label = next(
            (k for k, v in AUDIO_SOURCE_MAP.items() if v == src_code),
            "auto",
        )
        return {
            "version": self.version,
            "config": self.config,
            "providers": list(KNOWN_PROVIDERS.keys()),
            "languages": LANGUAGES,
            "overlay_styles": [{"id": sid, "label": label} for sid, label in OVERLAY_STYLE_OPTIONS],
            "whisper_models": WHISPER_MODELS,
            "compute_options": COMPUTE_OPTIONS,
            "capture_modes": [{"id": mid, "label": label} for mid, label in CAPTURE_MODES],
            "audio_source_langs": AUDIO_SOURCE_LANGS,
            "audio_source_map": AUDIO_SOURCE_MAP,
            "interview_types": INTERVIEW_TYPES,
            "audio_available": AUDIO_AVAILABLE,
            "app_capture_supported": is_app_capture_supported(),
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
            "live": {
                "running": self._audio_running,
                "source_label": src_label,
            },
            "interview": {
                "running": self._interview_running,
                "context_empty": not bool((self.config.get("interview_context") or "").strip()),
                "history": self._interview_history[-8:],
            },
            "text": {"busy": self._text_busy},
            "uga": {"busy": self._uga_busy},
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

    # ── Region ──────────────────────────────────────────────────────────

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

    # ── Game translate ──────────────────────────────────────────────────

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
        if self._audio_running:
            self._stop_audio()
        if self._interview_running:
            self._stop_interview()

        self._ensure_overlay()
        self.translator = self._make_translator()
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

    # ── Text translate ──────────────────────────────────────────────────

    def translate_text(self, text: str, target_language: str | None = None) -> dict:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "Cole um texto para traduzir."}
        if not self.config.get("api_key"):
            return {"ok": False, "error": "Configure a API Key nas configurações (⚙)."}
        if self._text_busy:
            return {"ok": False, "error": "Já traduzindo..."}

        lang = target_language or self.config.get("target_language", "Português")
        self._text_busy = True
        self._emit_state()
        self.notify("text_status", {"title": "Traduzindo...", "detail": ""})

        def work():
            try:
                result = self._make_translator(lang).translate_text(text, target_language=lang)
                self.notify("text_result", {"text": result or ""})
                self.notify("text_status", {"title": "Pronto", "detail": f"{len(result or '')} caracteres"})
            except Exception as exc:
                self.notify("text_status", {"title": "Erro", "detail": str(exc)[:120]})
            finally:
                self._text_busy = False
                self._emit_state()

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True}

    # ── Uga Buga ────────────────────────────────────────────────────────

    def _decode_images(self, images_b64: list) -> list[Image.Image]:
        imgs = []
        for item in images_b64 or []:
            raw = item
            if isinstance(item, dict):
                raw = item.get("data") or item.get("b64") or ""
            if not raw:
                continue
            if "," in raw and raw.strip().startswith("data:"):
                raw = raw.split(",", 1)[1]
            try:
                imgs.append(Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB"))
            except Exception:
                continue
        return imgs

    def uga_summarize(self, text: str = "", images_b64: list | None = None) -> dict:
        text = (text or "").strip()
        imgs = self._decode_images(images_b64 or [])
        if not text and not imgs:
            return {"ok": False, "error": "Informe texto ou imagem do item/skill."}
        if not self.config.get("api_key"):
            return {"ok": False, "error": "Configure a API Key nas configurações (⚙)."}
        if self._uga_busy:
            return {"ok": False, "error": "Já gerando..."}

        self._uga_busy = True
        self._emit_state()
        self.notify("uga_status", {"title": "Gerando resumo...", "detail": ""})

        def work():
            try:
                result = self._make_translator().summarize_uga_buga(text=text, imgs=imgs)
                self.notify("uga_result", {"text": result or ""})
                self.notify("uga_status", {"title": "Pronto", "detail": f"{len(result or '')} caracteres"})
            except Exception as exc:
                self.notify("uga_status", {"title": "Erro", "detail": str(exc)[:120]})
            finally:
                self._uga_busy = False
                self._emit_state()

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True}

    # ── Live audio ──────────────────────────────────────────────────────

    def list_audio_devices(self) -> list:
        if not AUDIO_AVAILABLE:
            return []
        try:
            return list_output_devices()
        except Exception:
            return []

    def list_audio_apps(self) -> list:
        if not AUDIO_AVAILABLE:
            return []
        try:
            return list_audio_applications()
        except Exception:
            return []

    def audio_toggle(self) -> dict:
        if self._audio_running:
            self._stop_audio()
        else:
            self._start_audio()
        return {"ok": True}

    def _start_audio(self):
        if not AUDIO_AVAILABLE:
            self.notify("live_status", {"title": "Indisponível", "detail": "Recurso só no Windows."})
            return
        if not self.config.get("api_key"):
            self.notify("live_status", {"title": "Erro", "detail": "Configure a API Key (⚙)."})
            return
        if self._interview_running:
            self._stop_interview()
        if self.running:
            self._stop()

        capture_mode = self.config.get("audio_capture_mode", "system")
        target_pid = int(self.config.get("audio_target_pid") or 0) or None
        if capture_mode == "application" and not target_pid:
            self.notify("live_status", {"title": "Erro", "detail": "Selecione um aplicativo com áudio."})
            return

        device = self.config.get("audio_device") or None
        self._ensure_overlay()
        self.notify("live_status", {"title": "Iniciando...", "detail": "Carregando Whisper"})
        self._emit_state()

        def work():
            try:
                translator = self._make_translator()
                pipeline = AudioPipeline(
                    translator=translator,
                    device=device,
                    capture_mode=capture_mode,
                    target_pid=target_pid if capture_mode == "application" else None,
                    whisper_model=self.config.get("whisper_model", "tiny"),
                    compute_device=self.config.get("whisper_compute_device", "cpu"),
                    source_language=self.config.get("audio_source_language", "auto"),
                    streaming=bool(self.config.get("audio_streaming", True)),
                    mode="translate",
                    on_status=lambda msg: self.notify("live_status", {"title": msg, "detail": ""}),
                    on_original=lambda text: self.notify("live_original", {"text": text}),
                    on_translation=self._on_live_translation,
                    on_translation_partial=self._on_live_partial,
                    on_error=lambda err: self.notify(
                        "live_status", {"title": "Erro", "detail": str(err)[:120]}
                    ),
                )
                pipeline.start()
                self._audio_pipeline = pipeline
                self._audio_running = True
                self.notify("live_status", {"title": "Ouvindo...", "detail": "Aguardando fala"})
                self._emit_state()
            except Exception as exc:
                log(f"Erro ao iniciar áudio: {exc}\n{traceback.format_exc()}")
                self._audio_running = False
                self._audio_pipeline = None
                self.notify("live_status", {"title": "Erro", "detail": str(exc)[:120]})
                self._emit_state()

        threading.Thread(target=work, daemon=True).start()

    def _on_live_translation(self, text: str):
        self.notify("live_translation", {"text": text, "partial": False})
        if self.overlay:
            self.overlay.show_live(text, partial=False)

    def _on_live_partial(self, text: str):
        self.notify("live_translation", {"text": text, "partial": True})
        if self.overlay:
            self.overlay.show_live(text, partial=True)

    def _stop_audio(self):
        self._audio_running = False
        if self._audio_pipeline:
            try:
                self._audio_pipeline.stop()
            except Exception:
                pass
            self._audio_pipeline = None
        if self.overlay:
            try:
                self.overlay.clear_live()
            except Exception:
                pass
        self.notify("live_status", {"title": "Parado", "detail": ""})
        self._emit_state()

    # ── Interview ───────────────────────────────────────────────────────

    def interview_toggle(self) -> dict:
        if self._interview_running:
            self._stop_interview()
        else:
            self._start_interview()
        return {"ok": True}

    def _start_interview(self):
        if not AUDIO_AVAILABLE:
            self.notify("interview_status", {"title": "Indisponível", "detail": "Recurso só no Windows."})
            return
        if not self.config.get("api_key"):
            self.notify("interview_status", {"title": "Erro", "detail": "Configure a API Key (⚙)."})
            return
        if self._audio_running:
            self._stop_audio()
        if self.running:
            self._stop()

        capture_mode = self.config.get("interview_capture_mode", "system")
        target_pid = int(self.config.get("interview_target_pid") or 0) or None
        if capture_mode == "application" and not target_pid:
            self.notify(
                "interview_status",
                {"title": "Erro", "detail": "Selecione um aplicativo com áudio."},
            )
            return

        device = self.config.get("interview_audio_device") or None
        self.notify("interview_status", {"title": "Iniciando...", "detail": "Carregando Whisper"})
        self._emit_state()

        def work():
            try:
                translator = self._make_translator(
                    self.config.get("interview_answer_language", "Português")
                )
                pipeline = AudioPipeline(
                    translator=translator,
                    device=device,
                    capture_mode=capture_mode,
                    target_pid=target_pid if capture_mode == "application" else None,
                    whisper_model=self.config.get("whisper_model", "tiny"),
                    compute_device=self.config.get("whisper_compute_device", "cpu"),
                    source_language=self.config.get("audio_source_language", "auto"),
                    streaming=bool(self.config.get("interview_streaming", True)),
                    mode="interview",
                    interview_context=self.config.get("interview_context", ""),
                    interview_type=self.config.get("interview_type", "Geral"),
                    answer_language=self.config.get("interview_answer_language", "Português"),
                    on_status=lambda msg: self.notify(
                        "interview_status", {"title": msg, "detail": ""}
                    ),
                    on_original=lambda text: self.notify("interview_question", {"text": text}),
                    on_translation=self._on_interview_answer,
                    on_translation_partial=lambda text: self.notify(
                        "interview_answer", {"text": text, "partial": True}
                    ),
                    on_error=lambda err: self.notify(
                        "interview_status", {"title": "Erro", "detail": str(err)[:120]}
                    ),
                )
                pipeline.start()
                self._interview_pipeline = pipeline
                self._interview_running = True
                self.notify("interview_status", {"title": "Ouvindo...", "detail": "Aguardando pergunta"})
                self._emit_state()
            except Exception as exc:
                log(f"Erro ao iniciar entrevista: {exc}\n{traceback.format_exc()}")
                self._interview_running = False
                self._interview_pipeline = None
                self.notify("interview_status", {"title": "Erro", "detail": str(exc)[:120]})
                self._emit_state()

        threading.Thread(target=work, daemon=True).start()

    def _on_interview_answer(self, text: str):
        self.notify("interview_answer", {"text": text, "partial": False})
        self._interview_history.append({"answer": text})
        if len(self._interview_history) > 20:
            self._interview_history = self._interview_history[-20:]
        self._emit_state()

    def _stop_interview(self):
        self._interview_running = False
        if self._interview_pipeline:
            try:
                self._interview_pipeline.stop()
            except Exception:
                pass
            self._interview_pipeline = None
        self.notify("interview_status", {"title": "Parado", "detail": ""})
        self._emit_state()

    # ── Hotkeys ─────────────────────────────────────────────────────────

    def _normalize_hotkey(self, hotkey: str) -> str:
        return (hotkey or "").strip().lower()

    def _register_hotkey(self, hotkey: str, callback):
        hk = self._normalize_hotkey(hotkey)
        if not hk or sys.platform != "win32":
            return
        try:
            keyboard.add_hotkey(hk, callback, suppress=False)
        except Exception as exc:
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
        self._register_hotkey(
            self.config.get("hotkey_audio", "f12"),
            lambda: self._run_hotkey(self.audio_toggle),
        )
        self._hotkeys_registered = True

    def shutdown(self):
        self.running = False
        if self._audio_running:
            self._stop_audio()
        if self._interview_running:
            self._stop_interview()
        if sys.platform == "win32":
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
