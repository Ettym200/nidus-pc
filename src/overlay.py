import tkinter as tk
import threading

from src import ui_theme as theme

HANDLE_SIZE = 12
MAX_LIVE_LINES = 4
MIN_WINDOW_HEIGHT = 110

CHROMA = "#010103"
OVERLAY_ALPHA_FALLBACK = 0.78
BAR_HEIGHT = 4
TEXT_PADDING = 14
TEXT_MARGIN = 8
OUTLINE_COLOR = "#000000"
OUTLINE_WIDTH = 2


class Overlay:
    def __init__(self):
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait()

    def _apply_transparency(self):
        try:
            self._root.configure(bg=CHROMA)
            self._root.attributes("-transparentcolor", CHROMA)
            self._transparent = True
        except tk.TclError:
            self._root.attributes("-alpha", OVERLAY_ALPHA_FALLBACK)
            self._transparent = False

    def _run(self):
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.withdraw()
        self._apply_transparency()

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._screen_h = sh
        self._w, self._h = 700, MIN_WINDOW_HEIGHT
        self._x = (sw - self._w) // 2
        self._y = sh - 160
        self._root.geometry(f"{self._w}x{self._h}+{self._x}+{self._y}")

        bg = CHROMA if getattr(self, "_transparent", False) else theme.SURFACE_ALT

        self._frame = tk.Frame(self._root, bg=bg, cursor="fleur")
        self._frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._canvas = tk.Canvas(
            self._frame, bg=bg, highlightthickness=0, bd=0,
            width=self._w, height=max(50, self._h - BAR_HEIGHT),
        )
        self._canvas.place(relx=0, rely=0, relwidth=1, relheight=1, y=BAR_HEIGHT)

        self._bar = tk.Frame(self._frame, bg=theme.ACCENT, height=BAR_HEIGHT, cursor="fleur")
        self._bar.place(relx=0, rely=0, relwidth=1, height=4)

        self._handle = tk.Frame(
            self._root, bg=theme.ACCENT,
            width=HANDLE_SIZE, height=HANDLE_SIZE,
            cursor="size_nw_se",
        )
        self._handle.place(relx=1.0, rely=1.0, anchor="se")

        self._btn_close = tk.Label(
            self._bar, text="×", bg=theme.ACCENT, fg="white",
            font=(theme.FONT, 9, "bold"), cursor="hand2",
        )
        self._btn_close.place(relx=1.0, rely=0, anchor="ne", x=-4, y=-1)
        self._btn_close.bind("<Button-1>", lambda e: self._do_hide())

        for w in (self._frame, self._bar, self._canvas):
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

    def _outline_offsets(self):
        offsets = []
        for r in range(1, OUTLINE_WIDTH + 1):
            for dx in (-r, 0, r):
                for dy in (-r, 0, r):
                    if dx == 0 and dy == 0:
                        continue
                    offsets.append((dx, dy))
        return offsets

    def _text_origin(self, justify: str, canvas_h: int):
        inset = TEXT_PADDING + OUTLINE_WIDTH
        if justify == "center":
            return "center", self._w // 2, canvas_h // 2
        return "nw", inset, inset

    def _measure_text_bbox(self, text: str, font, justify: str, wrap_width: int):
        if not text:
            return None
        canvas_h = max(50, self._h - BAR_HEIGHT)
        anchor, x, y = self._text_origin(justify, canvas_h)
        measure = self._canvas.create_text(
            x, y, text=text, font=font, width=wrap_width,
            anchor=anchor, justify=justify,
        )
        bbox = self._canvas.bbox(measure)
        self._canvas.delete(measure)
        return bbox

    def _required_window_height(self, text: str, font, justify: str, wrap_width: int) -> int:
        bbox = self._measure_text_bbox(text, font, justify, wrap_width)
        if not bbox:
            return MIN_WINDOW_HEIGHT
        text_h = bbox[3] - bbox[1]
        inset = TEXT_PADDING + OUTLINE_WIDTH
        canvas_h = text_h + inset * 2 + TEXT_MARGIN * 2
        total = BAR_HEIGHT + canvas_h
        max_h = int(self._screen_h * 0.5)
        return max(MIN_WINDOW_HEIGHT, min(max_h, total))

    def _resize_window(self, height: int):
        if abs(height - self._h) <= 2:
            return
        self._h = height
        self._root.geometry(f"{self._w}x{self._h}+{self._x}+{self._y}")
        self._canvas.config(width=self._w, height=max(50, self._h - BAR_HEIGHT))

    def _draw_text(self, text: str, fg: str, font, justify: str, wrap_width: int):
        self._canvas.delete("all")
        if not text:
            return

        needed_h = self._required_window_height(text, font, justify, wrap_width)
        self._resize_window(needed_h)

        canvas_h = max(50, self._h - BAR_HEIGHT)
        self._canvas.config(width=self._w, height=canvas_h)
        anchor, x, y = self._text_origin(justify, canvas_h)

        bbox = self._measure_text_bbox(text, font, justify, wrap_width)
        pad_x, pad_y = TEXT_MARGIN + OUTLINE_WIDTH, TEXT_MARGIN + OUTLINE_WIDTH
        if bbox:
            self._canvas.create_rectangle(
                bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y,
                fill="black", outline="", stipple="gray50",
            )

        for dx, dy in self._outline_offsets():
            self._canvas.create_text(
                x + dx, y + dy, text=text, fill=OUTLINE_COLOR, font=font,
                width=wrap_width, anchor=anchor, justify=justify,
            )

        self._canvas.create_text(
            x, y, text=text, fill=fg, font=font,
            width=wrap_width, anchor=anchor, justify=justify,
        )

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
        self._h = max(MIN_WINDOW_HEIGHT, self._resize_h0 + (e.y_root - self._resize_oy))
        self._canvas.config(width=self._w, height=max(50, self._h - BAR_HEIGHT))
        self._root.geometry(f"{self._w}x{self._h}+{self._x}+{self._y}")

    def show(self, text: str):
        if not text:
            return
        self._root.after(0, self._do_show, text)

    def show_partial(self, text: str):
        if not text:
            return
        self._root.after(0, self._do_show, text)

    def show_live(self, text: str, partial: bool = False):
        if not text:
            return
        self._root.after(0, self._do_show_live, text, partial)

    def clear_live(self):
        self._root.after(0, self._do_clear_live)

    def _do_show(self, text: str):
        self._live_history = []
        self._live_partial = ""
        wrap = self._w - 28
        self._draw_text(text, "#ffffff", (theme.FONT, 16, "bold"), "center", wrap)
        if not self._visible:
            self._root.deiconify()
            self._visible = True

    def _do_clear_live(self):
        self._live_history = []
        self._live_partial = ""
        self._draw_text("", "#ffffff", (theme.FONT, 14, "bold"), "left", self._w - 28)

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

        if len(lines) == 1:
            display = lines[0]
            fg = theme.ACCENT if partial else "#ffffff"
        else:
            older = lines[:-1]
            current = lines[-1]
            display = "\n".join(f"  {ln}" for ln in older) + f"\n▸ {current}"
            fg = "#ffffff"

        wrap = self._w - 28
        self._draw_text(display, fg, (theme.FONT, 14, "bold"), "left", wrap)

        if not self._visible:
            self._root.deiconify()
            self._visible = True

    def _do_hide(self):
        self._root.withdraw()
        self._visible = False

    def hide(self):
        if self._root:
            self._root.after(0, self._do_hide)
