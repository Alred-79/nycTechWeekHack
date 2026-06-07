"""Render an .excalidraw element JSON to a clean SVG (for slide/Devpost export)."""
import json
import sys
import html
import math

PAD = 30
FONT = "Helvetica, Arial, sans-serif"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def bounds(elements):
    xs, ys = [], []
    for e in elements:
        x, y = e.get("x", 0), e.get("y", 0)
        w, h = e.get("width", 0), e.get("height", 0)
        xs += [x, x + w]
        ys += [y, y + h]
    return min(xs), min(ys), max(xs), max(ys)


def render_rect(e):
    op = e.get("opacity", 100) / 100.0
    rx = 12 if e.get("roundness") else 0
    return (
        f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["width"]}" height="{e["height"]}" '
        f'rx="{rx}" ry="{rx}" fill="{e.get("backgroundColor", "transparent")}" '
        f'stroke="{e.get("strokeColor", "#1e1e1e")}" stroke-width="{e.get("strokeWidth", 2)}" '
        f'opacity="{op}"/>'
    )


def _wrap(line, max_chars):
    if len(line) <= max_chars:
        return [line]
    words, cur, out = line.split(" "), "", []
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        out.append(cur)
    return out


def render_text(e):
    fs = e.get("fontSize", 16)
    color = e.get("strokeColor", "#1e1e1e")
    lines = e["text"].split("\n")
    if e.get("containerId"):
        max_chars = max(6, int(e.get("width", 200) / (fs * 0.55)))
        wrapped = []
        for ln in lines:
            wrapped += _wrap(ln, max_chars)
        lines = wrapped
    lh = fs * 1.25
    align = e.get("textAlign", "left")
    out = []
    if e.get("containerId") or e.get("verticalAlign") == "middle":
        cx = e["x"] + e["width"] / 2
        cy = e["y"] + e["height"] / 2
        anchor = "middle"
        start_y = cy - (len(lines) - 1) * lh / 2 + fs * 0.35
        tx = cx
    else:
        anchor = "start" if align == "left" else "middle"
        tx = e["x"] if align == "left" else e["x"] + e.get("width", 0) / 2
        start_y = e["y"] + fs
    for i, ln in enumerate(lines):
        y = start_y + i * lh
        out.append(
            f'<text x="{tx}" y="{y:.1f}" font-family="{FONT}" font-size="{fs}" '
            f'fill="{color}" text-anchor="{anchor}">{esc(ln)}</text>'
        )
    return "\n".join(out)


def render_arrow(e):
    ox, oy = e["x"], e["y"]
    pts = [(ox + dx, oy + dy) for dx, dy in e["points"]]
    color = e.get("strokeColor", "#1e1e1e")
    sw = e.get("strokeWidth", 2)
    dash = ' stroke-dasharray="6 5"' if e.get("strokeStyle") == "dashed" else ""
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    out = [f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{sw}"{dash}/>']
    if e.get("endArrowhead", "arrow") == "arrow" and len(pts) >= 2:
        x2, y2 = pts[-1]
        x1, y1 = pts[-2]
        ang = math.atan2(y2 - y1, x2 - x1)
        size = 10
        for a in (ang + math.radians(150), ang - math.radians(150)):
            hx = x2 + size * math.cos(a)
            hy = y2 + size * math.sin(a)
            out.append(f'<line x1="{x2:.1f}" y1="{y2:.1f}" x2="{hx:.1f}" y2="{hy:.1f}" '
                       f'stroke="{color}" stroke-width="{sw}"/>')
    return "\n".join(out)


def render(path_in, path_out):
    data = json.load(open(path_in))
    els = data["elements"]
    minx, miny, maxx, maxy = bounds(els)
    w = maxx - minx + 2 * PAD
    h = maxy - miny + 2 * PAD
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
        f'viewBox="{minx - PAD:.0f} {miny - PAD:.0f} {w:.0f} {h:.0f}">',
        f'<rect x="{minx - PAD:.0f}" y="{miny - PAD:.0f}" width="{w:.0f}" height="{h:.0f}" fill="#ffffff"/>',
    ]
    # draw shapes/arrows first, text last
    for e in els:
        t = e["type"]
        if t == "rectangle":
            parts.append(render_rect(e))
        elif t == "arrow":
            parts.append(render_arrow(e))
    for e in els:
        if e["type"] == "text":
            parts.append(render_text(e))
    parts.append("</svg>")
    open(path_out, "w").write("\n".join(parts))
    print(f"wrote {path_out}  ({w:.0f}x{h:.0f})")


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
