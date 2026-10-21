import math
import pathlib

from PIL import Image, ImageDraw, ImageFilter

HERE = pathlib.Path(__file__).resolve().parent
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
SUPER = 8

TILE = (11, 16, 32, 255)
TILE_EDGE = (40, 58, 96, 255)
DISC_HOT = (255, 214, 140, 255)
DISC = (255, 164, 36, 255)
DISC_COOL = (200, 80, 20, 255)
RING = (143, 208, 255, 255)
STAR = (230, 240, 255, 255)


def disc_mask(n, tilt, inner, outer, front):
    mask = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(mask)
    c = n / 2
    box = lambda r: (c - r, c - r * tilt, c + r, c + r * tilt)
    d.ellipse(box(outer), fill=255)
    d.ellipse(box(inner), fill=0)
    if front is not None:
        half = Image.new("L", (n, n), 0)
        ImageDraw.Draw(half).rectangle((0, c if front else 0, n, n if front else c), fill=255)
        mask = Image.composite(mask, Image.new("L", (n, n), 0), half)
    return mask


def gradient_disc(n):
    img = Image.new("RGBA", (n, n))
    px = img.load()
    c = n / 2
    for y in range(n):
        for x in range(n):
            t = min(1.0, math.hypot(x - c, (y - c) * 2.6) / (n * 0.46))
            a, b, s = (DISC_HOT, DISC, t / 0.5) if t < 0.5 else (DISC, DISC_COOL, (t - 0.5) / 0.5)
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * s) for i in range(4))
    return img


def draw(size):
    n = size * SUPER
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = n * 0.04
    radius = n * 0.2
    d.rounded_rectangle((pad, pad, n - pad, n - pad), radius=radius, fill=TILE, outline=TILE_EDGE,
                        width=max(SUPER, round(n * 0.02)))
    c = n / 2
    small = size < 32

    if not small:
        for fx, fy, r in ((0.22, 0.24, 0.012), (0.78, 0.2, 0.009), (0.8, 0.78, 0.011), (0.2, 0.8, 0.008)):
            d.ellipse((n * fx - n * r, n * fy - n * r, n * fx + n * r, n * fy + n * r), fill=STAR)

    tilt = 0.38
    outer = n * (0.44 if small else 0.42)
    inner = n * (0.2 if small else 0.19)
    disc = gradient_disc(n)
    back = disc_mask(n, tilt, inner, outer, front=False)
    img.paste(disc, (0, 0), back)

    hole = n * (0.16 if small else 0.15)
    glow = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ring_w = n * (0.035 if small else 0.022)
    ImageDraw.Draw(glow).ellipse((c - hole - ring_w, c - hole - ring_w, c + hole + ring_w, c + hole + ring_w),
                                 fill=RING)
    if not small:
        glow = glow.filter(ImageFilter.GaussianBlur(n * 0.012))
    img.alpha_composite(glow)
    d.ellipse((c - hole, c - hole, c + hole, c + hole), fill=(0, 0, 0, 255))

    front = disc_mask(n, tilt, inner, outer, front=True)
    img.paste(disc, (0, 0), front)
    return img.resize((size, size), Image.LANCZOS)


def main():
    images = [draw(s) for s in SIZES]
    out = HERE / "ed-overlay.ico"
    images[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print(f"wrote {out} ({', '.join(str(s) for s in SIZES)})")


if __name__ == "__main__":
    main()
