"""Renders docs/demo.gif — a terminal-style animation of `research.py ask`.

This is NOT a screen recording. A literal screen capture on this machine
would have shown the actual desktop (browser tabs, other apps) rather than
a terminal window, since CLI tool calls here don't render into any visible
window Pillow/ffmpeg could point a recorder at. Instead: the command and
answer text below were captured verbatim from a real run of

    python research.py ask "What is hybrid retrieval and how are lexical and semantic search combined?"

on 2026-07-19 (see comparisons/ and ROADMAP.md for how the corpus behind
this answer was built) and are replayed here as a typewriter animation —
the same idea as asciinema/vhs (record real terminal I/O, not desktop
pixels), implemented directly with Pillow since neither was installed.

Re-run this after changing COMMAND/ANSWER_PARAS/SOURCES to a different
real captured `ask` output to regenerate the GIF.
"""
import os
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")

W, H = 960, 620
BG = (13, 17, 23)              # GitHub-dark-ish terminal background
TITLEBAR = (22, 27, 34)
FG = (201, 209, 217)           # main text
PROMPT_COLOR = (63, 185, 80)   # green $
CMD_COLOR = (121, 192, 255)    # cyan-ish command text
DIM = (110, 118, 129)          # sources / dim text
ACCENT = (210, 168, 255)       # citation markers

FONT_PATH = r"C:\Windows\Fonts\consola.ttf"
FONT_SIZE = 16
LINE_H = 24
PAD_X = 28
TITLEBAR_H = 40
BODY_TOP = TITLEBAR_H + 24
WRAP_COLS = 78

font = ImageFont.truetype(FONT_PATH, FONT_SIZE)


def new_canvas():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, TITLEBAR_H], fill=TITLEBAR)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([16 + i * 22, 14, 16 + i * 22 + 12, 26], fill=c)
    d.text((W / 2, TITLEBAR_H / 2), "research.py — ask", font=font, fill=DIM, anchor="mm")
    return img, d


def draw_lines(d, lines, y_start):
    """lines: (text, color) or (text, color, [(substring, color), ...]) to recolor within text."""
    y = y_start
    for entry in lines:
        text, color = entry[0], entry[1]
        segments = entry[2] if len(entry) > 2 else None
        if segments:
            x = PAD_X
            remaining = text
            while remaining:
                matched = False
                for seg, seg_color in segments:
                    if remaining.startswith(seg):
                        d.text((x, y), seg, font=font, fill=seg_color)
                        x += d.textlength(seg, font=font)
                        remaining = remaining[len(seg):]
                        matched = True
                        break
                if not matched:
                    ch = remaining[0]
                    d.text((x, y), ch, font=font, fill=color)
                    x += d.textlength(ch, font=font)
                    remaining = remaining[1:]
        else:
            d.text((PAD_X, y), text, font=font, fill=color)
        y += LINE_H
    return y


def wrap_paragraph(text, cols=WRAP_COLS):
    if not text:
        return [""]
    return textwrap.wrap(text, width=cols, break_long_words=False, break_on_hyphens=False) or [""]


def build_static_lines(command, answer_paragraphs, sources):
    lines = []
    lines.append((f"$ {command}", None, [("$ ", PROMPT_COLOR), (command, CMD_COLOR)]))
    lines.append(("", FG))
    for para in answer_paragraphs:
        for wl in wrap_paragraph(para):
            segs = [("[1]", ACCENT), ("[2]", ACCENT), ("[3]", ACCENT)]
            lines.append((wl, FG, segs))
        lines.append(("", FG))
    lines.append(("---", DIM))
    lines.append(("Sources:", DIM))
    for s in sources:
        for wl in wrap_paragraph(s, cols=WRAP_COLS):
            lines.append((wl, DIM))
    return lines


# --- Verbatim from a real `research.py ask` run, 2026-07-19 ---
COMMAND = 'python research.py ask "What is hybrid retrieval and how are lexical and semantic search combined?"'
ANSWER_PARAS = [
    "Hybrid retrieval is the fusion of lexical and semantic retrieval approaches [1]. Lexical search retrieves documents based on exact term matching, while semantic search uses deep learning models (like BERT) to encode queries and documents into vector representations that capture their semantic similarity, reducing retrieval to a nearest neighbor search [1]. Because these two approaches are hypothesized to be complementary in how they model relevance, hybrid retrieval combines them [1].",
    "The combination is performed by fusing the ranked lists produced separately by a lexical search system and a semantic search system: for a query q, and ranked document lists R_Lex (from lexical retrieval) and R_Sem (from semantic retrieval), the task is to construct a final, unified ranking [1].",
]
SOURCES = ["[1] An Analysis of Fusion Functions for Hybrid Retrieval  (work_id=35)"]

frames = []
durations = []


def add_frame(img, ms):
    frames.append(img)  # keep RGB; quantized to a shared palette at the end
    durations.append(ms)


# Scene 1: typewriter the command
for i in range(0, len(COMMAND) + 1, 2):
    img, d = new_canvas()
    partial = COMMAND[:i]
    cursor = "▌" if (i // 2) % 2 == 0 else " "
    d.text((PAD_X, BODY_TOP), "$ ", font=font, fill=PROMPT_COLOR)
    x = PAD_X + d.textlength("$ ", font=font)
    d.text((x, BODY_TOP), partial + cursor, font=font, fill=CMD_COLOR)
    add_frame(img, 18)
img, d = new_canvas()
d.text((PAD_X, BODY_TOP), "$ ", font=font, fill=PROMPT_COLOR)
x = PAD_X + d.textlength("$ ", font=font)
d.text((x, BODY_TOP), COMMAND, font=font, fill=CMD_COLOR)
add_frame(img, 500)

# Scene 2: thinking dots (brief, honest nod to the real API latency)
for dots in ["", ".", "..", "...", "..", "."]:
    img, d = new_canvas()
    d.text((PAD_X, BODY_TOP), "$ ", font=font, fill=PROMPT_COLOR)
    x = PAD_X + d.textlength("$ ", font=font)
    d.text((x, BODY_TOP), COMMAND, font=font, fill=CMD_COLOR)
    d.text((PAD_X, BODY_TOP + LINE_H * 1.5), "thinking" + dots, font=font, fill=DIM)
    add_frame(img, 220)

# Scene 3: progressively reveal the real answer, one wrapped line at a time
full_lines = build_static_lines(COMMAND, ANSWER_PARAS, SOURCES)
for n in range(1, len(full_lines) + 1):
    img, d = new_canvas()
    draw_lines(d, full_lines[:n], BODY_TOP)
    add_frame(img, 90)

# Hold final frame before the loop restarts
img, d = new_canvas()
draw_lines(d, full_lines, BODY_TOP)
add_frame(img, 3200)

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.gif")

# Explicit shared palette: per-frame adaptive quantization drops the tiny
# traffic-light dots (few pixels, outvoted by the large background area)
# and remaps them to the nearest big-area color, causing flicker. Building
# the palette from exactly the known colors gives each one its own slot.
known_colors = [BG, TITLEBAR, FG, PROMPT_COLOR, CMD_COLOR, DIM, ACCENT,
                (255, 95, 86), (255, 189, 46), (39, 201, 63)]
swatch = Image.new("RGB", (len(known_colors), 1))
for i, c in enumerate(known_colors):
    swatch.putpixel((i, 0), c)
palette_source = swatch.convert("P", palette=Image.ADAPTIVE, colors=len(known_colors))

quantized = [f.quantize(palette=palette_source, dither=Image.NONE) for f in frames]
quantized[0].save(
    out_path, save_all=True, append_images=quantized[1:], duration=durations, loop=0, optimize=False
)
print("frames:", len(quantized), "->", out_path)
