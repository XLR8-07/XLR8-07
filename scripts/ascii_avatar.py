"""Turn the GitHub avatar into ASCII art for the profile card.

One-off helper, run locally when the avatar changes:
    pip install pillow
    python3 scripts/ascii_avatar.py > card/avatar.txt
"""

import io
import sys
import urllib.request

from PIL import Image, ImageOps

AVATAR_URL = "https://avatars.githubusercontent.com/u/43420293?v=4&s=400"
WIDTH = 40  # columns
CHAR_ASPECT = 0.5  # a monospace cell is roughly twice as tall as it is wide
RAMP = "@%#*+=-:. "  # dark -> light
BG_TOLERANCE = 28  # how close to the corner colour still counts as background


def main():
    raw = urllib.request.urlopen(AVATAR_URL).read()
    img = Image.open(io.BytesIO(raw)).convert("RGB")

    height = int(WIDTH * img.height / img.width * CHAR_ASPECT)
    small = img.resize((WIDTH, height), Image.LANCZOS)
    grey = ImageOps.autocontrast(small.convert("L"), cutoff=2)
    bg = small.getpixel((0, 0))

    lines = []
    for y in range(height):
        row = []
        for x in range(WIDTH):
            px = small.getpixel((x, y))
            if max(abs(a - b) for a, b in zip(px, bg)) < BG_TOLERANCE:
                row.append(" ")
                continue
            level = grey.getpixel((x, y)) * (len(RAMP) - 1) // 255
            row.append(RAMP[level])
        lines.append("".join(row).rstrip())

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
