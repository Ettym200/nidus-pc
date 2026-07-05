import mss
import numpy as np
import time
import hashlib
from PIL import Image


class ScreenCapture:
    def __init__(self, region: dict, interval: float = 1.5):
        self.region = region
        self.interval = interval
        self._last_hash = None

    def _capture_frame(self) -> Image.Image:
        with mss.mss() as sct:
            monitor = {
                "left": self.region["x1"],
                "top": self.region["y1"],
                "width": self.region["x2"] - self.region["x1"],
                "height": self.region["y2"] - self.region["y1"],
            }
            raw = sct.grab(monitor)
            return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    def _hash(self, img: Image.Image) -> str:
        # Converte pra escala de cinza e binariza (só texto de alto contraste fica)
        gray = np.array(img.convert("L"))
        # Threshold: pixels muito claros (texto branco) ou muito escuros (texto preto)
        binary = ((gray > 200) | (gray < 50)).astype(np.uint8) * 255
        # Reduz tamanho antes de hashear para ser rápido
        small = Image.fromarray(binary).resize((128, 32))
        return hashlib.md5(np.array(small).tobytes()).hexdigest()

    def stream(self):
        """Gera (frame, changed) continuamente."""
        while True:
            start = time.time()
            frame = self._capture_frame()
            h = self._hash(frame)
            changed = h != self._last_hash
            if changed:
                self._last_hash = h
            yield frame, changed
            elapsed = time.time() - start
            sleep = max(0, self.interval - elapsed)
            time.sleep(sleep)
