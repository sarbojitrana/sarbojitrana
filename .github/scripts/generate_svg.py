"""Renders the neofetch-style profile card as an SVG.

Combines a freshly re-sampled ASCII-art avatar (pulled live each run, so it
always matches the current GitHub profile picture) with live stats
(stats.py, loc.py) and static bio content (config.py) into one wide card.

Every glyph is placed at an explicit x/y with textLength forced, so the
grid lines up regardless of which monospace font the viewer's browser
actually substitutes.
"""
import html
import os

import ascii_art
import config
import loc
import stats

HERE = os.path.dirname(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
ASSETS_DIR = os.path.join(REPO_ROOT, "assets")

FONT_FAMILY = "'JetBrains Mono','Fira Code',Consolas,Menlo,monospace"
FONT_SIZE = 16
CHAR_W = 9.9
LINE_H = 21
PAD = 20
GAP = 26

ART_LINE_H = 16
ART_CHAR_W = round(ART_LINE_H * 0.52, 2)

LABEL_DOT_COLS = 26
VALUE_COL = LABEL_DOT_COLS + 2

THEMES = {
    "dark": {
        "bg": "#1c2128",
        "border": "#444c56",
        "user": "#8ddb8c",
        "label": "#8fc7ff",
        "dots": "#636e7b",
        "value": "#e2e8ee",
        "heading": "#ffb771",
        "muted": "#9ea7b3",
        "add": "#56d364",
        "del": "#ff7b72",
        "swatches": [
            "#1c2128", "#ff7b72", "#56d364", "#e3b341",
            "#79c0ff", "#d2a8ff", "#56d4dd", "#e2e8ee",
        ],
    },
}


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def mono_run(x, y, segments, theme_color_default):
    """segments: list of (text, color|None). Returns an SVG <text> element
    with one tspan per segment, each pinned to an explicit x via textLength
    so layout never depends on the viewer's actual font metrics."""
    parts = [f'<text x="{x:.2f}" y="{y:.2f}" font-family="{FONT_FAMILY}" font-size="{FONT_SIZE}" xml:space="preserve">']
    cursor = x
    for text, color in segments:
        if text == "":
            continue
        width = len(text) * CHAR_W
        fill = color or theme_color_default
        parts.append(
            f'<tspan x="{cursor:.2f}" y="{y:.2f}" fill="{fill}" '
            f'textLength="{width:.2f}" lengthAdjust="spacingAndGlyphs">{esc(text)}</tspan>'
        )
        cursor += width
    parts.append("</text>")
    return "".join(parts)


def render_art(grid, x0, y0, theme, art_line_h, art_char_w):
    out = []
    for row_i, row in enumerate(grid):
        y = y0 + row_i * art_line_h + art_line_h * 0.8
        segments = []
        run_text = ""
        run_color = None
        for cell in row:
            color = cell["hex"] if cell else theme["bg"]
            char = cell["c"] if cell else " "
            if color != run_color and run_text:
                segments.append((run_text, run_color))
                run_text = ""
            run_color = color
            run_text += char
        if run_text:
            segments.append((run_text, run_color))
        out.append(mono_run_art(x0, y, segments, art_line_h, art_char_w))
    return "".join(out)


def mono_run_art(x, y, segments, art_line_h, art_char_w):
    parts = [f'<text x="{x:.2f}" y="{y:.2f}" font-family="{FONT_FAMILY}" font-size="{art_line_h:.2f}" xml:space="preserve">']
    cursor = x
    for text, color in segments:
        width = len(text) * art_char_w
        parts.append(
            f'<tspan x="{cursor:.2f}" y="{y:.2f}" fill="{color}" '
            f'textLength="{width:.2f}" lengthAdjust="spacingAndGlyphs">{esc(text)}</tspan>'
        )
        cursor += width
    parts.append("</text>")
    return "".join(parts)


def measure_text_height(art_rows_unused=None) -> float:
    """Mirrors the y-cursor advances in build_svg without needing real data,
    so the art column's line height can be solved to exactly fill it."""
    y = PAD + LINE_H * 0.8
    y += LINE_H * 1.4  # prompt line
    for label, _ in config.FIELDS:
        y += LINE_H * 0.6 if label is None else LINE_H
    y += LINE_H * 0.5 + LINE_H * 1.4  # Contact header
    y += LINE_H * len(config.CONTACT)
    y += LINE_H * 0.5 + LINE_H * 1.4  # GitHub Stats header
    y += LINE_H  # Repos
    y += LINE_H  # Commits
    y += LINE_H * 1.8  # Lines of Code -> swatches baseline
    y += LINE_H * 1.2  # after swatches
    return y


def field_line(x, y, label, value, theme):
    if label is None:
        return ""
    dots_count = max(1, LABEL_DOT_COLS - len(label) - 1)
    segments = [
        (f"{label}", theme["label"]),
        (" " + ("." * dots_count) + " ", theme["dots"]),
        (str(value), theme["value"]),
    ]
    return mono_run(x, y, segments, theme["value"])


def section_header(x, y, title, total_chars, theme):
    dash_count = max(0, total_chars - len(title) - 2)
    segments = [
        ("- " + title + " ", theme["heading"]),
        ("-" * dash_count, theme["border"]),
    ]
    return mono_run(x, y, segments, theme["border"])


VALUE_START_COL = LABEL_DOT_COLS + 1


def compute_total_chars(data: dict) -> int:
    max_chars = len(f"{config.PROMPT_USER}@{config.PROMPT_HOST}") + 4

    def track(value):
        nonlocal max_chars
        max_chars = max(max_chars, VALUE_START_COL + len(str(value)))

    for label, value in config.FIELDS:
        if label is not None:
            track(value)
    for label, value in config.CONTACT:
        track(value)

    s, l = data["stats"], data["loc"]
    repos_val = f"{s['repos']}" + (f" {{Contrib: {s['contributed']}}}" if s["contributed"] is not None else "")
    track(repos_val + f" | Stars: {s['stars']:,}")
    commits_val = f"{s['commits']:,}" if s["commits"] is not None else "pending PAT"
    track(commits_val + f" | Followers: {s['followers']:,}")
    track(f"{l['net']:,} ({l['additions']:,}++, {l['deletions']:,}--)")

    return max_chars + 2


def build_svg(theme_name: str, data: dict) -> str:
    theme = THEMES[theme_name]
    art_grid = data["art_grid"]
    art_rows = len(art_grid)
    art_cols = len(art_grid[0]) if art_rows else 0
    art_line_h, art_char_w = ART_LINE_H, ART_CHAR_W

    right_x = PAD + art_cols * art_char_w + GAP
    total_chars = compute_total_chars(data)

    lines = []
    y = PAD + LINE_H * 0.8

    prompt = f"{config.PROMPT_USER}@{config.PROMPT_HOST}"
    lines.append(mono_run(right_x, y, [
        (prompt + " ", theme["user"]),
        ("-" * max(0, total_chars - len(prompt) - 1), theme["border"]),
    ], theme["border"]))
    y += LINE_H * 1.4

    for label, value in config.FIELDS:
        if label is None:
            y += LINE_H * 0.6
            continue
        lines.append(field_line(right_x, y, label, value, theme))
        y += LINE_H

    y += LINE_H * 0.5
    lines.append(section_header(right_x, y, "Contact", total_chars, theme))
    y += LINE_H * 1.4
    for label, value in config.CONTACT:
        lines.append(field_line(right_x, y, label, value, theme))
        y += LINE_H

    y += LINE_H * 0.5
    lines.append(section_header(right_x, y, "GitHub Stats", total_chars, theme))
    y += LINE_H * 1.4

    s = data["stats"]
    l = data["loc"]
    repos_val = f"{s['repos']}" + (f" {{Contrib: {s['contributed']}}}" if s["contributed"] is not None else "")
    lines.append(field_line(right_x, y, "Repos", repos_val + f" | Stars: {s['stars']:,}", theme))
    y += LINE_H
    commits_val = f"{s['commits']:,}" if s["commits"] is not None else "pending PAT"
    lines.append(field_line(right_x, y, "Commits", commits_val + f" | Followers: {s['followers']:,}", theme))
    y += LINE_H

    loc_label = "Lines of Code"
    dots_count = max(1, LABEL_DOT_COLS - len(loc_label) - 1)
    segments = [
        (loc_label, theme["label"]),
        (" " + ("." * dots_count) + " ", theme["dots"]),
        (f"{l['net']:,} (", theme["value"]),
        (f"{l['additions']:,}++", theme["add"]),
        (", ", theme["value"]),
        (f"{l['deletions']:,}--", theme["del"]),
        (")", theme["value"]),
    ]
    lines.append(mono_run(right_x, y, segments, theme["value"]))
    y += LINE_H * 1.8

    swatch_size = 16
    swatch_gap = 4
    sw = []
    for i, color in enumerate(theme["swatches"]):
        sx = right_x + i * (swatch_size + swatch_gap)
        sw.append(f'<rect x="{sx:.2f}" y="{y - swatch_size + 4:.2f}" width="{swatch_size}" height="{swatch_size}" rx="3" fill="{color}" stroke="{theme["border"]}"/>')
    lines.append("".join(sw))
    y += LINE_H * 1.2

    content_bottom = max(y, PAD + art_rows * art_line_h + LINE_H)
    width = right_x + total_chars * CHAR_W + PAD
    height = content_bottom + PAD * 0.6

    art_svg = render_art(art_grid, PAD, PAD, theme, art_line_h, art_char_w)

    svg = f"""<svg width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" xmlns="http://www.w3.org/2000/svg">
<rect x="0.5" y="0.5" width="{width - 1:.0f}" height="{height - 1:.0f}" rx="10" fill="{theme['bg']}" stroke="{theme['border']}"/>
{art_svg}
{''.join(lines)}
</svg>"""
    return svg


def art_rows_to_fill_card() -> int:
    text_height = measure_text_height()
    return max(1, round((text_height - PAD - LINE_H) / ART_LINE_H))


def main():
    # Re-pulled from the live GitHub avatar every run, so the art always
    # tracks whatever profile picture is currently set. Rows are chosen so
    # the art column's height exactly matches the text column's -- no gap.
    art_grid = ascii_art.build_grid(
        ascii_art.fetch_avatar(), rows=art_rows_to_fill_card()
    )

    data = {
        "art_grid": art_grid,
        "stats": stats.get_stats(),
        "loc": loc.get_loc() if os.environ.get("RUN_LOC", "1") != "0" else {"additions": 0, "deletions": 0, "net": 0},
    }

    os.makedirs(ASSETS_DIR, exist_ok=True)
    svg = build_svg("dark", data)
    out_path = os.path.join(ASSETS_DIR, "fetch_dark.svg")
    with open(out_path, "w") as f:
        f.write(svg)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
