"""Gera icon.ico com multiplos tamanhos a partir de icon.png."""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "icon.png"
DST = ROOT / "icon.ico"

SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]


def main():
    img = Image.open(SRC).convert("RGBA")
    img.save(DST, format="ICO", sizes=SIZES)
    print(f"Gerado: {DST}")


if __name__ == "__main__":
    main()
