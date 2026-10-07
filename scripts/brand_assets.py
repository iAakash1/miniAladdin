"""Generate OmniSignal's favicon, app icon and social-card images.

The mark is the one `dashboard/src/components/ui/Logo.tsx` draws: three
ascending signal bars inside a rounded frame, on a 20-unit grid. This script
reproduces that geometry so the browser tab, the home-screen icon and the
link-preview card show the same mark as the product, and can be regenerated
instead of hand-edited.

    python scripts/brand_assets.py

Writes into dashboard/src/app/ (Next.js file-based metadata):
    icon.svg, favicon.ico, apple-icon.png, opengraph-image.png, twitter-image.png

Needs Pillow. The social card uses the system sans-serif at generation time
only; the output is a committed PNG, so nothing here runs in the build.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

APP = Path(__file__).resolve().parent.parent / "dashboard" / "src" / "app"

BG = (10, 11, 13)          # --p-base, dark theme
ACCENT = (91, 154, 224)    # --accent
INK = (230, 232, 235)      # --ink
INK_MUTED = (163, 171, 182)
RULE = (30, 34, 40)

SS = 8  # supersampling factor for anti-aliasing

# Geometry of LogoMark, in its 20-unit grid: (x, y, w, h, rx, opacity)
FRAME = (0.75, 0.75, 18.5, 18.5, 4.25)
FRAME_STROKE = 1.5
BARS = ((4.75, 10.5, 2.5, 5.0, 0.75, 1.0), (8.75, 7.5, 2.5, 8.0, 0.75, 1.0), (12.75, 4.5, 2.5, 11.0, 0.75, 0.55))


def draw_mark(canvas: Image.Image, left: float, top: float, size: float, color=ACCENT) -> None:
    """Draw the mark with its 20-unit grid scaled to `size` pixels."""
    k = size / 20.0
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y, w, h, rx = FRAME
    d.rounded_rectangle(
        [left + x * k, top + y * k, left + (x + w) * k, top + (y + h) * k],
        radius=rx * k, outline=color + (255,), width=max(1, round(FRAME_STROKE * k)),
    )
    for bx, by, bw, bh, brx, opacity in BARS:
        d.rounded_rectangle(
            [left + bx * k, top + by * k, left + (bx + bw) * k, top + (by + bh) * k],
            radius=brx * k, fill=color + (round(255 * opacity),),
        )
    canvas.alpha_composite(layer)


def tile(px: int, radius_ratio: float = 0.22, pad_ratio: float = 0.14) -> Image.Image:
    """A square icon: dark rounded tile, mark centred inside."""
    big = px * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=big * radius_ratio, fill=BG + (255,))
    pad = big * pad_ratio
    draw_mark(img, pad, pad, big - 2 * pad)
    return img.resize((px, px), Image.LANCZOS)


def write_icons() -> None:
    sizes = (16, 32, 48)
    base = tile(256)
    base.save(APP / "favicon.ico", format="ICO", sizes=[(s, s) for s in sizes])
    tile(180, radius_ratio=0.0, pad_ratio=0.2).convert("RGB").save(APP / "apple-icon.png", optimize=True)

    k = 32 / 20.0
    pad = 32 * 0.14
    inner = 32 - 2 * pad
    k = inner / 20.0
    x, y, w, h, rx = FRAME
    bars = "".join(
        f'<rect x="{pad + bx * k:.3f}" y="{pad + by * k:.3f}" width="{bw * k:.3f}" height="{bh * k:.3f}" '
        f'rx="{brx * k:.3f}" fill="#5b9ae0"' + (f' opacity="{op}"' if op != 1.0 else "") + "/>"
        for bx, by, bw, bh, brx, op in BARS
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">'
        '<title>OmniSignal</title>'
        '<rect width="32" height="32" rx="7" fill="#0a0b0d"/>'
        f'<rect x="{pad + x * k:.3f}" y="{pad + y * k:.3f}" width="{w * k:.3f}" height="{h * k:.3f}" rx="{rx * k:.3f}" '
        f'fill="none" stroke="#5b9ae0" stroke-width="{FRAME_STROKE * k:.3f}"/>'
        f"{bars}</svg>\n"
    )
    (APP / "icon.svg").write_text(svg)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for path in candidates:
        if Path(path).exists():
            f = ImageFont.truetype(path, size)
            if bold:
                try:
                    f.set_variation_by_name("Bold")
                except Exception:  # noqa: BLE001 — static font: regular weight is fine
                    pass
            return f
    return ImageFont.load_default()


def write_social_card() -> None:
    w, h = 1200, 630
    img = Image.new("RGBA", (w * 1, h * 1), BG + (255,))
    d = ImageDraw.Draw(img)

    # quiet baseline grid, like the terminal's own rules
    for gx in range(0, w, 60):
        d.line([(gx, 0), (gx, h)], fill=RULE + (90,), width=1)
    for gy in range(0, h, 60):
        d.line([(0, gy), (w, gy)], fill=RULE + (90,), width=1)

    mark = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
    draw_mark(mark, 120 * 2, 150 * 2, 150 * 2)
    mark = mark.resize((w, h), Image.LANCZOS)
    img.alpha_composite(mark)

    d.text((320, 150), "OmniSignal", font=font(112, bold=True), fill=INK)
    d.text((324, 292), "Evidence-grounded equity research", font=font(44), fill=INK_MUTED)

    y = 410
    for line in (
        "Deterministic signals. Reconciled multi-provider evidence.",
        "SEC primary sources. Grounded explanation that never decides.",
    ):
        d.text((124, y), line, font=font(32), fill=INK_MUTED)
        y += 52
    d.line([(124, 540), (1076, 540)], fill=RULE + (255,), width=2)
    d.text((124, 560), "omnisignalterminal.vercel.app", font=font(28), fill=ACCENT)

    out = img.convert("RGB")
    out.save(APP / "opengraph-image.png", optimize=True)
    out.save(APP / "twitter-image.png", optimize=True)


def main() -> int:
    if not APP.is_dir():
        print(f"missing {APP}", file=sys.stderr)
        return 1
    write_icons()
    write_social_card()
    for name in ("icon.svg", "favicon.ico", "apple-icon.png", "opengraph-image.png", "twitter-image.png"):
        print(f"{name:22} {(APP / name).stat().st_size:>8} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
