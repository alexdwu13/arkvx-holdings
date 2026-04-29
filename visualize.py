#!/usr/bin/env python3
"""Render a stacked-percent terminal chart of ARKVX holdings over time."""

import argparse
import colorsys
import csv
import glob
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
FILE_RE = re.compile(r"ARKVX_HOLDINGS_(\d{4}-\d{2}-\d{2})\.csv$")


def parse_csv(path: Path):
    holdings = {}
    asof = None
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return holdings, asof
        try:
            date_idx = header.index("date")
            company_idx = header.index("company")
            weight_idx = next(i for i, h in enumerate(header) if "weight" in h.lower())
        except (ValueError, StopIteration):
            return holdings, asof
        for row in reader:
            if len(row) <= max(company_idx, weight_idx, date_idx):
                continue
            company = row[company_idx].strip()
            wstr = row[weight_idx].strip().rstrip("%")
            if not company or not wstr:
                continue
            try:
                w = float(wstr)
            except ValueError:
                continue
            holdings[company] = holdings.get(company, 0.0) + w
            if asof is None and row[date_idx].strip():
                asof = row[date_idx].strip()
    return holdings, asof


def load_all(data_dir: Path):
    """Return list of (download_date, asof_date, {company: weight_pct}) sorted by date."""
    rows = []
    for p in sorted(data_dir.glob("ARKVX_HOLDINGS_*.csv")):
        m = FILE_RE.search(p.name)
        if not m:
            continue
        h, asof = parse_csv(p)
        if not h:
            continue
        rows.append((m.group(1), asof, h))
    return rows


def normalize_to_100(weights: dict):
    total = sum(weights.values())
    if total <= 0:
        return weights
    return {k: v * 100.0 / total for k, v in weights.items()}


def bucket_other(rows, other_pct: float):
    """Pick a stable set of 'top' holdings across all dates.

    A company is kept individually if in any date its weight pushes it out of
    the bottom 'other_pct' (cumulative from smallest). Everything else folds
    into 'Other'.
    """
    # For each date, mark which companies fall in the bottom other_pct cumulatively.
    keep = set()
    for _, _asof, w in rows:
        items = sorted(w.items(), key=lambda x: x[1])  # ascending
        cum = 0.0
        for name, weight in items:
            cum += weight
            if cum > other_pct:
                # this and remaining go into "kept"
                idx = items.index((name, weight))
                for n2, _ in items[idx:]:
                    keep.add(n2)
                break
    return keep


def reshape(rows, keep):
    """Return (dates, names_in_order, matrix) where matrix[d][n] is pct, summing to 100."""
    dates = [d for d, _, _ in rows]
    asofs = [a for _, a, _ in rows]
    avg = defaultdict(float)
    counts = defaultdict(int)
    for _, _a, w in rows:
        for k, v in w.items():
            name = k if k in keep else "Other"
            avg[name] += v
            counts[name] += 1
    for k in avg:
        avg[k] /= max(counts[k], 1)
    names = sorted(avg.keys(), key=lambda n: (-avg[n], n))
    if "Other" in names:
        names.remove("Other")
        names.append("Other")

    matrix = []
    for _, _a, w in rows:
        col = defaultdict(float)
        for k, v in w.items():
            col[k if k in keep else "Other"] += v
        total = sum(col.values()) or 1.0
        matrix.append([col.get(n, 0.0) * 100.0 / total for n in names])
    return dates, asofs, names, matrix


# ---- color palette ----

def hsl_to_rgb(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


def palette(n: int):
    """Return n visually distinct RGB tuples using golden-ratio hue stepping."""
    GOLDEN = 0.61803398875
    cols = []
    h = 0.13
    for i in range(n):
        # alternate lightness/saturation to separate adjacent bands
        if i % 3 == 0:
            s, l = 0.78, 0.55
        elif i % 3 == 1:
            s, l = 0.62, 0.45
        else:
            s, l = 0.85, 0.65
        cols.append(hsl_to_rgb(h % 1.0, s, l))
        h += GOLDEN
    return cols


OTHER_COLOR = (110, 110, 115)


def fg(rgb):
    r, g, b = rgb
    return f"\x1b[38;2;{r};{g};{b}m"


def bg(rgb):
    r, g, b = rgb
    return f"\x1b[48;2;{r};{g};{b}m"


RESET = "\x1b[0m"


# ---- rendering ----

def render(dates, names, matrix, *, height=30, col_width=3, gap=0):
    """Render a stacked percent chart using half-block characters for 2x vertical resolution."""
    sub_rows = height * 2  # using ▀ for top half and ▄ for bottom half
    # Build per-column band map: for each column, list of (rgb_for_subrow) indexed bottom→top
    n_cols = len(dates)
    cols_pixels = []  # list of length n_cols, each a list of length sub_rows of rgb tuples
    pal = palette(len(names))
    name_color = {}
    for i, name in enumerate(names):
        name_color[name] = OTHER_COLOR if name == "Other" else pal[i]

    for col_idx in range(n_cols):
        weights = matrix[col_idx]  # pct per name, sums to 100
        # convert pct → cumulative subrow boundaries
        pixels = []
        cum = 0.0
        # For each name, paint cum..cum+w (in subrows). Use rounding so total = sub_rows.
        # We do this by computing integer subrow allocations summing to sub_rows.
        raw = [w * sub_rows / 100.0 for w in weights]
        floors = [int(x) for x in raw]
        remainder = sub_rows - sum(floors)
        # distribute leftover subrows to the largest fractional parts
        fracs = sorted(
            range(len(weights)),
            key=lambda i: (raw[i] - floors[i]),
            reverse=True,
        )
        alloc = floors[:]
        for i in fracs[:remainder]:
            alloc[i] += 1
        # build bottom-up pixel list (largest weights are first in `names`, drawn at bottom)
        for name, count in zip(names, alloc):
            pixels.extend([name_color[name]] * count)
        # Safety pad/trim
        if len(pixels) < sub_rows:
            pixels.extend([name_color[names[-1]]] * (sub_rows - len(pixels)))
        pixels = pixels[:sub_rows]
        cols_pixels.append(pixels)

    # Render rows top→bottom. Each printed row covers two subrows.
    lines = []
    for row in range(height):
        # subrow indices: top = sub_rows - 1 - 2*row, bottom = sub_rows - 2 - 2*row
        top_sub = sub_rows - 1 - 2 * row
        bot_sub = sub_rows - 2 - 2 * row
        # y-axis label every 5 rows
        pct_label = 100 - int(row * 100 / max(height - 1, 1))
        if row == 0 or row == height - 1 or row % 5 == 0:
            label = f"{pct_label:>3}%│"
        else:
            label = "    │"
        parts = [label]
        for col_idx in range(n_cols):
            top_rgb = cols_pixels[col_idx][top_sub]
            bot_rgb = cols_pixels[col_idx][bot_sub]
            cell = f"{fg(top_rgb)}{bg(bot_rgb)}{'▀' * col_width}{RESET}"
            parts.append(cell)
            if gap:
                parts.append(" " * gap)
        lines.append("".join(parts))

    # X-axis tick line and date labels
    axis = "    └" + "─" * (n_cols * (col_width + gap))
    lines.append(axis)

    # Date labels: rotate? Just show first, middle, last to keep it tidy.
    # Or show every Nth date based on width.
    label_line_chars = [" "] * (5 + n_cols * (col_width + gap))
    # decide tick stride based on terminal width
    # show as many short MM-DD labels as fit
    short = [d[5:] for d in dates]  # MM-DD
    label_w = 5  # "MM-DD"
    stride = max(1, (label_w + 1) // (col_width + gap) + 1)
    for i in range(0, n_cols, stride):
        center = 5 + i * (col_width + gap) + col_width // 2
        lbl = short[i]
        start = center - len(lbl) // 2
        for j, ch in enumerate(lbl):
            pos = start + j
            if 0 <= pos < len(label_line_chars):
                label_line_chars[pos] = ch
    lines.append("".join(label_line_chars))
    return lines, name_color


def render_legend(names, name_color, weights_latest, *, max_width):
    """Show name + color swatch + latest weight, in two columns if it fits."""
    items = []
    for i, name in enumerate(names):
        sw = f"{bg(name_color[name])}  {RESET}"
        pct = weights_latest[i]
        label = name if len(name) <= 32 else name[:29] + "…"
        items.append(f"{sw} {label}  {pct:5.2f}%")
    # plain-text widths for layout
    plain = [re.sub(r"\x1b\[[0-9;]*m", "", s) for s in items]
    col_w = max(len(p) for p in plain) + 3
    n_cols = max(1, max_width // col_w)
    rows = (len(items) + n_cols - 1) // n_cols
    out = []
    for r in range(rows):
        parts = []
        for c in range(n_cols):
            idx = c * rows + r
            if idx < len(items):
                pad = col_w - len(plain[idx])
                parts.append(items[idx] + " " * pad)
        out.append("".join(parts).rstrip())
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", default=str(DATA_DIR), help="Path to data dir.")
    p.add_argument("--other-pct", type=float, default=10.0,
                   help="Bottom cumulative %% to fold into 'Other' (default 10).")
    p.add_argument("--height", type=int, default=None,
                   help="Chart height in rows (default: terminal-aware).")
    p.add_argument("--width", type=int, default=None,
                   help="Total width in columns (default: terminal-aware).")
    args = p.parse_args(argv)

    data_dir = Path(args.data)
    rows = load_all(data_dir)
    if not rows:
        print(f"No ARKVX_HOLDINGS_*.csv found in {data_dir}", file=sys.stderr)
        return 1

    keep = bucket_other(rows, args.other_pct)
    dates, asofs, names, matrix = reshape(rows, keep)
    unique_asofs = sorted({a for a in asofs if a})

    term = shutil.get_terminal_size((100, 30))
    height = args.height or max(18, min(40, term.lines - 14))
    avail_w = (args.width or term.columns) - 6  # 5 for y-axis, 1 buffer
    n = max(len(dates), 1)
    col_width, gap = 4, 1
    if (col_width + gap) * n > avail_w:
        if avail_w // n >= 3:
            col_width, gap = avail_w // n - 1, 1
        else:
            col_width, gap = max(1, avail_w // n), 0

    lines, name_color = render(dates, names, matrix, height=height,
                               col_width=col_width, gap=gap)

    title = f"ARKVX Holdings — {dates[0]} → {dates[-1]}  ({len(dates)} snapshots)"
    if len(unique_asofs) == 1:
        subtitle = f"holdings as of {unique_asofs[0]} (unchanged across all snapshots)"
    elif unique_asofs:
        subtitle = f"as-of dates: {', '.join(unique_asofs)}"
    else:
        subtitle = ""
    print()
    print(f"  \x1b[1m{title}\x1b[0m")
    if subtitle:
        print(f"  \x1b[2m{subtitle}\x1b[0m")
    print()

    chart_plain_w = 5 + n * (col_width + gap)
    legend_w = max(20, term.columns - chart_plain_w - 3)
    legend = render_legend(names, name_color, matrix[-1], max_width=legend_w)

    pad = " " * chart_plain_w
    total = max(len(lines), len(legend))
    for i in range(total):
        chart_line = lines[i] if i < len(lines) else pad
        legend_line = legend[i] if i < len(legend) else ""
        print(f"{chart_line}   {legend_line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
