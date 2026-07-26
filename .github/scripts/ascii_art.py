"""Converts the GitHub avatar into a grid of colored monospace characters.

Run standalone to regenerate ascii_art.json whenever the avatar changes:
    python3 .github/scripts/ascii_art.py
"""
import io
import json
import os

import requests
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

USERNAME = "sarbojitrana"
OUT_PATH = os.path.join(os.path.dirname(__file__), "ascii_art.json")

# Dense -> sparse. Index 0 renders as a blank cell (lets the card background
# show through), the rest ramp up in "ink" density.
RAMP = " ..::--==++**##%%@@"

COLS = 44
CELL_ASPECT = 0.52  # monospace char width / height, used to pick ROWS
GAMMA = 0.8  # <1 spreads midtones out so more cells earn a character


def current_avatar_url() -> str:
    resp = requests.get(f"https://api.github.com/users/{USERNAME}", timeout=30)
    resp.raise_for_status()
    return resp.json()["avatar_url"]


def fetch_avatar() -> Image.Image:
    resp = requests.get(current_avatar_url(), timeout=30)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert("RGB")


def build_grid(img: Image.Image, cols: int = COLS, rows: int | None = None):
    # rows defaults to what keeps the sampled grid roughly square-looking;
    # callers that need the art to fill a specific card height pass rows
    # explicitly, which stretches the sampling instead (a minor, acceptable
    # distortion for abstract colored ascii art).
    rows = max(1, rows if rows is not None else round(cols * CELL_ASPECT))
    img = ImageOps.autocontrast(img, cutoff=1)
    small = img.resize((cols, rows), Image.LANCZOS)
    small = ImageEnhance.Color(small).enhance(1.5)
    small = ImageEnhance.Contrast(small).enhance(1.2)
    small = ImageEnhance.Brightness(small).enhance(1.35)
    small = small.filter(ImageFilter.SMOOTH)

    pixels = small.load()
    grid = []
    for y in range(rows):
        row = []
        for x in range(cols):
            r, g, b = pixels[x, y]
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            mx, mn = max(r, g, b), min(r, g, b)
            saturation = 0 if mx == 0 else (mx - mn) / mx
            intensity = 0.5 * luminance + 0.5 * saturation
            intensity = intensity ** GAMMA
            idx = min(len(RAMP) - 1, int(intensity * len(RAMP)))
            char = RAMP[idx]
            if char == " ":
                row.append(None)
            else:
                # blend each cell's color toward white so it reads as bright
                # against the card's dark background instead of murky
                br = round(r + (255 - r) * 0.22)
                bg = round(g + (255 - g) * 0.22)
                bb = round(b + (255 - b) * 0.22)
                row.append({"c": char, "hex": "#%02x%02x%02x" % (br, bg, bb)})
        grid.append(row)
    return grid


def main():
    img = fetch_avatar()
    grid = build_grid(img)
    with open(OUT_PATH, "w") as f:
        json.dump({"cols": COLS, "rows": len(grid), "grid": grid}, f)
    print(f"Wrote {OUT_PATH}: {COLS}x{len(grid)}")


if __name__ == "__main__":
    main()
