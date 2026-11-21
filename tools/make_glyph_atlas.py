#!/usr/bin/env python3
"""Regenerate the glyph atlas the plugin uses to draw its menu-bar numbers.

Dev-only: needs Pillow and Inter SemiBold (https://github.com/rsms/inter). The
plugin itself never imports Pillow — it only reads the atlas this prints.

    python3 tools/make_glyph_atlas.py /path/to/Inter-SemiBold.otf

Prints the GLYPH_* constants to paste into claude-usage.5m.py. The glyphs are
Inter's, so the atlas is a derivative of the font and stays under the SIL Open
Font License 1.1 (see licenses/Inter-OFL.txt); the rest of the plugin is MIT.
"""
import base64
import importlib.util
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
CHARS = "0123456789%·"           # everything the menu-bar title can print
SPACE = " "
SIZE = 22                        # px @2x: 16px digits, matching macOS's menu-bar text
HEIGHT = 22                      # cell height
BASELINE = 18                    # cap height is 16px, so caps span rows 2..17
PAD = 2                          # room for overhang and anti-aliasing either side


def main(font_path):
    spec = importlib.util.spec_from_file_location("plugin", os.path.join(HERE, "..", "claude-usage.5m.py"))
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)

    font = ImageFont.truetype(font_path, SIZE)
    cells, metrics, x = [], {}, 0
    for ch in CHARS:
        advance = font.getlength(ch)
        w = math.ceil(advance) + 2 * PAD
        cell = Image.new("L", (w, HEIGHT), 0)
        ImageDraw.Draw(cell).text((PAD, BASELINE), ch, font=font, fill=255, anchor="ls")
        cells.append(cell)
        metrics[ch] = (x, w, round(advance, 3))
        x += w
    metrics[SPACE] = (0, 0, round(font.getlength(SPACE), 3))

    atlas = Image.new("L", (x, HEIGHT), 0)
    for cell, ch in zip(cells, CHARS):
        atlas.paste(cell, (metrics[ch][0], 0))
    alpha = atlas.load()
    rows = [bytearray(b for i in range(x) for b in (0, 0, 0, alpha[i, y])) for y in range(HEIGHT)]
    png = plugin._png_encode_rgba(x, HEIGHT, rows)
    b64 = base64.b64encode(png).decode("ascii")

    def line(code, comment):
        print(f"{code:<18}  # {comment}")

    line(f"GLYPH_H = {HEIGHT}", f"cell height; baseline at row {BASELINE}, caps from row {BASELINE - 16}")
    line(f"GLYPH_CAP_MID = {BASELINE - 8}", "vertical middle of the digits, within a cell")
    line(f"GLYPH_PAD = {PAD}", "cells start this far left of the pen position")
    line("GLYPHS = {", "char: (x in atlas, cell width, advance), all px @2x")
    for ch, (gx, gw, adv) in metrics.items():
        print(f"    {ch!r}: ({gx}, {gw}, {adv}),")
    print("}")
    print(f'GLYPH_ATLAS = "{b64}"')


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf")
