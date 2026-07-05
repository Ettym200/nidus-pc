import tkinter as tk
import threading

from src import ui_theme as theme

HANDLE_SIZE = 12


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
        self._label.place(relx=0.5, rely=0.52, anchor="center")

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
        if not text:
            return
        self._root.after(0, self._do_show, text)

    def _do_show(self, text: str):
        self._label.config(text=text)
        if not self._visible:
            self._root.deiconify()
            self._visible = True

    def _do_hide(self):
        self._root.withdraw()
        self._visible = False

    def hide(self):
        if self._root:
            self._root.after(0, self._do_hide)
