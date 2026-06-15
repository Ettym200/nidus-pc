import sys
import ctypes
import platform

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"

# Windows: re-lança como admin para hotkeys funcionarem em jogos
if IS_WINDOWS:
    def _is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    if not _is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1
        )
        sys.exit(0)

import tkinter as tk
from tkinter import ttk
import threading
import json
import os
from PIL import Image

# Hotkeys: keyboard no Windows, pynput no Linux
if IS_WINDOWS:
    import keyboard
    def _add_hotkey(key, fn):
        if key:
            keyboard.add_hotkey(key, fn)
    def _unhook_all():
        keyboard.unhook_all()
else:
    from pynput import keyboard as pynput_kb
    _hotkey_listener = None
    _hotkey_map = {}

    def _add_hotkey(key, fn):
        _hotkey_map[key.lower()] = fn

    def _unhook_all():
        global _hotkey_listener
        _hotkey_map.clear()
        if _hotkey_listener:
            _hotkey_listener.stop()
            _hotkey_listener = None

    def _start_pynput():
        global _hotkey_listener
        def on_press(k):
            try:
                name = k.name.lower() if hasattr(k, "name") else k.char
                if name in _hotkey_map:
                    _hotkey_map[name]()
            except Exception:
                pass
        _hotkey_listener = pynput_kb.Listener(on_press=on_press)
        _hotkey_listener.start()
from capture import ScreenCapture
from translator import Translator, KNOWN_PROVIDERS
from overlay import Overlay

CONFIG_FILE = "config.json"

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

PROVIDER_HINTS = {
    "openai":     "Modelo: gpt-4o-mini  |  openai.com",
    "anthropic":  "Modelo: claude-haiku  |  anthropic.com",
    "openrouter": "Base URL já configurada  |  openrouter.ai",
    "groq":       "Modelo padrão: llama-4-scout (com visão)  |  groq.com  — GRÁTIS",
    "custom":     "Informe a Base URL abaixo (ex: http://localhost:11434/v1)",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Game Translator")
        self.geometry("520x700")
        self.resizable(False, True)
        self.configure(bg="#1a1a2e")

        self.config = load_config()
        self.running = False
        self.overlay = None
        self.capture = None
        self.translator = None

        self._build_ui()
        self._register_hotkeys()

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel", background="#1a1a2e", foreground="#eaeaea", font=("Segoe UI", 10))
        style.configure("TEntry", fieldbackground="#16213e", foreground="#eaeaea")
        style.configure("TButton", background="#0f3460", foreground="#eaeaea", font=("Segoe UI", 10))
        style.configure("TCombobox", fieldbackground="#16213e", foreground="#eaeaea", background="#16213e", selectbackground="#16213e", selectforeground="#eaeaea")
        style.map("TCombobox", fieldbackground=[("readonly", "#16213e")], foreground=[("readonly", "#eaeaea")], background=[("readonly", "#16213e")])

        # Canvas com scrollbar para acomodar todo o conteúdo
        canvas = tk.Canvas(self, bg="#1a1a2e", highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg="#1a1a2e")
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_resize(e):
            canvas.itemconfig(canvas_window, width=e.width)
        canvas.bind("<Configure>", _on_resize)

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_frame_configure)

        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        f = inner  # todos os widgets usam f como parent
        pad = {"padx": 16, "pady": 6}

        tk.Label(f, text="Game Translator", bg="#1a1a2e", fg="#e94560",
                 font=("Segoe UI", 16, "bold")).pack(pady=(20, 4))
        tk.Label(f, text="Tradução simultânea de legendas de jogos",
                 bg="#1a1a2e", fg="#aaaaaa", font=("Segoe UI", 9)).pack(pady=(0, 12))

        # API
        frame_api = tk.LabelFrame(f, text=" Configuração da API ", bg="#1a1a2e", fg="#e94560",
                                   font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        frame_api.pack(fill="x", **pad)
        frame_api.columnconfigure(1, weight=1)

        tk.Label(frame_api, text="Provedor:", bg="#1a1a2e", fg="#eaeaea").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.provider_var = tk.StringVar(value=self.config["api_provider"])
        providers = ttk.Combobox(frame_api, textvariable=self.provider_var,
                                  values=PROVIDER_LIST, width=18, state="readonly")
        providers.grid(row=0, column=1, sticky="w", padx=8, pady=4)
        providers.bind("<<ComboboxSelected>>", self._on_provider_change)

        self.hint_var = tk.StringVar(value=PROVIDER_HINTS.get(self.config["api_provider"], ""))
        self.hint_label = tk.Label(frame_api, textvariable=self.hint_var, bg="#1a1a2e",
                                    fg="#666699", font=("Segoe UI", 8), wraplength=360)
        self.hint_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        tk.Label(frame_api, text="API Key:", bg="#1a1a2e", fg="#eaeaea").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.api_key_var = tk.StringVar(value=self.config["api_key"])
        tk.Entry(frame_api, textvariable=self.api_key_var, show="*", width=36,
                 bg="#16213e", fg="#eaeaea", insertbackground="white", relief="flat").grid(row=2, column=1, padx=8, pady=4, sticky="ew")

        # Base URL customizada
        tk.Label(frame_api, text="Base URL:", bg="#1a1a2e", fg="#eaeaea").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        self.base_url_var = tk.StringVar(value=self.config["custom_base_url"])
        self.base_url_entry = tk.Entry(frame_api, textvariable=self.base_url_var, width=36,
                                        bg="#16213e", fg="#eaeaea", insertbackground="white", relief="flat")
        self.base_url_entry.grid(row=3, column=1, padx=8, pady=4, sticky="ew")

        # Modelo
        tk.Label(frame_api, text="Modelo:", bg="#1a1a2e", fg="#eaeaea").grid(row=4, column=0, sticky="w", padx=8, pady=4)
        self.model_var = tk.StringVar(value=self.config["model"])
        tk.Entry(frame_api, textvariable=self.model_var, width=36,
                 bg="#16213e", fg="#aaaaaa", insertbackground="white", relief="flat",
                 ).grid(row=4, column=1, padx=8, pady=4, sticky="ew")
        tk.Label(frame_api, text="(deixe vazio para usar o padrão do provedor)",
                 bg="#1a1a2e", fg="#555577", font=("Segoe UI", 8)).grid(row=5, column=1, sticky="w", padx=8)

        self._update_url_state()

        # Tradução
        frame_trans = tk.LabelFrame(f, text=" Tradução ", bg="#1a1a2e", fg="#e94560",
                                     font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        frame_trans.pack(fill="x", **pad)

        tk.Label(frame_trans, text="Traduzir para:", bg="#1a1a2e", fg="#eaeaea").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.lang_var = tk.StringVar(value=self.config["target_language"])
        langs = ttk.Combobox(frame_trans, textvariable=self.lang_var,
                              values=["Português", "Inglês", "Espanhol", "Japonês", "Francês"], width=16, state="readonly")
        langs.grid(row=0, column=1, sticky="w", padx=8, pady=4)

        tk.Label(frame_trans, text="Modo:", bg="#1a1a2e", fg="#eaeaea").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.mode_var = tk.StringVar(value=self.config.get("mode", "once"))
        frame_mode = tk.Frame(frame_trans, bg="#1a1a2e")
        frame_mode.grid(row=1, column=1, sticky="w", padx=8, pady=4)
        tk.Radiobutton(frame_mode, text="Traduzir uma vez", variable=self.mode_var, value="once",
                       bg="#1a1a2e", fg="#eaeaea", selectcolor="#0f3460",
                       command=self._on_mode_change).pack(side="left", padx=(0, 12))
        tk.Radiobutton(frame_mode, text="Contínuo", variable=self.mode_var, value="continuous",
                       bg="#1a1a2e", fg="#eaeaea", selectcolor="#0f3460",
                       command=self._on_mode_change).pack(side="left")

        self.interval_frame = tk.Frame(frame_trans, bg="#1a1a2e")
        self.interval_frame.grid(row=2, column=0, columnspan=2, sticky="w")
        tk.Label(self.interval_frame, text="Intervalo (s):", bg="#1a1a2e", fg="#eaeaea").pack(side="left", padx=8, pady=4)
        self.interval_var = tk.DoubleVar(value=self.config["capture_interval"])
        tk.Scale(self.interval_frame, variable=self.interval_var, from_=0.5, to=5.0, resolution=0.5,
                 orient="horizontal", bg="#1a1a2e", fg="#eaeaea", highlightthickness=0,
                 troughcolor="#16213e", length=200).pack(side="left", pady=4)

        # Região
        frame_region = tk.LabelFrame(f, text=" Região Monitorada ", bg="#1a1a2e", fg="#e94560",
                                      font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        frame_region.pack(fill="x", **pad)

        self.region_label = tk.Label(frame_region, text=self._region_text(), bg="#1a1a2e", fg="#aaaaaa")
        self.region_label.pack(side="left", padx=8, pady=6)
        tk.Button(frame_region, text="Selecionar região", command=self._select_region,
                  bg="#0f3460", fg="#eaeaea", relief="flat", cursor="hand2").pack(side="right", padx=8, pady=6)

        # Hotkeys
        frame_hotkey = tk.LabelFrame(f, text=" Atalhos de Teclado ", bg="#1a1a2e", fg="#e94560",
                                      font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        frame_hotkey.pack(fill="x", **pad)
        frame_hotkey.columnconfigure(1, weight=1)

        tk.Label(frame_hotkey, text="Selecionar região:", bg="#1a1a2e", fg="#eaeaea").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.hotkey_region_var = tk.StringVar(value=self.config.get("hotkey_region", "f9"))
        self._make_hotkey_entry(frame_hotkey, self.hotkey_region_var, row=0)

        tk.Label(frame_hotkey, text="Traduzir agora:", bg="#1a1a2e", fg="#eaeaea").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.hotkey_translate_var = tk.StringVar(value=self.config.get("hotkey_translate", "f10"))
        self._make_hotkey_entry(frame_hotkey, self.hotkey_translate_var, row=1)

        tk.Label(frame_hotkey, text="Mostrar/ocultar tradução:", bg="#1a1a2e", fg="#eaeaea").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.hotkey_toggle_var = tk.StringVar(value=self.config.get("hotkey_toggle", "f11"))
        self._make_hotkey_entry(frame_hotkey, self.hotkey_toggle_var, row=2)

        tk.Label(frame_hotkey, text="(clique no campo e pressione a tecla desejada)",
                 bg="#1a1a2e", fg="#555577", font=("Segoe UI", 8)).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        # Status
        self.status_var = tk.StringVar(value="Parado")
        tk.Label(f, textvariable=self.status_var, bg="#1a1a2e", fg="#aaaaaa",
                 font=("Segoe UI", 9)).pack(pady=(8, 0))

        self.last_text_var = tk.StringVar(value="")
        tk.Label(f, textvariable=self.last_text_var, bg="#1a1a2e", fg="#e94560",
                 font=("Segoe UI", 9, "italic"), wraplength=460).pack(pady=(2, 8))

        self.btn_start = tk.Button(f, text="▶  Iniciar Tradução", command=self._toggle,
                                    bg="#e94560", fg="white", font=("Segoe UI", 12, "bold"),
                                    relief="flat", cursor="hand2", height=2)
        self.btn_start.pack(fill="x", padx=16, pady=(8, 4))

        tk.Button(f, text="Salvar configurações", command=self._save,
                  bg="#0f3460", fg="#eaeaea", relief="flat", cursor="hand2").pack(pady=4)

        tk.Button(f, text="?  Como usar", command=self._open_help,
                  bg="#0f3460", fg="#eaeaea", font=("Segoe UI", 9),
                  relief="flat", cursor="hand2").pack(pady=(0, 4))

        tk.Button(f, text="❤  Apoiar via Pix", command=self._open_donation,
                  bg="#1a6b3a", fg="#ffffff", font=("Segoe UI", 9),
                  relief="flat", cursor="hand2").pack(pady=(0, 20))

    def _on_provider_change(self, _=None):
        self.hint_var.set(PROVIDER_HINTS.get(self.provider_var.get(), ""))
        self._update_url_state()

    def _update_url_state(self):
        provider = self.provider_var.get()
        # Base URL só editável em "custom"; nos demais é exibida como info
        if provider == "custom":
            self.base_url_entry.config(state="normal", fg="#eaeaea")
        else:
            known_url = KNOWN_PROVIDERS.get(provider, {}).get("base_url") or "(padrão do SDK)"
            self.base_url_var.set(known_url)
            self.base_url_entry.config(state="disabled", fg="#555577")

    def _region_text(self):
        r = self.config.get("region")
        if r:
            return f"x1={r['x1']} y1={r['y1']}  →  x2={r['x2']} y2={r['y2']}"
        return "Nenhuma selecionada"

    def _make_hotkey_entry(self, parent, var, row):
        entry = tk.Entry(parent, textvariable=var, width=12, bg="#16213e", fg="#e94560",
                         insertbackground="white", relief="flat", font=("Segoe UI", 10, "bold"),
                         justify="center", readonlybackground="#16213e", state="readonly")
        entry.grid(row=row, column=1, sticky="w", padx=8, pady=4)

        def on_click(e):
            entry.config(state="normal", fg="#ffffff")
            entry.delete(0, "end")
            entry.insert(0, "Pressione uma tecla...")
            entry.config(state="readonly")
            entry.bind("<KeyPress>", lambda ev: self._capture_key(ev, var, entry))
            entry.focus_set()

        entry.bind("<Button-1>", on_click)

    def _capture_key(self, event, var, entry):
        key = event.keysym.lower()
        if key in ("escape",):
            entry.config(fg="#e94560")
            var.set(var.get())
            return
        var.set(key)
        entry.config(fg="#e94560")
        entry.unbind("<KeyPress>")
        self._register_hotkeys()

    def _register_hotkeys(self):
        _unhook_all()
        _add_hotkey(self.hotkey_region_var.get(),    lambda: self.after(0, self._select_region))
        _add_hotkey(self.hotkey_translate_var.get(), lambda: self.after(0, self._toggle))
        _add_hotkey(self.hotkey_toggle_var.get(),    lambda: self.after(0, self._toggle_overlay))
        if IS_LINUX:
            _start_pynput()

    def _open_help(self):
        win = tk.Toplevel(self)
        win.title("Como usar o Game Translator")
        win.configure(bg="#1a1a2e")
        win.geometry("560x620")
        win.resizable(False, True)
        win.attributes("-topmost", True)

        canvas = tk.Canvas(win, bg="#1a1a2e", highlightthickness=0)
        sb = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        f = tk.Frame(canvas, bg="#1a1a2e")
        cw = canvas.create_window((0, 0), window=f, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        f.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        def section(title):
            tk.Label(f, text=title, bg="#1a1a2e", fg="#e94560",
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=20, pady=(16, 2))
            tk.Frame(f, bg="#e94560", height=1).pack(fill="x", padx=20)

        def text(msg):
            tk.Label(f, text=msg, bg="#1a1a2e", fg="#cccccc",
                     font=("Segoe UI", 9), wraplength=500, justify="left").pack(anchor="w", padx=28, pady=3)

        def step(n, msg):
            tk.Label(f, text=f"  {n}.  {msg}", bg="#1a1a2e", fg="#eaeaea",
                     font=("Segoe UI", 9), wraplength=490, justify="left").pack(anchor="w", padx=20, pady=2)

        def code(msg):
            tk.Label(f, text=msg, bg="#16213e", fg="#e94560",
                     font=("Courier New", 9), padx=10, pady=4).pack(anchor="w", padx=28, pady=2, fill="x")

        tk.Label(f, text="Como usar o Game Translator", bg="#1a1a2e", fg="#e94560",
                 font=("Segoe UI", 14, "bold")).pack(pady=(20, 4))
        tk.Label(f, text="Guia completo de configuração e uso", bg="#1a1a2e",
                 fg="#aaaaaa", font=("Segoe UI", 9)).pack(pady=(0, 8))

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

        section("6. Atalhos de teclado")
        text("Funcionam mesmo com o jogo em foco (rode como administrador):")
        code("F9  →  Abrir seletor de região")
        code("F10 →  Traduzir agora / Iniciar-Parar")
        code("F11 →  Mostrar / ocultar a tradução")
        text("Para trocar uma tecla: clique no campo do atalho e pressione a nova tecla.")

        section("7. Overlay (janela de tradução)")
        text("A tradução aparece numa janelinha preta sobre o jogo.")
        step(1, "Arraste pela barra vermelha no topo para mover")
        step(2, "Arraste o canto inferior direito para redimensionar")
        step(3, "Clique no ✕ para fechar temporariamente")
        text("")

        tk.Button(f, text="Fechar", command=win.destroy,
                  bg="#e94560", fg="white", relief="flat", cursor="hand2",
                  font=("Segoe UI", 10)).pack(pady=20)

    def _open_donation(self):
        win = tk.Toplevel(self)
        win.title("Apoiar o projeto")
        win.configure(bg="#1a1a2e")
        win.resizable(False, False)
        win.attributes("-topmost", True)

        tk.Label(win, text="Apoie o Game Translator", bg="#1a1a2e", fg="#e94560",
                 font=("Segoe UI", 14, "bold")).pack(pady=(20, 4))
        tk.Label(win, text="Se o app te ajudou, considere contribuir :)", bg="#1a1a2e",
                 fg="#aaaaaa", font=("Segoe UI", 9)).pack(pady=(0, 12))

        # QR Code
        try:
            from PIL import ImageTk
            img = Image.open("code.jpeg").resize((220, 220))
            photo = ImageTk.PhotoImage(img)
            lbl_img = tk.Label(win, image=photo, bg="#1a1a2e")
            lbl_img.image = photo
            lbl_img.pack(pady=(0, 8))
        except Exception:
            tk.Label(win, text="[QR Code não encontrado]", bg="#1a1a2e", fg="#555").pack()

        # Chave Pix
        PIX_KEY = "00020126580014BR.GOV.BCB.PIX01364df31385-39ad-4587-9a8b-72bb281d15905204000053039865802BR5917Jeferson Marciano6009SAO PAULO62140510AATRReYlC6630486CC"
        tk.Label(win, text="Chave Pix (copia e cola):", bg="#1a1a2e", fg="#eaeaea",
                 font=("Segoe UI", 9, "bold")).pack()

        frame_pix = tk.Frame(win, bg="#16213e")
        frame_pix.pack(padx=20, pady=4, fill="x")
        pix_entry = tk.Entry(frame_pix, font=("Segoe UI", 7), bg="#16213e", fg="#eaeaea",
                             relief="flat", readonlybackground="#16213e", state="readonly")
        pix_entry.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=6)
        pix_entry.config(state="normal")
        pix_entry.insert(0, PIX_KEY)
        pix_entry.config(state="readonly")

        def copiar():
            win.clipboard_clear()
            win.clipboard_append(PIX_KEY)
            btn_copy.config(text="Copiado!")
            win.after(2000, lambda: btn_copy.config(text="Copiar"))

        btn_copy = tk.Button(frame_pix, text="Copiar", command=copiar,
                             bg="#e94560", fg="white", relief="flat", cursor="hand2", padx=8)
        btn_copy.pack(side="right", pady=4, padx=4)

        # Link Nubank
        import webbrowser
        NUBANK_URL = "https://nubank.com.br/cobrar/9319j/6a2db4f7-c325-43b6-8f4b-6b919faf887e"
        tk.Button(win, text="Abrir link do Nubank", fg="#a259ff", bg="#1a1a2e",
                  relief="flat", cursor="hand2", font=("Segoe UI", 9, "underline"),
                  command=lambda: webbrowser.open(NUBANK_URL)).pack(pady=(4, 20))

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
            self.btn_start.config(text="▶  Traduzir Agora")
        else:
            self.interval_frame.grid()
            self.btn_start.config(text="▶  Iniciar Tradução")

    def _select_region(self):
        self.withdraw()
        selector = RegionSelector(self)
        self.wait_window(selector)
        if selector.result:
            self.config["region"] = selector.result
            self.region_label.config(text=self._region_text())
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
        save_config(self.config)
        self._register_hotkeys()
        self.status_var.set("Configurações salvas!")

    def _toggle(self):
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self):
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
            self.btn_start.config(state="disabled", text="Traduzindo...", bg="#555")
            self.status_var.set("Traduzindo...")
            self.thread = threading.Thread(target=self._translate_once, daemon=True)
        else:
            self.running = True
            self.btn_start.config(text="■  Parar", bg="#555")
            self.status_var.set("Rodando...")
            self.thread = threading.Thread(target=self._loop, daemon=True)

        self.thread.start()

    def _stop(self):
        self.running = False
        self.btn_start.config(text="▶  Iniciar Tradução", bg="#e94560")
        self.status_var.set("Parado")
        self.after(0, self._on_mode_change)  # restaura label correto do botão

    def _translate_once(self):
        try:
            frame = self.capture.capture_now()
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
            label = "▶  Traduzir Agora" if self.mode_var.get() == "once" else "▶  Iniciar Tradução"
            self.after(0, lambda: self.btn_start.config(state="normal", text=label, bg="#e94560"))

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
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.start_x = self.start_y = 0
        self.rect = None
        self.fill_rect = None
        self.dim_rects = []
        self.info_label = None

        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.55)
        self.configure(bg="#000010")
        self.attributes("-topmost", True)

        self.canvas = tk.Canvas(self, cursor="cross", bg="#000010", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Instrução no topo
        self.canvas.create_rectangle(0, 0, 9999, 52, fill="#000000", outline="")
        self.canvas.create_text(0, 26, text="  Arraste para selecionar a região das legendas   |   ESC para cancelar",
                                anchor="w", fill="white", font=("Segoe UI", 13))

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
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        # Escurece fora da seleção
        self.dim_rects = [
            self.canvas.create_rectangle(0,  0,  sw,  min(y1,y2), fill="#000010", outline=""),
            self.canvas.create_rectangle(0,  max(y1,y2), sw, sh,  fill="#000010", outline=""),
            self.canvas.create_rectangle(0,  min(y1,y2), min(x1,x2), max(y1,y2), fill="#000010", outline=""),
            self.canvas.create_rectangle(max(x1,x2), min(y1,y2), sw, max(y1,y2), fill="#000010", outline=""),
        ]

        # Área selecionada fica mais clara (quase transparente)
        self.fill_rect = self.canvas.create_rectangle(x1, y1, x2, y2, fill="#ffffff", outline="", stipple="gray12")

        # Borda vermelha
        self.rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline="#e94560", width=3)

        # Dimensões
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        self.info_label = self.canvas.create_text(
            (x1 + x2) // 2, min(y1, y2) - 10,
            text=f"{w} × {h} px",
            fill="#e94560", font=("Segoe UI", 11, "bold"), anchor="s"
        )

    def _on_release(self, e):
        x1, y1 = min(self.start_x, e.x), min(self.start_y, e.y)
        x2, y2 = max(self.start_x, e.x), max(self.start_y, e.y)
        if x2 - x1 > 20 and y2 - y1 > 10:
            self.result = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
