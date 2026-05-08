from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    root = Path("samples/raw")
    root.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGBA", (256, 256), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((64, 64, 192, 192), fill=(40, 120, 255, 255))
    img.save(root / "blue_orb_on_white.png")

    checker = Image.new("RGB", (256, 256), (255, 255, 255))
    draw = ImageDraw.Draw(checker)
    cell = 16
    for y in range(0, 256, cell):
        for x in range(0, 256, cell):
            v = 200 if ((x // cell) + (y // cell)) % 2 == 0 else 240
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(v, v, v))
    draw.rectangle((84, 84, 172, 172), fill=(40, 120, 255))
    checker.save(root / "fake_checkerboard.png")

    real = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(real)
    draw.rounded_rectangle((64, 80, 192, 176), radius=24, fill=(255, 180, 40, 255))
    real.save(root / "real_alpha.png")


if __name__ == "__main__":
    main()
