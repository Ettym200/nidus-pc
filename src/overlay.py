import tkinter as tk
import threading

from src import ui_theme as theme

HANDLE_SIZE = 12
MAX_LIVE_LINES = 4
LIVE_LINE_HEIGHT = 34
LIVE_BASE_HEIGHT = 56


class Overlay:
    def __init__(self):
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait()

    def _run(self):
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.92)
        self._root.configure(bg=theme.SURFACE_ALT)
        self._root.withdraw()

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._w, self._h = 700, 110
        self._x = (sw - self._w) // 2
        self._y = sh - 160
        self._root.geometry(f"{self._w}x{self._h}+{self._x}+{self._y}")

        self._frame = tk.Frame(self._root, bg=theme.SURFACE_ALT, cursor="fleur")
        self._frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._label = tk.Label(
            self._frame, text="", bg=theme.SURFACE_ALT, fg=theme.TEXT,
            font=(theme.FONT, 16, "bold"),
            wraplength=self._w - 24,
            justify="center",
        )
        self._label.place(relx=0.5, rely=0.55, anchor="center")

        self._bar = tk.Frame(self._frame, bg=theme.ACCENT, height=8, cursor="fleur")
        self._bar.place(relx=0, rely=0, relwidth=1, height=8)

        self._handle = tk.Frame(
            self._root, bg=theme.ACCENT,
            width=HANDLE_SIZE, height=HANDLE_SIZE,
            cursor="size_nw_se",
        )
        self._handle.place(relx=1.0, rely=1.0, anchor="se")

        self._btn_close = tk.Label(
            self._bar, text="×", bg=theme.ACCENT, fg="white",
            font=(theme.FONT, 10, "bold"), cursor="hand2",
        )
        self._btn_close.place(relx=1.0, rely=0, anchor="ne", x=-6, y=0)
        self._btn_close.bind("<Button-1>", lambda e: self._do_hide())

        for w in (self._frame, self._bar, self._label):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_motion)

        self._handle.bind("<ButtonPress-1>", self._resize_start)
        self._handle.bind("<B1-Motion>", self._resize_motion)

        self._drag_ox = self._drag_oy = 0
        self._resize_ox = self._resize_oy = 0
        self._visible = False
        self._live_history: list[str] = []
        self._live_partial = ""

        self._ready.set()
        self._root.mainloop()

    def _drag_start(self, e):
        self._drag_ox = e.x_root - self._x
        self._drag_oy = e.y_root - self._y

    def _drag_motion(self, e):
        self._x = e.x_root - self._drag_ox
        self._y = e.y_root - self._drag_oy
        self._root.geometry(f"{self._w}x{self._h}+{self._x}+{self._y}")

    def _resize_start(self, e):
        self._resize_ox = e.x_root
        self._resize_oy = e.y_root
        self._resize_w0 = self._w
        self._resize_h0 = self._h

    def _resize_motion(self, e):
        self._w = max(200, self._resize_w0 + (e.x_root - self._resize_ox))
        self._h = max(50, self._resize_h0 + (e.y_root - self._resize_oy))
        self._label.config(wraplength=self._w - 24)
        self._root.geometry(f"{self._w}x{self._h}+{self._x}+{self._y}")

    def show(self, text: str):
        """Modo jogo: uma linha, substitui o texto."""
        if not text:
            return
        self._root.after(0, self._do_show, text)

    def show_partial(self, text: str):
        if not text:
            return
        self._root.after(0, self._do_show, text)

    def show_live(self, text: str, partial: bool = False):
        """Modo Live: mantém linhas anteriores visíveis."""
        if not text:
            return
        self._root.after(0, self._do_show_live, text, partial)

    def clear_live(self):
        self._root.after(0, self._do_clear_live)

    def _do_show(self, text: str):
        self._live_history = []
        self._live_partial = ""
        self._label.config(
            text=text,
            fg=theme.TEXT,
            font=(theme.FONT, 16, "bold"),
            justify="center",
        )
        if self._h != 110:
            self._h = 110
            self._root.geometry(f"{self._w}x{self._h}+{self._x}+{self._y}")
        if not self._visible:
            self._root.deiconify()
            self._visible = True

    def _do_clear_live(self):
        self._live_history = []
        self._live_partial = ""
        self._label.config(text="")

    def _do_show_live(self, text: str, partial: bool):
        if partial:
            self._live_partial = text
        else:
            self._live_partial = ""
            if text and (not self._live_history or self._live_history[-1] != text):
                self._live_history.append(text)
                if len(self._live_history) > MAX_LIVE_LINES:
                    self._live_history = self._live_history[-MAX_LIVE_LINES:]

        lines = list(self._live_history)
        if self._live_partial:
            lines.append(self._live_partial)

        if not lines:
            return

        # Linhas antigas em tom mais suave, última linha em destaque
        if len(lines) == 1:
            display = lines[0]
            fg = theme.ACCENT if partial else theme.TEXT
        else:
            older = lines[:-1]
            current = lines[-1]
            display = "\n".join(f"  {ln}" for ln in older) + f"\n▸ {current}"
            fg = theme.TEXT

        self._label.config(
            text=display,
            fg=fg,
            font=(theme.FONT, 14, "bold"),
            justify="left",
            wraplength=self._w - 28,
        )

        line_count = len(lines)
        new_h = max(110, min(300, LIVE_BASE_HEIGHT + line_count * LIVE_LINE_HEIGHT))
        if abs(new_h - self._h) > 4:
            self._h = new_h
            self._root.geometry(f"{self._w}x{self._h}+{self._x}+{self._y}")

        if not self._visible:
            self._root.deiconify()
            self._visible = True

    def _do_hide(self):
        self._root.withdraw()
        self._visible = False

    def hide(self):
        if self._root:
            self._root.after(0, self._do_hide)
