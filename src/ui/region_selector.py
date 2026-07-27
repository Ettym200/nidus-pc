import tkinter as tk

from src import ui_theme as theme


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
        self.bind("<Escape>", lambda _e: self.destroy())

    def _clear(self):
        for item in [self.rect, self.fill_rect, self.info_label] + self.dim_rects:
            if item:
                self.canvas.delete(item)
        self.dim_rects = []
        self.rect = self.fill_rect = self.info_label = None

    def _on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self._clear()

    def _on_drag(self, event):
        self._clear()
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y
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

    def _on_release(self, event):
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        if x2 - x1 > 20 and y2 - y1 > 10:
            ml, mt = self.monitor["left"], self.monitor["top"]
            self.result = {"x1": x1 + ml, "y1": y1 + mt, "x2": x2 + ml, "y2": y2 + mt}
        self.destroy()
