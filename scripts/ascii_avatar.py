"""Turn the portrait into coloured ASCII art for the profile card.

One-off helper, run locally when the photo changes. The input needs a transparent
background (e.g. cut out with rembg), like card/portrait.png:
    pip install pillow
    python3 scripts/ascii_avatar.py card/portrait.png > card/avatar.json

Output is a list of rows, each a list of [text, "#rrggbb" or null] runs.
"""

import json
import sys

from PIL import Image, ImageChops, ImageFilter, ImageOps

WIDTH = 70  # columns
CHAR_ASPECT = 0.52  # cell width / line height, matching ASCII_FONT and ASCII_LINE in build_card.py
CROP = (50, 0, 350, 320)  # head and shoulders
RAMP = "@%#*+=-:."  # dark -> light
EDGE_STRENGTH = 0.6  # darken outlines (glasses, eyes, mouth) so they survive the downscale
ALPHA_CUTOFF = 110


def main(path):
    img = Image.open(path).convert("RGBA").crop(CROP)
    alpha = img.split()[3]
    rgb = Image.new("RGB", img.size, (255, 255, 255))
    rgb.paste(img, mask=alpha)

    # find edges at 2x, then darken them into the brightness map
    big = ImageOps.autocontrast(rgb.resize((img.width * 2, img.height * 2), Image.LANCZOS).convert("L"), cutoff=1)
    edges = big.filter(ImageFilter.GaussianBlur(1.2)).filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges, cutoff=2).filter(ImageFilter.MaxFilter(3))
    shade = ImageChops.subtract(big, edges.point(lambda v: int(v * EDGE_STRENGTH)))

    size = (WIDTH, int(WIDTH * img.height / img.width * CHAR_ASPECT))
    colour = rgb.resize(size, Image.LANCZOS)
    shade = shade.resize(size, Image.BOX)
    alpha = alpha.resize(size, Image.LANCZOS)

    rows = []
    for y in range(size[1]):
        runs = []
        for x in range(size[0]):
            if alpha.getpixel((x, y)) < ALPHA_CUTOFF:
                char, hex_ = " ", None
            else:
                char = RAMP[min(shade.getpixel((x, y)) * len(RAMP) // 256, len(RAMP) - 1)]
                # 4 bits per channel keeps runs long and the SVG small
                hex_ = "#" + "".join(f"{c & 0xF0 | 0x08:02x}" for c in colour.getpixel((x, y)))
            if runs and runs[-1][1] == hex_:
                runs[-1][0] += char
            else:
                runs.append([char, hex_])
        if runs and runs[-1][1] is None:
            runs.pop()
        rows.append(runs)

    while rows and not rows[0]:
        rows.pop(0)
    while rows and not rows[-1]:
        rows.pop()
    json.dump(rows, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(sys.argv[1])
