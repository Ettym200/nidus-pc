import sys
import ctypes
import subprocess
import os

# Re-lança como admin se necessário (para hotkeys funcionarem em jogos)
def _is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _setup_runtime():
    app_dir = _app_dir()
    os.chdir(app_dir)
    return app_dir


def _relaunch_as_admin():
    exe = sys.executable
    params = subprocess.list2cmdline(sys.argv[1:])
    cwd = os.path.dirname(os.path.abspath(exe))
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, cwd, 1)
    if ret > 32:
        sys.exit(0)


APP_DIR = _setup_runtime()

_DEBUG = os.environ.get("NIDUS_DEBUG") == "1" or "--debug" in sys.argv

if not _is_admin() and not _DEBUG:
    _relaunch_as_admin()

if _DEBUG:
    print("[Nidus] Modo debug — sem elevação de admin. Atalhos globais podem não funcionar.")
    print(f"[Nidus] Diretório: {APP_DIR}")

import tkinter as tk
import threading
import queue
import json
import keyboard
import mouse
import customtkinter as ctk
from PIL import Image
from src.capture import ScreenCapture
from src.translator import Translator, KNOWN_PROVIDERS
from src.overlay import Overlay
from src.audio_pipeline import AudioPipeline
from src.speech_to_text import WHISPER_MODELS, COMPUTE_OPTIONS

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
from src import ui_theme as theme
from src.updater import check_update

CONFIG_FILE = os.path.join(APP_DIR, "config.json")
APP_VERSION = "1.0.5"
RELEASES_URL = "https://github.com/Ettym200/nidus-pc/releases/latest"

DEFAULT_CONFIG = {
    "api_key": "",
    "api_provider": "openrouter",
    "custom_base_url": "",
    "model": "",
    "target_language": "Português",
    "region": None,
    "profiles": {},
    "capture_interval": 1.5,
    "hotkey_region": "f9",
    "hotkey_translate": "f10",
    "skipped_update_version": "",
    "audio_device": "",
    "audio_capture_mode": "system",
    "audio_target_pid": 0,
    "whisper_model": "tiny",
    "whisper_compute_device": "cpu",
    "audio_source_language": "auto",
    "audio_streaming": True,
    "hotkey_audio": "f12",
    "interview_context": "",
    "interview_type": "Geral",
    "interview_answer_language": "Português",
    "interview_streaming": True,
    "interview_capture_mode": "system",
    "interview_target_pid": 0,
    "interview_audio_device": "",
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return {**DEFAULT_CONFIG, **data}
    return DEFAULT_CONFIG.copy()


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


PROVIDER_LIST = list(KNOWN_PROVIDERS.keys())

MOUSE_HOTKEY_PREFIX = "mouse:"
MOUSE_BUTTON_MAP = {1: "left", 2: "middle", 3: "right", 4: "x", 5: "x2"}
MOUSE_DISPLAY = {
    "left": "Botão Esquerdo",
    "middle": "Botão Meio",
    "right": "Botão Direito",
    "x": "Mouse 4",
    "x2": "Mouse 5",
}
MOUSE_TO_LIB = {
    "left": mouse.LEFT,
    "middle": mouse.MIDDLE,
    "right": mouse.RIGHT,
    "x": mouse.X,
    "x2": mouse.X2,
}

PROVIDER_HINTS = {
    "openai":     "Modelo: gpt-4o-mini  |  openai.com",
    "anthropic":  "Modelo: claude-haiku  |  anthropic.com",
    "openrouter": "Base URL já configurada  |  openrouter.ai",
    "groq":       "Modelo padrão: llama-4-scout (com visão)  |  groq.com  — GRÁTIS",
    "custom":     "Informe a Base URL abaixo (ex: http://localhost:11434/v1)",
}


def _resource_path(name: str) -> str:
    if os.path.isabs(name) and os.path.exists(name):
        return name
    rel = os.path.join("assets", name)
    base = getattr(sys, "_MEIPASS", APP_DIR)
    bundled = os.path.join(base, rel)
    if os.path.exists(bundled):
        return bundled
    local = os.path.join(APP_DIR, rel)
    if os.path.exists(local):
        return local
    return bundled


def _set_window_icon(window):
    ico = _resource_path("icon.ico")
    png = _resource_path("icon.png")
    for setter in (
        lambda: window.iconbitmap(default=ico),
        lambda: window.wm_iconbitmap(ico),
        lambda: window.tk.call("wm", "iconbitmap", window._w, ico),
    ):
        try:
            setter()
            return
        except Exception:
            pass
    try:
        icon = tk.PhotoImage(file=png)
        window.iconphoto(True, icon)
        window._nidus_icon = icon
    except Exception:
        pass


class App(ctk.CTk):
    LANGUAGES = [
        "Português", "Inglês", "Espanhol", "Japonês", "Francês", "Alemão",
        "Italiano", "Coreano", "Chinês Simplificado", "Chinês Tradicional",
        "Russo", "Árabe", "Hindi", "Turco", "Polonês", "Holandês",
        "Sueco", "Norueguês", "Dinamarquês", "Finlandês", "Grego",
        "Hebraico", "Tailandês", "Vietnamita", "Indonésio", "Malaio",
        "Romeno", "Húngaro", "Tcheco", "Eslovaco", "Croata", "Ucraniano",
    ]
    AUDIO_SOURCE_LANGS = [
        "auto", "Inglês", "Japonês", "Espanhol", "Português", "Francês",
        "Alemão", "Coreano", "Chinês", "Russo",
    ]
    AUDIO_SOURCE_MAP = {
        "auto": "auto",
        "Inglês": "en", "Japonês": "ja", "Espanhol": "es", "Português": "pt",
        "Francês": "fr", "Alemão": "de", "Coreano": "ko", "Chinês": "zh", "Russo": "ru",
    }

    def __init__(self):
        theme.setup_theme()
        super().__init__()
        self.title("Nidus")
        self.geometry("920x720")
        self.minsize(880, 620)
        self.configure(fg_color=theme.BG)
        _set_window_icon(self)
        self.after(200, lambda: _set_window_icon(self))

        self.config = load_config()
        self.running = False
        self.audio_running = False
        self.interview_running = False
        self.overlay = None
        self.capture = None
        self.translator = None
        self.audio_pipeline = None
        self.interview_pipeline = None
        self._ui_queue: queue.Queue = queue.Queue()
        self._interview_answer_cache = ""

        self._build_ui()
        self._poll_ui_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._register_hotkeys()
        self._on_mode_change()
        self.after(1500, self._check_updates_async)

    def _poll_ui_queue(self):
        while True:
            try:
                fn, args, kwargs = self._ui_queue.get_nowait()
                fn(*args, **kwargs)
            except queue.Empty:
                break
            except Exception as exc:
                from src.debug_log import log
                log(f"Erro na UI: {exc}")
        self.after(30, self._poll_ui_queue)

    def _ui(self, fn, *args, **kwargs):
        self._ui_queue.put((fn, args, kwargs))

    def _on_close(self):
        try:
            if self.audio_running:
                self._stop_audio()
            if self.interview_running:
                self._stop_interview()
        finally:
            self.destroy()

    def _check_updates_async(self):
        def _run():
            skipped = self.config.get("skipped_update_version", "")
            info = check_update(APP_VERSION, skipped)
            if info:
                self.after(0, lambda: self._show_update_dialog(info))
        threading.Thread(target=_run, daemon=True).start()

    def _show_update_dialog(self, info):
        win = ctk.CTkToplevel(self)
        win.title("Atualização disponível")
        win.geometry("420x280")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(fg_color=theme.BG)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(
            win, text="Nova versão disponível!",
            font=(theme.FONT, 16, "bold"), text_color=theme.ACCENT,
        ).pack(pady=(20, 6))

        ctk.CTkLabel(
            win,
            text=f"Você está na v{APP_VERSION}  →  v{info['version']} já está no ar.",
            font=(theme.FONT, 11), text_color=theme.TEXT,
            wraplength=380,
        ).pack(pady=(0, 8))

        notes = info.get("notes", "")
        if notes:
            preview = notes if len(notes) <= 200 else notes[:200] + "..."
            ctk.CTkLabel(
                win, text=preview,
                font=(theme.FONT, 10), text_color=theme.TEXT_MUTED,
                wraplength=380, justify="left",
            ).pack(pady=(0, 12), padx=20)

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(8, 20))

        def download():
            import webbrowser
            webbrowser.open(info["url"])

        def later():
            self.config["skipped_update_version"] = info["tag"]
            save_config(self.config)
            win.destroy()

        theme.primary_btn(btn_row, "Baixar agora", download).pack(
            side="left", fill="x", expand=True, padx=(0, 6),
        )
        theme.secondary_btn(btn_row, "Depois", later).pack(side="left", fill="x", expand=True)

    # ── UI principal ─────────────────────────────────────────────────────

    def _build_ui(self):
        self.tabs = ctk.CTkTabview(
            self, fg_color=theme.BG,
            segmented_button_fg_color=theme.SURFACE,
            segmented_button_selected_color=theme.SECONDARY,
            segmented_button_selected_hover_color="#1a4a80",
            segmented_button_unselected_color=theme.SURFACE,
            segmented_button_unselected_hover_color=theme.SURFACE_ALT,
            text_color=theme.TEXT_DIM,
        )
        self.tabs.pack(fill="both", expand=True, padx=12, pady=12)

        tab_game = self.tabs.add("Jogo")
        tab_live = self.tabs.add("Live")
        tab_interview = self.tabs.add("Entrevista")
        tab_text = self.tabs.add("Traduzir Texto")

        self._build_game_tab(tab_game)
        self._build_live_tab(tab_live)
        self._build_interview_tab(tab_interview)
        self._build_text_tab(tab_text)

    def _build_game_tab(self, parent):
        parent.configure(fg_color=theme.BG)
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, fg_color=theme.BG, corner_radius=0)
        scroll.grid(row=0, column=0, sticky="nsew")
        f = scroll
        pad = {"padx": 4, "pady": 6}

        title_row = ctk.CTkFrame(f, fg_color="transparent")
        title_row.pack(fill="x", pady=(12, 4))
        ctk.CTkLabel(
            title_row, text="Nidus",
            font=(theme.FONT, 18, "bold"), text_color=theme.ACCENT,
        ).pack(side="left")
        ctk.CTkLabel(
            title_row, text=f"v{APP_VERSION}",
            font=(theme.FONT, 10), text_color=theme.TEXT_MUTED,
        ).pack(side="left", padx=(8, 0), pady=(4, 0))
        ctk.CTkLabel(
            f, text="Tradução simultânea de legendas de jogos",
            font=(theme.FONT, 11), text_color=theme.TEXT_MUTED,
        ).pack(pady=(0, 12))

        # ── Configuração da API (sempre visível) ───────────────────────
        frame_api = theme.card(f)
        frame_api.pack(fill="x", **pad)
        frame_api.columnconfigure(1, weight=1)
        theme.section_title(frame_api, "Configuração da API").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 8),
        )

        theme.field_label(frame_api, "Provedor:").grid(
            row=1, column=0, sticky="w", padx=14, pady=4,
        )
        self.provider_var = tk.StringVar(value=self.config["api_provider"])
        theme.combo(
            frame_api, PROVIDER_LIST, variable=self.provider_var,
            command=self._on_provider_change, width=200,
        ).grid(row=1, column=1, sticky="w", padx=14, pady=4)

        self.hint_var = tk.StringVar(value=PROVIDER_HINTS.get(self.config["api_provider"], ""))
        ctk.CTkLabel(
            frame_api, textvariable=self.hint_var,
            font=(theme.FONT, 10), text_color=theme.TEXT_MUTED,
            anchor="w", wraplength=400, justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 6))

        theme.field_label(frame_api, "API Key:").grid(row=3, column=0, sticky="w", padx=14, pady=4)
        self.api_key_var = tk.StringVar(value=self.config["api_key"])
        theme.entry(frame_api, textvariable=self.api_key_var, show="*", width=300).grid(
            row=3, column=1, sticky="ew", padx=14, pady=4,
        )

        theme.field_label(frame_api, "Base URL:").grid(row=4, column=0, sticky="w", padx=14, pady=4)
        self.base_url_var = tk.StringVar(value=self.config["custom_base_url"])
        self.base_url_entry = theme.entry(frame_api, textvariable=self.base_url_var, width=300)
        self.base_url_entry.grid(row=4, column=1, sticky="ew", padx=14, pady=4)

        theme.field_label(frame_api, "Modelo:").grid(row=5, column=0, sticky="w", padx=14, pady=4)
        self.model_var = tk.StringVar(value=self.config["model"])
        theme.entry(frame_api, textvariable=self.model_var, width=300).grid(
            row=5, column=1, sticky="ew", padx=14, pady=4,
        )
        theme.hint_label(frame_api, "(deixe vazio para usar o padrão do provedor)").grid(
            row=6, column=1, sticky="w", padx=14,
        )

        theme.primary_btn(
            frame_api, "Gerenciar Keys", self._open_keys,
            height=36, font=(theme.FONT, 11, "bold"),
        ).grid(row=7, column=0, columnspan=2, pady=(10, 14), padx=14, sticky="ew")

        self._update_url_state()

        # ── Tradução ─────────────────────────────────────────────────────
        frame_trans = theme.card(f)
        frame_trans.pack(fill="x", **pad)

        theme.section_title(frame_trans, "Tradução").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 8),
        )

        theme.field_label(frame_trans, "Traduzir para:").grid(
            row=1, column=0, sticky="w", padx=14, pady=4,
        )
        self.lang_var = tk.StringVar(value=self.config["target_language"])
        theme.combo(frame_trans, self.LANGUAGES, variable=self.lang_var, width=220).grid(
            row=1, column=1, sticky="w", padx=14, pady=4,
        )

        theme.field_label(frame_trans, "Modo:").grid(row=2, column=0, sticky="w", padx=14, pady=4)
        frame_mode = ctk.CTkFrame(frame_trans, fg_color="transparent")
        frame_mode.grid(row=2, column=1, sticky="w", padx=14, pady=4)
        self.mode_var = tk.StringVar(value=self.config.get("mode", "once"))
        ctk.CTkRadioButton(
            frame_mode, text="Traduzir uma vez", variable=self.mode_var, value="once",
            command=self._on_mode_change,
            font=(theme.FONT, 11), text_color=theme.TEXT,
            fg_color=theme.ACCENT, hover_color="#c73a52",
        ).pack(side="left", padx=(0, 12))
        ctk.CTkRadioButton(
            frame_mode, text="Contínuo", variable=self.mode_var, value="continuous",
            command=self._on_mode_change,
            font=(theme.FONT, 11), text_color=theme.TEXT,
            fg_color=theme.ACCENT, hover_color="#c73a52",
        ).pack(side="left")

        self.interval_frame = ctk.CTkFrame(frame_trans, fg_color="transparent")
        self.interval_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=4)
        theme.field_label(self.interval_frame, "Intervalo (s):").pack(side="left")
        self.interval_var = tk.DoubleVar(value=self.config["capture_interval"])
        ctk.CTkSlider(
            self.interval_frame, from_=0.5, to=5.0, number_of_steps=9,
            variable=self.interval_var,
            fg_color=theme.SURFACE_ALT, progress_color=theme.ACCENT,
            button_color=theme.ACCENT, button_hover_color="#c73a52",
            width=220,
        ).pack(side="left", padx=(8, 0), pady=4)

        # ── Região monitorada ────────────────────────────────────────────
        frame_region = theme.card(f)
        frame_region.pack(fill="x", **pad)

        theme.section_title(frame_region, "Região Monitorada").pack(
            anchor="w", padx=14, pady=(12, 6),
        )

        mon_row = ctk.CTkFrame(frame_region, fg_color="transparent")
        mon_row.pack(fill="x", padx=14, pady=(0, 6))
        theme.field_label(mon_row, "Monitor:").pack(side="left")
        self.monitor_var = tk.StringVar()
        self._monitors = self._get_monitors()
        mon_names = [
            f"Monitor {i+1}  ({m['width']}×{m['height']}  +{m['left']},+{m['top']})"
            for i, m in enumerate(self._monitors)
        ]
        saved_mon = self.config.get("monitor_index", 0)
        self.monitor_var.set(mon_names[min(saved_mon, len(mon_names) - 1)])
        theme.combo(mon_row, mon_names, variable=self.monitor_var, width=340).pack(
            side="left", padx=(8, 0),
        )

        region_row = ctk.CTkFrame(frame_region, fg_color="transparent")
        region_row.pack(fill="x", padx=14, pady=(0, 14))
        self.region_label = ctk.CTkLabel(
            region_row, text=self._region_text(),
            font=(theme.FONT, 10), text_color=theme.TEXT_MUTED,
        )
        self.region_label.pack(side="left")
        theme.secondary_btn(
            region_row, "Selecionar região", self._select_region, width=140,
        ).pack(side="right")

        # ── Atalhos ──────────────────────────────────────────────────────
        frame_hotkey = theme.card(f)
        frame_hotkey.pack(fill="x", **pad)
        frame_hotkey.columnconfigure(1, weight=1)

        theme.section_title(frame_hotkey, "Atalhos").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 8),
        )

        theme.field_label(frame_hotkey, "Selecionar região:").grid(
            row=1, column=0, sticky="w", padx=14, pady=4,
        )
        self.hotkey_region_var = tk.StringVar(value=self.config.get("hotkey_region", "f9"))
        self._make_hotkey_entry(frame_hotkey, self.hotkey_region_var, row=1)

        theme.field_label(frame_hotkey, "Traduzir agora:").grid(
            row=2, column=0, sticky="w", padx=14, pady=4,
        )
        self.hotkey_translate_var = tk.StringVar(value=self.config.get("hotkey_translate", "f10"))
        self._make_hotkey_entry(frame_hotkey, self.hotkey_translate_var, row=2)

        theme.field_label(frame_hotkey, "Mostrar/ocultar tradução:").grid(
            row=3, column=0, sticky="w", padx=14, pady=4,
        )
        self.hotkey_toggle_var = tk.StringVar(value=self.config.get("hotkey_toggle", "f11"))
        self._make_hotkey_entry(frame_hotkey, self.hotkey_toggle_var, row=3)

        theme.field_label(frame_hotkey, "Tradução por áudio (Live):").grid(
            row=4, column=0, sticky="w", padx=14, pady=4,
        )
        self.hotkey_audio_var = tk.StringVar(value=self.config.get("hotkey_audio", "f12"))
        self._make_hotkey_entry(frame_hotkey, self.hotkey_audio_var, row=4)

        theme.hint_label(
            frame_hotkey,
            "(clique no campo e pressione uma tecla ou botão do mouse)",
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 14))

        actions = ctk.CTkFrame(parent, fg_color=theme.SURFACE, corner_radius=theme.CORNER)
        actions.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        actions.columnconfigure(0, weight=1)

        status_row = ctk.CTkFrame(actions, fg_color="transparent")
        status_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))
        self.status_var = tk.StringVar(value="Parado")
        ctk.CTkLabel(
            status_row, textvariable=self.status_var,
            font=(theme.FONT, 11), text_color=theme.TEXT_DIM,
        ).pack(side="left")
        self.last_text_var = tk.StringVar(value="")
        ctk.CTkLabel(
            status_row, textvariable=self.last_text_var,
            font=(theme.FONT, 10, "italic"), text_color=theme.ACCENT,
            wraplength=520, justify="right",
        ).pack(side="right", fill="x", expand=True, padx=(12, 0))

        self.btn_start = theme.primary_btn(
            actions, "Iniciar Tradução", self._toggle, height=44,
        )
        self.btn_start.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 8))

        btn_row = ctk.CTkFrame(actions, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        btn_row.columnconfigure((0, 1, 2), weight=1)
        theme.secondary_btn(
            btn_row, "Salvar", self._save, height=34, font=(theme.FONT, 10),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        theme.secondary_btn(
            btn_row, "Como usar", self._open_help, height=34, font=(theme.FONT, 10),
        ).grid(row=0, column=1, sticky="ew", padx=4)
        theme.success_btn(
            btn_row, "Apoiar Pix", self._open_donation, height=34, font=(theme.FONT, 10),
        ).grid(row=0, column=2, sticky="ew", padx=(4, 0))

    def _build_live_tab(self, parent):
        parent.configure(fg_color=theme.BG)
        scroll = ctk.CTkScrollableFrame(parent, fg_color=theme.BG, corner_radius=0)
        scroll.pack(fill="both", expand=True)
        f = scroll
        pad = {"padx": 4, "pady": 6}

        ctk.CTkLabel(
            f, text="Tradução por áudio",
            font=(theme.FONT, 18, "bold"), text_color=theme.ACCENT,
        ).pack(pady=(12, 4))
        ctk.CTkLabel(
            f,
            text="Captura o áudio do sistema (lives, vídeos, chamadas) e exibe legendas traduzidas.",
            font=(theme.FONT, 11), text_color=theme.TEXT_MUTED, wraplength=460,
        ).pack(pady=(0, 8))

        if not AUDIO_AVAILABLE:
            ctk.CTkLabel(
                f,
                text="Disponível apenas no Windows com PyAudioWPatch instalado.",
                font=(theme.FONT, 11), text_color=theme.ACCENT, wraplength=460,
            ).pack(padx=16, pady=16)
            self.audio_status_var = tk.StringVar(value="Indisponível")
            self.audio_original_var = tk.StringVar(value="")
            self.audio_translation_var = tk.StringVar(value="")
            return

        theme.hint_label(
            f, "Configure a API Key na aba Jogo antes de iniciar.",
        ).pack(pady=(0, 8))

        frame_audio = theme.card(f)
        frame_audio.pack(fill="x", **pad)
        frame_audio.columnconfigure(1, weight=1)
        theme.section_title(frame_audio, "Áudio do sistema").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 8),
        )

        theme.field_label(frame_audio, "Capturar de:").grid(
            row=1, column=0, sticky="w", padx=14, pady=4,
        )
        mode_row = ctk.CTkFrame(frame_audio, fg_color="transparent")
        mode_row.grid(row=1, column=1, sticky="w", padx=14, pady=4)
        self.audio_capture_mode_var = tk.StringVar(
            value=self.config.get("audio_capture_mode", "system"),
        )
        for mode_id, mode_label in CAPTURE_MODES:
            ctk.CTkRadioButton(
                mode_row, text=mode_label, value=mode_id,
                variable=self.audio_capture_mode_var,
                command=self._on_audio_capture_mode_change,
                font=(theme.FONT, 11), text_color=theme.TEXT,
                fg_color=theme.ACCENT, hover_color="#c73a52",
            ).pack(side="left", padx=(0, 12))

        theme.hint_label(
            frame_audio,
            "Use 'Aplicativo' para traduzir só o navegador/jogo e ignorar Discord.",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 4))

        self._app_row = ctk.CTkFrame(frame_audio, fg_color="transparent")
        self._app_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=4)
        self._app_row.columnconfigure(1, weight=1)
        theme.field_label(self._app_row, "Aplicativo:").grid(
            row=0, column=0, sticky="w", pady=4,
        )
        app_pick = ctk.CTkFrame(self._app_row, fg_color="transparent")
        app_pick.grid(row=0, column=1, sticky="ew", pady=4)
        self.audio_app_var = tk.StringVar(value="")
        self.audio_app_combo = theme.combo(app_pick, [], variable=self.audio_app_var, width=260)
        self.audio_app_combo.pack(side="left")
        theme.secondary_btn(
            app_pick, "Atualizar", self._refresh_audio_apps, width=90,
        ).pack(side="left", padx=(8, 0))
        theme.hint_label(
            self._app_row,
            "Abra o app (ex.: Brave, Chrome) e clique Atualizar com áudio tocando.",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self._device_row = ctk.CTkFrame(frame_audio, fg_color="transparent")
        self._device_row.grid(row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=4)
        self._device_row.columnconfigure(1, weight=1)
        theme.field_label(self._device_row, "Dispositivo:").grid(
            row=0, column=0, sticky="w", pady=4,
        )
        dev_row = ctk.CTkFrame(self._device_row, fg_color="transparent")
        dev_row.grid(row=0, column=1, sticky="ew", pady=4)
        self.audio_device_var = tk.StringVar(value=self.config.get("audio_device", ""))
        self.audio_device_combo = theme.combo(dev_row, [], variable=self.audio_device_var, width=260)
        self.audio_device_combo.pack(side="left")
        theme.secondary_btn(dev_row, "Atualizar", self._refresh_audio_devices, width=90).pack(
            side="left", padx=(8, 0),
        )
        self._refresh_audio_devices()

        theme.field_label(frame_audio, "Idioma da fala:").grid(
            row=5, column=0, sticky="w", padx=14, pady=4,
        )
        self.audio_source_langs = self.AUDIO_SOURCE_LANGS
        self.audio_source_map = self.AUDIO_SOURCE_MAP
        saved_src = self.config.get("audio_source_language", "auto")
        src_display = next(
            (k for k, v in self.audio_source_map.items() if v == saved_src), "auto",
        )
        self.audio_source_var = tk.StringVar(value=src_display)
        theme.combo(
            frame_audio, self.audio_source_langs, variable=self.audio_source_var, width=220,
        ).grid(row=5, column=1, sticky="w", padx=14, pady=4)

        theme.field_label(frame_audio, "Modelo Whisper:").grid(
            row=6, column=0, sticky="w", padx=14, pady=4,
        )
        self.whisper_model_var = tk.StringVar(value=self.config.get("whisper_model", "base"))
        theme.combo(
            frame_audio, WHISPER_MODELS, variable=self.whisper_model_var, width=220,
        ).grid(row=6, column=1, sticky="w", padx=14, pady=4)
        theme.hint_label(
            frame_audio, "tiny/base = mais rápido | small/medium = mais preciso (baixa na 1ª vez)",
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 4))

        theme.field_label(frame_audio, "Processamento:").grid(
            row=8, column=0, sticky="w", padx=14, pady=4,
        )
        self.whisper_compute_var = tk.StringVar(
            value=self.config.get("whisper_compute_device", "auto"),
        )
        theme.combo(
            frame_audio, COMPUTE_OPTIONS, variable=self.whisper_compute_var, width=220,
        ).grid(row=8, column=1, sticky="w", padx=14, pady=4)
        theme.hint_label(
            frame_audio, "cpu = estável | auto/cuda = GPU NVIDIA (precisa drivers CUDA)",
        ).grid(row=9, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 4))

        theme.field_label(frame_audio, "Traduzir para:").grid(
            row=10, column=0, sticky="w", padx=14, pady=4,
        )
        self.audio_lang_var = tk.StringVar(value=self.config.get("target_language", "Português"))
        theme.combo(frame_audio, self.LANGUAGES, variable=self.audio_lang_var, width=220).grid(
            row=10, column=1, sticky="w", padx=14, pady=4,
        )

        stream_row = ctk.CTkFrame(frame_audio, fg_color="transparent")
        stream_row.grid(row=11, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 14))
        self.audio_streaming_var = tk.BooleanVar(value=self.config.get("audio_streaming", True))
        ctk.CTkCheckBox(
            stream_row, text="Tradução em streaming (texto aparece aos poucos)",
            variable=self.audio_streaming_var,
            font=(theme.FONT, 11), text_color=theme.TEXT,
            fg_color=theme.ACCENT, hover_color="#c73a52",
        ).pack(side="left")

        self.audio_status_var = tk.StringVar(value="Parado")
        ctk.CTkLabel(
            f, textvariable=self.audio_status_var,
            font=(theme.FONT, 11), text_color=theme.TEXT_DIM,
        ).pack(pady=(8, 0))

        self.audio_original_var = tk.StringVar(value="")
        ctk.CTkLabel(
            f, textvariable=self.audio_original_var,
            font=(theme.FONT, 10), text_color=theme.TEXT_MUTED, wraplength=460, justify="left",
        ).pack(pady=(2, 0))

        self.audio_translation_var = tk.StringVar(value="")
        ctk.CTkLabel(
            f, textvariable=self.audio_translation_var,
            font=(theme.FONT, 11, "italic"), text_color=theme.ACCENT, wraplength=460, justify="left",
        ).pack(pady=(2, 8))

        self.btn_audio_start = theme.primary_btn(
            f, "Iniciar tradução por áudio", self._toggle_audio, height=48,
        )
        self.btn_audio_start.pack(fill="x", padx=4, pady=(8, 16))

        self._audio_apps: list[dict] = []
        self._refresh_audio_apps()
        self._on_audio_capture_mode_change()

    INTERVIEW_TYPES = ["Geral", "Técnica", "Comportamental", "RH / Cultura"]

    def _build_interview_tab(self, parent):
        parent.configure(fg_color=theme.BG)
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            header, text="Modo Entrevista",
            font=(theme.FONT, 14, "bold"), text_color=theme.ACCENT,
        ).pack(anchor="w")
        theme.hint_label(
            header,
            "Ouve o entrevistador e sugere o que você deve responder.",
        ).pack(anchor="w")

        if not AUDIO_AVAILABLE:
            ctk.CTkLabel(
                parent,
                text="Disponível apenas no Windows com PyAudioWPatch instalado.",
                font=(theme.FONT, 11), text_color=theme.ACCENT, wraplength=460,
            ).grid(row=1, column=0, padx=16, pady=16)
            self.interview_status_var = tk.StringVar(value="Indisponível")
            return

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(body, fg_color=theme.BG, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        pad = {"padx": 2, "pady": 4}

        theme.hint_label(
            left, "Configure a API Key na aba Jogo antes de iniciar.",
        ).pack(anchor="w", pady=(0, 6))

        frame_profile = theme.card(left)
        frame_profile.pack(fill="x", **pad)
        frame_profile.columnconfigure(0, weight=1)
        theme.section_title(frame_profile, "Seu perfil").grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 4),
        )
        self.interview_context_box = ctk.CTkTextbox(
            frame_profile, height=72, fg_color=theme.SURFACE_ALT, text_color=theme.TEXT,
            font=(theme.FONT, 11), corner_radius=theme.CORNER_SM,
            border_width=1, border_color=theme.BORDER,
        )
        self.interview_context_box.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        saved_ctx = self.config.get("interview_context", "")
        if saved_ctx:
            self.interview_context_box.insert("1.0", saved_ctx)

        frame_audio = theme.card(left)
        frame_audio.pack(fill="x", **pad)
        frame_audio.columnconfigure(1, weight=1)
        theme.section_title(frame_audio, "Ouvir de").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6),
        )

        theme.field_label(frame_audio, "Capturar de:").grid(
            row=1, column=0, sticky="w", padx=14, pady=4,
        )
        iv_mode_row = ctk.CTkFrame(frame_audio, fg_color="transparent")
        iv_mode_row.grid(row=1, column=1, sticky="w", padx=14, pady=4)
        self.interview_capture_mode_var = tk.StringVar(
            value=self.config.get("interview_capture_mode", "system"),
        )
        for mode_id, mode_label in CAPTURE_MODES:
            ctk.CTkRadioButton(
                iv_mode_row, text=mode_label, value=mode_id,
                variable=self.interview_capture_mode_var,
                command=self._on_interview_capture_mode_change,
                font=(theme.FONT, 11), text_color=theme.TEXT,
                fg_color=theme.ACCENT, hover_color="#c73a52",
            ).pack(side="left", padx=(0, 10))

        self._interview_app_row = ctk.CTkFrame(frame_audio, fg_color="transparent")
        self._interview_app_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=4)
        self._interview_app_row.columnconfigure(1, weight=1)
        theme.field_label(self._interview_app_row, "Aplicativo:").grid(
            row=0, column=0, sticky="w", pady=4,
        )
        iv_app_pick = ctk.CTkFrame(self._interview_app_row, fg_color="transparent")
        iv_app_pick.grid(row=0, column=1, sticky="ew", pady=4)
        self.interview_app_var = tk.StringVar(value="")
        self.interview_app_combo = theme.combo(
            iv_app_pick, [], variable=self.interview_app_var, width=180,
        )
        self.interview_app_combo.pack(side="left", fill="x", expand=True)
        theme.secondary_btn(
            iv_app_pick, "Atualizar", self._refresh_interview_apps, width=80,
        ).pack(side="left", padx=(6, 0))

        self._interview_device_row = ctk.CTkFrame(frame_audio, fg_color="transparent")
        self._interview_device_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=4)
        self._interview_device_row.columnconfigure(1, weight=1)
        theme.field_label(self._interview_device_row, "Dispositivo:").grid(
            row=0, column=0, sticky="w", pady=4,
        )
        iv_dev_row = ctk.CTkFrame(self._interview_device_row, fg_color="transparent")
        iv_dev_row.grid(row=0, column=1, sticky="ew", pady=4)
        saved_dev = self.config.get("interview_audio_device", "")
        self.interview_device_var = tk.StringVar(
            value=saved_dev if saved_dev else "(Padrão do sistema)",
        )
        self.interview_device_combo = theme.combo(
            iv_dev_row, [], variable=self.interview_device_var, width=180,
        )
        self.interview_device_combo.pack(side="left", fill="x", expand=True)
        theme.secondary_btn(
            iv_dev_row, "Atualizar", self._refresh_interview_devices, width=80,
        ).pack(side="left", padx=(6, 0))
        self._refresh_interview_devices()

        theme.field_label(frame_audio, "Whisper:").grid(row=4, column=0, sticky="w", padx=14, pady=4)
        self.interview_whisper_var = tk.StringVar(value=self.config.get("whisper_model", "tiny"))
        theme.combo(
            frame_audio, WHISPER_MODELS, variable=self.interview_whisper_var, width=160,
        ).grid(row=4, column=1, sticky="w", padx=14, pady=4)

        theme.field_label(frame_audio, "CPU/GPU:").grid(row=5, column=0, sticky="w", padx=14, pady=4)
        self.interview_compute_var = tk.StringVar(
            value=self.config.get("whisper_compute_device", "cpu"),
        )
        theme.combo(
            frame_audio, COMPUTE_OPTIONS, variable=self.interview_compute_var, width=160,
        ).grid(row=5, column=1, sticky="w", padx=14, pady=(4, 12))

        frame_opts = theme.card(left)
        frame_opts.pack(fill="x", **pad)
        frame_opts.columnconfigure(1, weight=1)
        theme.section_title(frame_opts, "Configuração").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6),
        )

        theme.field_label(frame_opts, "Tipo:").grid(row=1, column=0, sticky="w", padx=14, pady=4)
        self.interview_type_var = tk.StringVar(value=self.config.get("interview_type", "Geral"))
        theme.combo(
            frame_opts, self.INTERVIEW_TYPES, variable=self.interview_type_var, width=160,
        ).grid(row=1, column=1, sticky="w", padx=14, pady=4)

        theme.field_label(frame_opts, "Respostas:").grid(row=2, column=0, sticky="w", padx=14, pady=4)
        self.interview_answer_lang_var = tk.StringVar(
            value=self.config.get("interview_answer_language", "Português"),
        )
        theme.combo(
            frame_opts, self.LANGUAGES, variable=self.interview_answer_lang_var, width=160,
        ).grid(row=2, column=1, sticky="w", padx=14, pady=4)

        theme.field_label(frame_opts, "Fala:").grid(row=3, column=0, sticky="w", padx=14, pady=4)
        saved_src = self.config.get("audio_source_language", "auto")
        src_display = next(
            (k for k, v in self.AUDIO_SOURCE_MAP.items() if v == saved_src), "auto",
        )
        self.interview_source_var = tk.StringVar(value=src_display)
        theme.combo(
            frame_opts, self.AUDIO_SOURCE_LANGS, variable=self.interview_source_var, width=160,
        ).grid(row=3, column=1, sticky="w", padx=14, pady=4)

        self.interview_streaming_var = tk.BooleanVar(
            value=self.config.get("interview_streaming", True),
        )
        ctk.CTkCheckBox(
            frame_opts, text="Streaming",
            variable=self.interview_streaming_var,
            font=(theme.FONT, 11), text_color=theme.TEXT,
            fg_color=theme.ACCENT, hover_color="#c73a52",
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 12))

        self._interview_apps: list[dict] = []
        self._refresh_interview_apps()
        self._on_interview_capture_mode_change()

        right = theme.card(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1)

        self.interview_status_var = tk.StringVar(value="Parado")
        ctk.CTkLabel(
            right, textvariable=self.interview_status_var,
            font=(theme.FONT, 11), text_color=theme.TEXT_DIM,
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        ctk.CTkLabel(
            right, text="Pergunta do entrevistador",
            font=(theme.FONT, 10), text_color=theme.TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(4, 2))

        self.interview_question_box = ctk.CTkTextbox(
            right, height=72, fg_color=theme.SURFACE_ALT, text_color=theme.TEXT,
            font=(theme.FONT, 12), corner_radius=theme.CORNER_SM,
            border_width=1, border_color=theme.BORDER,
        )
        self.interview_question_box.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        self.interview_question_box.configure(state="disabled")

        ans_hdr = ctk.CTkFrame(right, fg_color="transparent")
        ans_hdr.grid(row=3, column=0, sticky="ew", padx=14, pady=(4, 2))
        ans_hdr.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            ans_hdr, text="O que você deve responder",
            font=(theme.FONT, 11, "bold"), text_color=theme.ACCENT,
        ).grid(row=0, column=0, sticky="w")
        theme.secondary_btn(
            ans_hdr, "Copiar", self._copy_interview_answer, width=80, height=26,
            font=(theme.FONT, 10),
        ).grid(row=0, column=1, sticky="e")

        self.interview_answer_box = ctk.CTkTextbox(
            right, fg_color=theme.BG, text_color="#ffffff",
            font=(theme.FONT, 14), corner_radius=theme.CORNER_SM,
            border_width=2, border_color=theme.ACCENT,
            wrap="word",
        )
        self.interview_answer_box.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 12))
        self.interview_answer_box.configure(state="disabled")

        footer = ctk.CTkFrame(parent, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 10))
        footer.columnconfigure(0, weight=1)

        hist_hdr = ctk.CTkFrame(footer, fg_color="transparent")
        hist_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        ctk.CTkLabel(
            hist_hdr, text="Histórico da sessão",
            font=(theme.FONT, 10), text_color=theme.TEXT_MUTED,
        ).pack(side="left")
        theme.ghost_btn(
            hist_hdr, "Limpar", self._clear_interview_history, width=70, height=26,
            font=(theme.FONT, 10),
        ).pack(side="right")

        self.interview_history_box = ctk.CTkTextbox(
            footer, height=64, fg_color=theme.SURFACE, text_color=theme.TEXT_DIM,
            font=(theme.FONT, 10), corner_radius=theme.CORNER_SM,
            border_width=1, border_color=theme.BORDER,
        )
        self.interview_history_box.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.interview_history_box.configure(state="disabled")

        self.btn_interview_start = theme.primary_btn(
            footer, "Iniciar modo entrevista", self._toggle_interview, height=44,
        )
        self.btn_interview_start.grid(row=2, column=0, sticky="ew")

    def _set_textbox(self, box: ctk.CTkTextbox, text: str, readonly: bool = True):
        try:
            current = box.get("1.0", "end-1c")
            if current == text:
                return
            box.configure(state="normal")
            box.delete("1.0", "end")
            if text:
                box.insert("1.0", text)
            if readonly:
                box.configure(state="disabled")
        except Exception as exc:
            from src.debug_log import log
            log(f"Erro ao atualizar textbox: {exc}")

    def _copy_interview_answer(self):
        text = self.interview_answer_box.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.interview_status_var.set("Resposta copiada!")

    def _clear_interview_history(self):
        self._set_textbox(self.interview_history_box, "")

    def _append_interview_history(self, question: str, answer: str):
        try:
            self.interview_history_box.configure(state="normal")
            if self.interview_history_box.get("1.0", "end").strip():
                self.interview_history_box.insert("end", "\n\n")
            self.interview_history_box.insert(
                "end",
                f"P: {question}\nR: {answer}",
            )
            self.interview_history_box.see("end")
            self.interview_history_box.configure(state="disabled")
        except Exception as exc:
            from src.debug_log import log
            log(f"Erro ao atualizar histórico: {exc}")

    def _on_audio_capture_mode_change(self):
        mode = self.audio_capture_mode_var.get()
        if mode == "application":
            self._app_row.grid()
            self._device_row.grid_remove()
        else:
            self._app_row.grid_remove()
            self._device_row.grid()

    def _on_interview_capture_mode_change(self):
        mode = self.interview_capture_mode_var.get()
        if mode == "application":
            self._interview_app_row.grid()
            self._interview_device_row.grid_remove()
        else:
            self._interview_app_row.grid_remove()
            self._interview_device_row.grid()

    def _refresh_interview_apps(self):
        if not AUDIO_AVAILABLE or not is_app_capture_supported():
            return
        self._interview_apps = list_audio_applications()
        labels = [a["label"] for a in self._interview_apps]
        if not labels:
            labels = ["(Nenhum app com áudio — abra a chamada e clique Atualizar)"]
        self.interview_app_combo.configure(values=labels)
        saved_pid = self.config.get("interview_target_pid", 0)
        match = next((a for a in self._interview_apps if a["pid"] == saved_pid), None)
        if match:
            self.interview_app_var.set(match["label"])
        elif self._interview_apps:
            self.interview_app_var.set(self._interview_apps[0]["label"])
        else:
            self.interview_app_var.set(labels[0])

    def _refresh_interview_devices(self):
        if not AUDIO_AVAILABLE:
            return
        devices = ["(Padrão do sistema)"] + list_output_devices()
        self.interview_device_combo.configure(values=devices)
        current = self.config.get("interview_audio_device", "")
        if not current:
            self.interview_device_var.set("(Padrão do sistema)")
        elif current in devices:
            self.interview_device_var.set(current)
        elif devices:
            self.interview_device_var.set(devices[0])

    def _selected_interview_app_pid(self) -> int | None:
        label = self.interview_app_var.get()
        for app in self._interview_apps:
            if app["label"] == label:
                return app["pid"]
        return None

    def _refresh_audio_apps(self):
        if not AUDIO_AVAILABLE or not is_app_capture_supported():
            return
        self._audio_apps = list_audio_applications()
        labels = [a["label"] for a in self._audio_apps]
        if not labels:
            labels = ["(Nenhum app com áudio — abra o navegador e clique Atualizar)"]
        self.audio_app_combo.configure(values=labels)
        saved_pid = self.config.get("audio_target_pid", 0)
        match = next((a for a in self._audio_apps if a["pid"] == saved_pid), None)
        if match:
            self.audio_app_var.set(match["label"])
        elif self._audio_apps:
            self.audio_app_var.set(self._audio_apps[0]["label"])
        else:
            self.audio_app_var.set(labels[0])

    def _selected_audio_app_pid(self) -> int | None:
        label = self.audio_app_var.get()
        for app in self._audio_apps:
            if app["label"] == label:
                return app["pid"]
        return None

    def _build_text_tab(self, parent):
        parent.configure(fg_color=theme.BG)

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 6))

        theme.field_label(top, "Traduzir para:").pack(side="left")
        self.text_lang_var = tk.StringVar(value=self.config.get("target_language", "Português"))
        theme.combo(top, self.LANGUAGES, variable=self.text_lang_var, width=180).pack(
            side="left", padx=(6, 12),
        )

        self.btn_translate_text = theme.primary_btn(
            top, "Traduzir", self._do_text_translate, height=34, width=100,
            font=(theme.FONT, 11, "bold"),
        )
        self.btn_translate_text.pack(side="left")

        self.text_status_var = tk.StringVar(value="")
        ctk.CTkLabel(
            top, textvariable=self.text_status_var,
            font=(theme.FONT, 10), text_color=theme.TEXT_DIM,
        ).pack(side="left", padx=10)

        theme.ghost_btn(
            top, "Limpar", lambda: self.text_input.delete("1.0", "end"), width=70,
        ).pack(side="right")

        paned = tk.PanedWindow(
            parent, orient="vertical", bg=theme.BORDER,
            sashwidth=5, sashrelief="flat", sashpad=0,
        )
        paned.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        frame_in = tk.Frame(paned, bg=theme.SURFACE)
        paned.add(frame_in, minsize=80)

        ctk.CTkLabel(
            frame_in, text="Texto original",
            font=(theme.FONT, 10), text_color=theme.TEXT_MUTED, bg_color=theme.SURFACE,
        ).pack(anchor="w", padx=10, pady=(8, 2))

        self.text_input = ctk.CTkTextbox(
            frame_in, fg_color=theme.SURFACE_ALT, text_color=theme.TEXT,
            font=(theme.FONT, 12), corner_radius=theme.CORNER_SM,
            border_width=1, border_color=theme.BORDER,
        )
        self.text_input.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        frame_out = tk.Frame(paned, bg=theme.SURFACE_ALT)
        paned.add(frame_out, minsize=80)

        out_hdr = tk.Frame(frame_out, bg=theme.SURFACE_ALT)
        out_hdr.pack(fill="x", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            out_hdr, text="Tradução",
            font=(theme.FONT, 10), text_color=theme.TEXT_MUTED, bg_color=theme.SURFACE_ALT,
        ).pack(side="left")
        theme.secondary_btn(
            out_hdr, "Copiar", self._copy_text_result, width=80, height=26,
            font=(theme.FONT, 10),
        ).pack(side="right")

        self.text_output = ctk.CTkTextbox(
            frame_out, fg_color=theme.BG, text_color=theme.ACCENT,
            font=(theme.FONT, 12), corner_radius=theme.CORNER_SM,
            border_width=1, border_color=theme.BORDER,
        )
        self.text_output.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.text_output.configure(state="disabled")

    # ── Tradução de texto ────────────────────────────────────────────────

    def _do_text_translate(self):
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            return
        api_key = self.api_key_var.get().strip() or self.config.get("api_key", "")
        if not api_key:
            self.text_status_var.set("Configure a API Key na aba Jogo")
            return

        self.btn_translate_text.configure(state="disabled", text="Traduzindo...", fg_color=theme.DISABLED)
        self.text_status_var.set("Traduzindo...")

        def _run():
            try:
                t = Translator(
                    api_key=api_key,
                    provider=self.provider_var.get(),
                    target_language=self.text_lang_var.get(),
                    custom_base_url=self.base_url_var.get(),
                    model=self.model_var.get(),
                )
                result = t.translate_text(text, self.text_lang_var.get())
                self.after(0, lambda: self._set_text_result(result))
                self.after(0, lambda: self.text_status_var.set("Concluído"))
            except Exception as e:
                self.after(0, lambda: self._set_text_result(f"Erro: {e}"))
                self.after(0, lambda: self.text_status_var.set("Erro"))
            finally:
                self.after(0, lambda: self.btn_translate_text.configure(
                    state="normal", text="Traduzir", fg_color=theme.ACCENT,
                ))

        threading.Thread(target=_run, daemon=True).start()

    def _set_text_result(self, text):
        self.text_output.configure(state="normal")
        self.text_output.delete("1.0", "end")
        self.text_output.insert("1.0", text)
        self.text_output.configure(state="disabled")

    def _copy_text_result(self):
        result = self.text_output.get("1.0", "end").strip()
        if result:
            self.clipboard_clear()
            self.clipboard_append(result)

    # ── Config / provedor ────────────────────────────────────────────────

    def _on_provider_change(self, _=None):
        self.hint_var.set(PROVIDER_HINTS.get(self.provider_var.get(), ""))
        self._update_url_state()

    def _update_url_state(self):
        provider = self.provider_var.get()
        if provider == "custom":
            self.base_url_entry.configure(state="normal")
        else:
            known_url = KNOWN_PROVIDERS.get(provider, {}).get("base_url") or "(padrão do SDK)"
            self.base_url_var.set(known_url)
            self.base_url_entry.configure(state="disabled")

    def _get_monitors(self):
        import mss
        with mss.mss() as sct:
            return list(sct.monitors[1:])

    def _selected_monitor(self):
        try:
            idx = int(self.monitor_var.get().split()[1]) - 1
        except Exception:
            idx = 0
        return self._monitors[min(idx, len(self._monitors) - 1)]

    def _region_text(self):
        r = self.config.get("region")
        if r:
            return f"x1={r['x1']} y1={r['y1']}  →  x2={r['x2']} y2={r['y2']}"
        return "Nenhuma selecionada"

    # ── Atalhos ──────────────────────────────────────────────────────────

    def _hotkey_display(self, hotkey):
        if hotkey.startswith(MOUSE_HOTKEY_PREFIX):
            btn = hotkey[len(MOUSE_HOTKEY_PREFIX):]
            return MOUSE_DISPLAY.get(btn, hotkey)
        return hotkey.upper()

    def _is_mouse_hotkey(self, hotkey):
        return hotkey.startswith(MOUSE_HOTKEY_PREFIX)

    def _make_hotkey_entry(self, parent, var, row, col=1):
        entry = theme.entry(parent, width=120, justify="center")
        entry.grid(row=row, column=col, sticky="w", padx=14, pady=4)

        def show_value():
            entry.configure(state="normal")
            entry.delete(0, "end")
            entry.insert(0, self._hotkey_display(var.get()))
            entry.configure(state="disabled", text_color=theme.ACCENT)

        show_value()

        def stop_capture(restore=False, previous=None):
            if restore and previous is not None:
                var.set(previous)
            entry.unbind("<KeyPress>")
            self.unbind_all("<KeyPress>")
            for btn_num in MOUSE_BUTTON_MAP:
                self.unbind_all(f"<Button-{btn_num}>")
            show_value()
            self._register_hotkeys()

        def on_capture_key(event):
            key = event.keysym.lower()
            if key == "escape":
                stop_capture(restore=True, previous=original)
                return "break"
            var.set(key)
            stop_capture()
            return "break"

        def on_capture_button(event):
            btn = MOUSE_BUTTON_MAP.get(event.num)
            if not btn:
                return "break"
            var.set(f"{MOUSE_HOTKEY_PREFIX}{btn}")
            stop_capture()
            return "break"

        def on_click(e):
            nonlocal original
            original = var.get()
            entry.configure(state="normal", text_color=theme.TEXT)
            entry.delete(0, "end")
            entry.insert(0, "Pressione...")
            entry.focus_set()

            def start_listening():
                entry.bind("<KeyPress>", on_capture_key)
                self.bind_all("<KeyPress>", on_capture_key)
                for btn_num in MOUSE_BUTTON_MAP:
                    self.bind_all(f"<Button-{btn_num}>", on_capture_button)

            self.after(50, start_listening)

        original = var.get()
        entry.bind("<Button-1>", on_click)

    def _register_hotkey(self, hotkey, callback):
        if not hotkey:
            return
        if self._is_mouse_hotkey(hotkey):
            btn = hotkey[len(MOUSE_HOTKEY_PREFIX):]
            lib_btn = MOUSE_TO_LIB.get(btn)
            if lib_btn is not None:
                mouse.on_button(lambda: self.after(0, callback), buttons=(lib_btn,), types=(mouse.DOWN,))
        else:
            keyboard.add_hotkey(hotkey, lambda: self.after(0, callback))

    def _register_hotkeys(self):
        keyboard.unhook_all()
        mouse.unhook_all()
        self._register_hotkey(self.hotkey_region_var.get(), self._select_region)
        self._register_hotkey(self.hotkey_translate_var.get(), self._toggle)
        self._register_hotkey(self.hotkey_toggle_var.get(), self._toggle_overlay)
        self._register_hotkey(self.hotkey_audio_var.get(), self._toggle_audio)

    # ── Pop-ups ──────────────────────────────────────────────────────────

    def _open_keys(self):
        win = ctk.CTkToplevel(self)
        win.title("Gerenciar API Keys")
        win.geometry("500x620")
        win.minsize(480, 520)
        win.resizable(True, True)
        win.attributes("-topmost", True)
        win.configure(fg_color=theme.BG)

        scroll = ctk.CTkScrollableFrame(win, fg_color=theme.BG, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            scroll, text="Gerenciar API Keys",
            font=(theme.FONT, 16, "bold"), text_color=theme.ACCENT,
        ).pack(pady=(12, 4))
        theme.hint_label(
            scroll, "Salve várias keys e troque com um clique quando bater o limite.",
        ).pack(pady=(0, 12))

        frame_list = theme.card(scroll)
        frame_list.pack(fill="x", padx=8, pady=(0, 8))
        theme.section_title(frame_list, "Keys salvas").pack(anchor="w", padx=12, pady=(10, 6))

        lb_frame = ctk.CTkFrame(frame_list, fg_color=theme.SURFACE_ALT, corner_radius=theme.CORNER_SM)
        lb_frame.pack(fill="x", padx=12, pady=(0, 8))
        self._keys_listbox = tk.Listbox(
            lb_frame, bg=theme.SURFACE_ALT, fg=theme.TEXT,
            selectbackground=theme.ACCENT, selectforeground="white",
            font=(theme.FONT, 11), height=4, relief="flat",
            activestyle="none", highlightthickness=0, bd=0,
        )
        self._keys_listbox.pack(fill="x", padx=4, pady=4)
        self._keys_win = win
        self._refresh_keys_list()

        btn_frame = ctk.CTkFrame(frame_list, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(0, 12))
        theme.success_btn(btn_frame, "Usar esta key", self._use_selected_key, width=130).pack(
            side="left", padx=(0, 6),
        )
        theme.danger_btn(btn_frame, "Remover", self._remove_selected_key, width=100).pack(side="left")

        frame_new = theme.card(scroll)
        frame_new.pack(fill="x", padx=8, pady=(0, 12))
        frame_new.columnconfigure(1, weight=1)
        theme.section_title(frame_new, "Adicionar nova key").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 8),
        )

        theme.field_label(frame_new, "Apelido:").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self._new_key_name = theme.entry(frame_new, width=200)
        self._new_key_name.grid(row=1, column=1, sticky="ew", padx=12, pady=4)
        self._new_key_name.insert(0, "Ex: Groq pessoal")

        theme.field_label(frame_new, "Provedor:").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        self._new_key_provider = theme.combo(frame_new, PROVIDER_LIST, width=200)
        self._new_key_provider.set(self.config.get("api_provider", "openrouter"))
        self._new_key_provider.grid(row=2, column=1, sticky="w", padx=12, pady=4)

        theme.field_label(frame_new, "API Key:").grid(row=3, column=0, sticky="w", padx=12, pady=4)
        self._new_key_value = theme.entry(frame_new, show="*", width=280)
        self._new_key_value.grid(row=3, column=1, sticky="ew", padx=12, pady=4)

        theme.field_label(frame_new, "Modelo:").grid(row=4, column=0, sticky="w", padx=12, pady=4)
        self._new_key_model = theme.entry(frame_new, width=280)
        self._new_key_model.grid(row=4, column=1, sticky="ew", padx=12, pady=4)
        self._new_key_model.insert(0, "(opcional)")

        theme.primary_btn(
            frame_new, "Salvar key", self._save_new_key,
            height=36, font=(theme.FONT, 11, "bold"),
        ).grid(row=5, column=0, columnspan=2, pady=(10, 14), padx=12, sticky="ew")

    def _refresh_keys_list(self):
        self._keys_listbox.delete(0, "end")
        profiles = self.config.get("profiles", {})
        for name, data in profiles.items():
            provider = data.get("provider", "")
            model = data.get("model", "")
            label = f"  {name}  [{provider}]" + (f"  —  {model}" if model else "")
            self._keys_listbox.insert("end", label)

    def _save_new_key(self):
        name = self._new_key_name.get().strip()
        key = self._new_key_value.get().strip()
        provider = self._new_key_provider.get()
        model = self._new_key_model.get().strip()
        if model == "(opcional)":
            model = ""
        if not name or not key:
            return
        if "profiles" not in self.config:
            self.config["profiles"] = {}
        self.config["profiles"][name] = {"api_key": key, "provider": provider, "model": model}
        save_config(self.config)
        self._new_key_name.delete(0, "end")
        self._new_key_value.delete(0, "end")
        self._refresh_keys_list()

    def _use_selected_key(self):
        sel = self._keys_listbox.curselection()
        if not sel:
            return
        profiles = self.config.get("profiles", {})
        name = list(profiles.keys())[sel[0]]
        data = profiles[name]
        self.api_key_var.set(data.get("api_key", ""))
        self.provider_var.set(data.get("provider", "openrouter"))
        self.model_var.set(data.get("model", ""))
        self.config["api_key"] = data.get("api_key", "")
        self.config["api_provider"] = data.get("provider", "openrouter")
        self.config["model"] = data.get("model", "")
        self._on_provider_change()
        save_config(self.config)
        self._keys_win.destroy()

    def _remove_selected_key(self):
        sel = self._keys_listbox.curselection()
        if not sel:
            return
        profiles = self.config.get("profiles", {})
        name = list(profiles.keys())[sel[0]]
        del self.config["profiles"][name]
        save_config(self.config)
        self._refresh_keys_list()

    def _open_help(self):
        win = ctk.CTkToplevel(self)
        win.title("Como usar o Nidus")
        win.geometry("560x620")
        win.resizable(False, True)
        win.attributes("-topmost", True)
        win.configure(fg_color=theme.BG)

        scroll = ctk.CTkScrollableFrame(win, fg_color=theme.BG, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        f = scroll

        def section(title):
            ctk.CTkLabel(
                f, text=title, font=(theme.FONT, 12, "bold"), text_color=theme.ACCENT, anchor="w",
            ).pack(anchor="w", padx=12, pady=(16, 2))
            ctk.CTkFrame(f, fg_color=theme.ACCENT, height=1).pack(fill="x", padx=12)

        def text(msg):
            if not msg:
                ctk.CTkLabel(f, text="", height=4).pack()
                return
            ctk.CTkLabel(
                f, text=msg, font=(theme.FONT, 11), text_color=theme.TEXT,
                wraplength=500, justify="left", anchor="w",
            ).pack(anchor="w", padx=20, pady=2)

        def step(n, msg):
            ctk.CTkLabel(
                f, text=f"  {n}.  {msg}", font=(theme.FONT, 11), text_color=theme.TEXT,
                wraplength=490, justify="left", anchor="w",
            ).pack(anchor="w", padx=12, pady=2)

        def code(msg):
            ctk.CTkLabel(
                f, text=msg, font=("Courier New", 10), text_color=theme.ACCENT,
                fg_color=theme.SURFACE, corner_radius=6, anchor="w",
            ).pack(anchor="w", padx=20, pady=2, fill="x")

        ctk.CTkLabel(
            f, text="Como usar o Nidus",
            font=(theme.FONT, 16, "bold"), text_color=theme.ACCENT,
        ).pack(pady=(12, 4))
        theme.hint_label(f, "Guia completo de configuração e uso").pack(pady=(0, 8))

        section("1. Escolha um provedor de IA")
        text("O app precisa de uma API de IA para traduzir. Escolha um dos provedores abaixo:")
        text("• OpenRouter — recomendado, tem plano grátis e muitos modelos")
        text("• Groq — muito rápido, plano grátis generoso")
        text("• OpenAI — pago, mas muito preciso (gpt-4o-mini é barato)")
        text("• Anthropic — pago, Claude é excelente para tradução")
        text("• Custom — qualquer API compatível com OpenAI (Ollama local, etc.)")

        section("2. Como obter sua API Key")
        text("OpenRouter (recomendado para começar):")
        step(1, "Acesse openrouter.ai e crie uma conta gratuita")
        step(2, "Vá em Keys → Create Key")
        step(3, "Copie a chave e cole no campo API Key do app")
        step(4, "No campo Modelo, coloque: openai/gpt-4o-mini")
        text("")
        text("Groq (grátis):")
        step(1, "Acesse console.groq.com e crie uma conta")
        step(2, "Vá em API Keys → Create API Key")
        step(3, "Cole a chave no app e selecione o provedor Groq")
        text("")
        text("OpenAI:")
        step(1, "Acesse platform.openai.com")
        step(2, "Vá em API Keys → Create new secret key")
        step(3, "Cole no app — o modelo padrão já é gpt-4o-mini")

        section("3. Configure o app")
        step(1, "Selecione o Provedor e cole sua API Key")
        step(2, "Escolha o idioma para traduzir (ex: Português)")
        step(3, "Escolha o modo: 'Traduzir uma vez' ou 'Contínuo'")
        step(4, "Clique em Salvar configurações")

        section("4. Selecione a região para traduzir")
        step(1, "Abra o jogo e deixe a legenda/texto aparecer na tela")
        step(2, "Volte ao app (ou pressione F9) para abrir o seletor")
        step(3, "Arraste para desenhar um retângulo em volta do texto")
        step(4, "A região selecionada fica salva automaticamente")
        text("Dica: selecione só a área do texto, não a tela inteira — economiza tokens!")

        section("5. Traduzindo")
        text("Modo 'Traduzir uma vez':")
        step(1, "Deixe o texto visível na tela")
        step(2, "Pressione F10 ou clique em Traduzir Agora")
        step(3, "A tradução aparece na tela em ~1 segundo")
        text("")
        text("Modo 'Contínuo':")
        step(1, "Clique em Iniciar — o app monitora a região escolhida")
        step(2, "Quando o texto mudar, traduz automaticamente")
        step(3, "Clique em Parar quando terminar")

        section("6. Atalhos")
        text("Funcionam mesmo com o jogo em foco (rode como administrador):")
        code("F9  →  Abrir seletor de região")
        code("F10 →  Traduzir agora / Iniciar-Parar")
        code("F11 →  Mostrar / ocultar a tradução")
        code("F12 →  Iniciar / parar tradução por áudio (Live)")
        text("Você pode usar teclas do teclado ou botões do mouse (incluindo Mouse 4 e 5).")
        text("Para trocar um atalho: clique no campo e pressione a tecla ou botão desejado.")

        section("7. Overlay (janela de tradução)")
        text("A tradução aparece numa janelinha preta sobre o jogo.")
        step(1, "Arraste pela barra vermelha no topo para mover")
        step(2, "Arraste o canto inferior direito para redimensionar")
        step(3, "Clique no X para fechar temporariamente")

        theme.primary_btn(f, "Fechar", win.destroy, height=36).pack(pady=20, padx=12, fill="x")

    def _open_donation(self):
        win = ctk.CTkToplevel(self)
        win.title("Apoiar o projeto")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(fg_color=theme.BG)

        ctk.CTkLabel(
            win, text="Apoie o Nidus",
            font=(theme.FONT, 16, "bold"), text_color=theme.ACCENT,
        ).pack(pady=(20, 4))
        theme.hint_label(win, "Se o app te ajudou, considere contribuir :)").pack(pady=(0, 12))

        try:
            from PIL import ImageTk
            img = Image.open(_resource_path("code.jpeg")).resize((220, 220))
            photo = ImageTk.PhotoImage(img)
            lbl_img = ctk.CTkLabel(win, image=photo, text="")
            lbl_img.image = photo
            lbl_img.pack(pady=(0, 8))
        except Exception:
            ctk.CTkLabel(win, text="[QR Code não encontrado]", text_color=theme.TEXT_MUTED).pack()

        PIX_KEY = "00020126580014BR.GOV.BCB.PIX01364df31385-39ad-4587-9a8b-72bb281d15905204000053039865802BR5917Jeferson Marciano6009SAO PAULO62140510AATRReYlC6630486CC"
        theme.field_label(win, "Chave Pix (copia e cola):").pack()

        frame_pix = theme.card(win)
        frame_pix.pack(padx=20, pady=4, fill="x")
        pix_entry = theme.entry(frame_pix, font=(theme.FONT, 8))
        pix_entry.pack(side="left", fill="x", expand=True, padx=(10, 0), pady=8)
        pix_entry.insert(0, PIX_KEY)
        pix_entry.configure(state="disabled")

        def copiar():
            win.clipboard_clear()
            win.clipboard_append(PIX_KEY)
            btn_copy.configure(text="Copiado!")
            win.after(2000, lambda: btn_copy.configure(text="Copiar"))

        btn_copy = theme.primary_btn(frame_pix, "Copiar", copiar, width=80, height=30)
        btn_copy.pack(side="right", pady=6, padx=8)

        import webbrowser
        NUBANK_URL = "https://nubank.com.br/cobrar/9319j/6a2db4f7-c325-43b6-8f4b-6b919faf887e"
        ctk.CTkButton(
            win, text="Abrir link do Nubank",
            fg_color="transparent", hover_color=theme.SURFACE,
            text_color="#a259ff", font=(theme.FONT, 11, "underline"),
            command=lambda: webbrowser.open(NUBANK_URL),
        ).pack(pady=(4, 20))

    # ── Ações principais ─────────────────────────────────────────────────

    def _toggle_overlay(self):
        if not self.overlay:
            return
        if self.overlay._visible:
            self.overlay.hide()
        else:
            self.overlay._root.after(0, self.overlay._root.deiconify)
            self.overlay._visible = True

    def _on_mode_change(self):
        if self.mode_var.get() == "once":
            self.interval_frame.grid_remove()
            self.btn_start.configure(text="Traduzir Agora")
        else:
            self.interval_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=4)
            self.btn_start.configure(text="Iniciar Tradução")

    def _select_region(self):
        self.withdraw()
        mon = self._selected_monitor()
        selector = RegionSelector(self, mon)
        self.wait_window(selector)
        if selector.result:
            self.config["region"] = selector.result
            self.region_label.configure(text=self._region_text())
        self.deiconify()

    def _save(self):
        self.config["api_key"] = self.api_key_var.get()
        self.config["api_provider"] = self.provider_var.get()
        self.config["custom_base_url"] = self.base_url_var.get()
        self.config["model"] = self.model_var.get()
        self.config["target_language"] = self.lang_var.get()
        self.config["capture_interval"] = self.interval_var.get()
        self.config["mode"] = self.mode_var.get()
        self.config["hotkey_region"] = self.hotkey_region_var.get()
        self.config["hotkey_translate"] = self.hotkey_translate_var.get()
        self.config["hotkey_toggle"] = self.hotkey_toggle_var.get()
        self.config["hotkey_audio"] = self.hotkey_audio_var.get()
        try:
            self.config["monitor_index"] = int(self.monitor_var.get().split()[1]) - 1
        except Exception:
            self.config["monitor_index"] = 0
        save_config(self.config)
        self._register_hotkeys()
        self.status_var.set("Configurações salvas!")

    def _refresh_audio_devices(self):
        if not AUDIO_AVAILABLE:
            return
        devices = ["(Padrão do sistema)"] + list_output_devices()
        self.audio_device_combo.configure(values=devices)
        current = self.config.get("audio_device", "")
        if not current:
            self.audio_device_var.set("(Padrão do sistema)")
        elif current in devices:
            self.audio_device_var.set(current)
        elif devices:
            self.audio_device_var.set(devices[0])

    def _save_audio_config(self):
        device = self.audio_device_var.get()
        self.config["audio_device"] = "" if device == "(Padrão do sistema)" else device
        self.config["audio_capture_mode"] = self.audio_capture_mode_var.get()
        pid = self._selected_audio_app_pid()
        self.config["audio_target_pid"] = pid or 0
        self.config["whisper_model"] = self.whisper_model_var.get()
        self.config["whisper_compute_device"] = self.whisper_compute_var.get()
        self.config["audio_source_language"] = self.audio_source_map.get(
            self.audio_source_var.get(), "auto",
        )
        self.config["audio_streaming"] = self.audio_streaming_var.get()
        self.config["target_language"] = self.audio_lang_var.get()
        save_config(self.config)

    def _toggle_audio(self):
        if self.audio_running:
            self._stop_audio()
        else:
            self._start_audio()

    def _start_audio(self):
        if not AUDIO_AVAILABLE:
            self.audio_status_var.set("Recurso disponível apenas no Windows.")
            return
        if self.interview_running:
            self._stop_interview()
        if self.running:
            self._stop()
        self._save_audio_config()
        api_key = self.api_key_var.get().strip() or self.config.get("api_key", "")
        if not api_key:
            self.audio_status_var.set("Erro: configure a API Key na aba Jogo.")
            return

        if not self.overlay:
            self.overlay = Overlay()

        device = self.config.get("audio_device") or None
        capture_mode = self.config.get("audio_capture_mode", "system")
        target_pid = self.config.get("audio_target_pid") or None
        if capture_mode == "application" and not target_pid:
            self.audio_status_var.set("Erro: selecione um aplicativo com áudio.")
            self.btn_audio_start.configure(
                state="normal", text="Iniciar tradução por áudio", fg_color=theme.ACCENT,
            )
            return
        self.btn_audio_start.configure(state="disabled", text="Iniciando...", fg_color=theme.DISABLED)
        self.audio_status_var.set("Carregando...")

        def _run():
            try:
                translator = Translator(
                    api_key=api_key,
                    provider=self.provider_var.get(),
                    target_language=self.audio_lang_var.get(),
                    custom_base_url=self.base_url_var.get(),
                    model=self.model_var.get(),
                )
                self.audio_pipeline = AudioPipeline(
                    translator=translator,
                    device=device,
                    capture_mode=capture_mode,
                    target_pid=target_pid if capture_mode == "application" else None,
                    whisper_model=self.config["whisper_model"],
                    compute_device=self.config.get("whisper_compute_device", "auto"),
                    source_language=self.config["audio_source_language"],
                    streaming=self.config.get("audio_streaming", True),
                    on_status=lambda msg: self._ui(self.audio_status_var.set, msg),
                    on_original=lambda text: self._ui(
                        self.audio_original_var.set, f'Ouvido: "{text[:100]}"',
                    ),
                    on_translation=self._on_audio_translation,
                    on_translation_partial=self._on_audio_translation_partial,
                    on_error=lambda err: self._ui(
                        self.audio_status_var.set, f"Erro: {err[:80]}",
                    ),
                )
                self.audio_pipeline.start()
                self.audio_running = True
                self._ui(lambda: self.btn_audio_start.configure(
                    state="normal", text="Parar tradução por áudio", fg_color=theme.DISABLED,
                ))
            except Exception as e:
                import traceback
                from src.debug_log import log
                log(f"Erro ao iniciar áudio: {e}\n{traceback.format_exc()}")
                self._ui(self.audio_status_var.set, f"Erro: {str(e)[:80]}")
                self._ui(lambda: self.btn_audio_start.configure(
                    state="normal", text="Iniciar tradução por áudio", fg_color=theme.ACCENT,
                ))

        threading.Thread(target=_run, daemon=True).start()

    def _on_audio_translation(self, text: str):
        def _update():
            preview = f'"{text[:80]}..."' if len(text) > 80 else f'"{text}"'
            self.audio_translation_var.set(preview)
            if self.overlay:
                self.overlay.show_live(text, partial=False)
        self._ui(_update)

    def _on_audio_translation_partial(self, text: str):
        def _update():
            preview = f'"{text[:80]}..."' if len(text) > 80 else f'"{text}"'
            self.audio_translation_var.set(preview)
            if self.overlay:
                self.overlay.show_live(text, partial=True)
        self._ui(_update)

    def _stop_audio(self):
        self.audio_running = False
        if self.audio_pipeline:
            self.audio_pipeline.stop()
            self.audio_pipeline = None
        if self.overlay:
            self.overlay.clear_live()
        self.btn_audio_start.configure(
            state="normal", text="Iniciar tradução por áudio", fg_color=theme.ACCENT,
        )
        self.audio_status_var.set("Parado")

    def _save_interview_config(self):
        self.config["interview_context"] = self.interview_context_box.get("1.0", "end").strip()
        self.config["interview_type"] = self.interview_type_var.get()
        self.config["interview_answer_language"] = self.interview_answer_lang_var.get()
        self.config["interview_streaming"] = self.interview_streaming_var.get()
        self.config["interview_capture_mode"] = self.interview_capture_mode_var.get()
        pid = self._selected_interview_app_pid()
        self.config["interview_target_pid"] = pid or 0
        device = self.interview_device_var.get()
        self.config["interview_audio_device"] = "" if device == "(Padrão do sistema)" else device
        self.config["whisper_model"] = self.interview_whisper_var.get()
        self.config["whisper_compute_device"] = self.interview_compute_var.get()
        self.config["audio_source_language"] = self.AUDIO_SOURCE_MAP.get(
            self.interview_source_var.get(), "auto",
        )
        save_config(self.config)

    def _toggle_interview(self):
        if self.interview_running:
            self._stop_interview()
        else:
            self._start_interview()

    def _start_interview(self):
        if not AUDIO_AVAILABLE:
            self.interview_status_var.set("Recurso disponível apenas no Windows.")
            return
        if self.audio_running:
            self._stop_audio()
        if self.running:
            self._stop()
        self._save_interview_config()
        api_key = self.api_key_var.get().strip() or self.config.get("api_key", "")
        if not api_key:
            self.interview_status_var.set("Erro: configure a API Key na aba Jogo.")
            return

        device = self.config.get("interview_audio_device") or None
        capture_mode = self.config.get("interview_capture_mode", "system")
        target_pid = self.config.get("interview_target_pid") or None
        if capture_mode == "application" and not target_pid:
            self.interview_status_var.set(
                "Erro: selecione um aplicativo com áudio (clique Atualizar).",
            )
            return

        self.btn_interview_start.configure(
            state="disabled", text="Iniciando...", fg_color=theme.DISABLED,
        )
        self.interview_status_var.set("Carregando...")
        self._interview_answer_cache = ""
        self._set_textbox(self.interview_question_box, "")
        self._set_textbox(self.interview_answer_box, "", readonly=False)

        def _run():
            try:
                translator = Translator(
                    api_key=api_key,
                    provider=self.provider_var.get(),
                    target_language=self.interview_answer_lang_var.get(),
                    custom_base_url=self.base_url_var.get(),
                    model=self.model_var.get(),
                )
                self.interview_pipeline = AudioPipeline(
                    translator=translator,
                    device=device,
                    capture_mode=capture_mode,
                    target_pid=target_pid if capture_mode == "application" else None,
                    whisper_model=self.config["whisper_model"],
                    compute_device=self.config.get("whisper_compute_device", "auto"),
                    source_language=self.config["audio_source_language"],
                    streaming=self.config.get("interview_streaming", True),
                    mode="interview",
                    interview_context=self.config.get("interview_context", ""),
                    interview_type=self.config.get("interview_type", "Geral"),
                    answer_language=self.config.get("interview_answer_language", "Português"),
                    on_status=lambda msg: self._ui(self.interview_status_var.set, msg),
                    on_original=lambda text: self._ui(self._on_interview_question, text),
                    on_translation=lambda text: self._ui(self._on_interview_answer, text),
                    on_translation_partial=lambda text: self._ui(
                        self._on_interview_answer_partial, text,
                    ),
                    on_error=lambda err: self._ui(
                        self.interview_status_var.set, f"Erro: {err[:80]}",
                    ),
                )
                self.interview_pipeline.start()
                self.interview_running = True
                self._ui(lambda: self.btn_interview_start.configure(
                    state="normal", text="Parar modo entrevista", fg_color=theme.DISABLED,
                ))
            except Exception as e:
                import traceback
                from src.debug_log import log
                log(f"Erro ao iniciar entrevista: {e}\n{traceback.format_exc()}")
                self._ui(self.interview_status_var.set, f"Erro: {str(e)[:80]}")
                self._ui(lambda: self.btn_interview_start.configure(
                    state="normal", text="Iniciar modo entrevista", fg_color=theme.ACCENT,
                ))

        threading.Thread(target=_run, daemon=True).start()

    def _on_interview_question(self, text: str):
        self._set_textbox(self.interview_question_box, text)
        self._last_interview_question = text

    def _on_interview_answer(self, text: str):
        self._interview_answer_cache = text
        self._set_textbox(self.interview_answer_box, text, readonly=False)
        question = getattr(self, "_last_interview_question", "")
        if question and text:
            self._append_interview_history(question, text)

    def _on_interview_answer_partial(self, text: str):
        if text == self._interview_answer_cache:
            return
        self._interview_answer_cache = text
        self._set_textbox(self.interview_answer_box, text, readonly=False)

    def _stop_interview(self):
        self.interview_running = False
        if self.interview_pipeline:
            self.interview_pipeline.stop()
            self.interview_pipeline = None
        self.btn_interview_start.configure(
            state="normal", text="Iniciar modo entrevista", fg_color=theme.ACCENT,
        )
        self.interview_status_var.set("Parado")

    def _toggle(self):
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self):
        if self.audio_running:
            self._stop_audio()
        if self.interview_running:
            self._stop_interview()
        self._save()
        if not self.config["api_key"]:
            self.status_var.set("Erro: informe a API Key!")
            return
        if not self.config.get("region"):
            self.status_var.set("Erro: selecione uma região!")
            return

        if not self.overlay:
            self.overlay = Overlay()
        self.translator = Translator(
            api_key=self.config["api_key"],
            provider=self.config["api_provider"],
            target_language=self.config["target_language"],
            custom_base_url=self.config["custom_base_url"],
            model=self.config["model"],
        )
        self.capture = ScreenCapture(self.config["region"], self.config["capture_interval"])

        if self.mode_var.get() == "once":
            self.btn_start.configure(state="disabled", text="Traduzindo...", fg_color=theme.DISABLED)
            self.status_var.set("Traduzindo...")
            self.thread = threading.Thread(target=self._translate_once, daemon=True)
        else:
            self.running = True
            self.btn_start.configure(text="Parar", fg_color=theme.DISABLED)
            self.status_var.set("Rodando...")
            self.thread = threading.Thread(target=self._loop, daemon=True)

        self.thread.start()

    def _stop(self):
        self.running = False
        self.btn_start.configure(state="normal", fg_color=theme.ACCENT)
        self.status_var.set("Parado")
        self.after(0, self._on_mode_change)

    def _translate_once(self):
        try:
            frame, _ = next(self.capture.stream())
            translation = self.translator.translate(frame)
            if translation:
                self.overlay.show(translation)
                preview = f'"{translation[:80]}..."' if len(translation) > 80 else f'"{translation}"'
                self.after(0, self.last_text_var.set, preview)
                self.after(0, self.status_var.set, "Tradução concluída!")
            else:
                self.after(0, self.status_var.set, "Nenhum texto encontrado.")
        except Exception as e:
            self.after(0, self.status_var.set, f"Erro: {str(e)[:80]}")
        finally:
            label = "Traduzir Agora" if self.mode_var.get() == "once" else "Iniciar Tradução"
            self.after(0, lambda: self.btn_start.configure(
                state="normal", text=label, fg_color=theme.ACCENT,
            ))

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
                    preview = f'"{translation[:80]}..."' if len(translation) > 80 else f'"{translation}"'
                    self.after(0, self.last_text_var.set, preview)
            except Exception as e:
                self.after(0, self.status_var.set, f"Erro: {str(e)[:80]}")


class RegionSelector(tk.Toplevel):
    def __init__(self, parent, monitor: dict):
        super().__init__(parent)
        self.monitor = monitor
        self.result = None
        self.start_x = self.start_y = 0
        self.rect = None
        self.fill_rect = None
        self.dim_rects = []
        self.info_label = None

        ml, mt = monitor["left"], monitor["top"]
        mw, mh = monitor["width"], monitor["height"]
        self.overrideredirect(True)
        self.geometry(f"{mw}x{mh}+{ml}+{mt}")
        self.attributes("-alpha", 0.55)
        self.configure(bg=theme.BG)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()

        self.canvas = tk.Canvas(self, cursor="cross", bg=theme.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.create_rectangle(0, 0, 9999, 52, fill=theme.SURFACE_ALT, outline="")
        self.canvas.create_text(
            16, 26,
            text=f"Monitor {mw}×{mh}  —  Arraste para selecionar a região   |   ESC para cancelar",
            anchor="w", fill=theme.TEXT, font=(theme.FONT, 13),
        )

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self.destroy())

    def _clear(self):
        for item in [self.rect, self.fill_rect, self.info_label] + self.dim_rects:
            if item:
                self.canvas.delete(item)
        self.dim_rects = []
        self.rect = self.fill_rect = self.info_label = None

    def _on_press(self, e):
        self.start_x, self.start_y = e.x, e.y
        self._clear()

    def _on_drag(self, e):
        self._clear()
        x1, y1 = self.start_x, self.start_y
        x2, y2 = e.x, e.y
        sw, sh = self.monitor["width"], self.monitor["height"]

        self.dim_rects = [
            self.canvas.create_rectangle(0, 0, sw, min(y1, y2), fill=theme.BG, outline=""),
            self.canvas.create_rectangle(0, max(y1, y2), sw, sh, fill=theme.BG, outline=""),
            self.canvas.create_rectangle(0, min(y1, y2), min(x1, x2), max(y1, y2), fill=theme.BG, outline=""),
            self.canvas.create_rectangle(max(x1, x2), min(y1, y2), sw, max(y1, y2), fill=theme.BG, outline=""),
        ]
        self.fill_rect = self.canvas.create_rectangle(
            x1, y1, x2, y2, fill="#ffffff", outline="", stipple="gray12",
        )
        self.rect = self.canvas.create_rectangle(
            x1, y1, x2, y2, outline=theme.ACCENT, width=3,
        )
        w, h = abs(x2 - x1), abs(y2 - y1)
        self.info_label = self.canvas.create_text(
            (x1 + x2) // 2, min(y1, y2) - 10,
            text=f"{w} × {h} px",
            fill=theme.ACCENT, font=(theme.FONT, 11, "bold"), anchor="s",
        )

    def _on_release(self, e):
        x1, y1 = min(self.start_x, e.x), min(self.start_y, e.y)
        x2, y2 = max(self.start_x, e.x), max(self.start_y, e.y)
        if x2 - x1 > 20 and y2 - y1 > 10:
            ml, mt = self.monitor["left"], self.monitor["top"]
            self.result = {"x1": x1 + ml, "y1": y1 + mt, "x2": x2 + ml, "y2": y2 + mt}
        self.destroy()


if __name__ == "__main__":
    def _thread_excepthook(args):
        import traceback
        from src.debug_log import log
        log(f"Erro em thread {args.thread.name}: {args.exc_value}\n{traceback.format_exc()}")
        if _DEBUG:
            traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = _thread_excepthook

    try:
        if _DEBUG:
            print("[Nidus] Iniciando interface...")
        app = App()
        if _DEBUG:
            print("[Nidus] App pronto. Feche a janela ou Ctrl+C aqui para encerrar.")
        app.mainloop()
    except Exception:
        import traceback
        log_path = os.path.join(APP_DIR, "nidus_error.log")
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        if _DEBUG:
            print(f"\n[Nidus] ERRO — detalhes também em:\n{log_path}\n")
            traceback.print_exc()
        if getattr(sys, "frozen", False):
            ctypes.windll.user32.MessageBoxW(
                0,
                f"O Nidus encontrou um erro ao iniciar.\n\nDetalhes em:\n{log_path}",
                "Nidus",
                0x10,
            )
        else:
            raise
