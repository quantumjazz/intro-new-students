#!/usr/bin/env python3
"""Write the deck's QR codes as crisp SVGs.

    python3 tools/make_qr.py [GAME_URL]

- The game, https://intro.visiometrica.com by default: img/qr-intro.svg
  (slides 1 and 2) and intro-game/frontend/qr.svg (admin page).
- The slides on GitHub Pages: img/qr-slides.svg (last slide).

Needs the `qrcode` package (pip install qrcode); it only builds the module
matrix, the SVG is ours.
"""

import sys
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_L

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "https://intro.visiometrica.com"
SLIDES_URL = "https://quantumjazz.github.io/intro-new-students/vavedenie.html"
INK = "#0E2A2F"


def qr_svg(url, border=2):
    # Low error correction keeps the code at version 2 (25×25 modules), so
    # each module stays large enough to scan from the back of the hall.
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_L, border=border)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()  # includes the border
    size = len(matrix)
    path = []
    for y, row in enumerate(matrix):
        x = 0
        while x < size:
            if row[x]:
                start = x
                while x < size and row[x]:
                    x += 1
                path.append(f"M{start} {y}h{x - start}v1h{start - x}z")
            else:
                x += 1
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size * 12}" height="{size * 12}" shape-rendering="crispEdges">'
        f'<title>{url}</title>'
        f'<path fill="{INK}" d="{"".join(path)}"/></svg>\n'
    ), qr.version


def main():
    game_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    jobs = [
        (game_url, [ROOT / "img" / "qr-intro.svg", ROOT / "intro-game" / "frontend" / "qr.svg"]),
        (SLIDES_URL, [ROOT / "img" / "qr-slides.svg"]),
    ]
    for url, targets in jobs:
        svg, version = qr_svg(url)
        for target in targets:
            target.write_text(svg, encoding="utf-8")
            print(f"wrote {target.relative_to(ROOT)}  ({url}, version {version})")


if __name__ == "__main__":
    main()
