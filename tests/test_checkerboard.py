from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from assetcut.checkerboard import (
    detect_checkerboard_background,
    remove_checkerboard_background,
)
from assetcut.validate import validate_image


def checkerboard_image(size: int = 64, cell: int = 8) -> Image.Image:
    image = Image.new("RGB", (size, size), (255, 255, 255))
    for y in range(size):
        for x in range(size):
            value = 210 if ((x // cell) + (y // cell)) % 2 == 0 else 245
            image.putpixel((x, y), (value, value, value))
    return image


def test_detect_checkerboard_background_uses_border_connected_background() -> None:
    image = checkerboard_image()
    for y in range(20, 44):
        for x in range(20, 44):
            image.putpixel((x, y), (180, 20, 20))
    image.putpixel((32, 32), (245, 245, 245))

    mask = detect_checkerboard_background(image)

    assert mask is not None
    assert mask.background[0, 0]
    assert not mask.background[32, 32]


def test_remove_checkerboard_background_outputs_real_alpha_png(tmp_path: Path) -> None:
    image = checkerboard_image()
    for y in range(20, 44):
        for x in range(20, 44):
            image.putpixel((x, y), (180, 20, 20))

    cutout = remove_checkerboard_background(image)
    out = tmp_path / "cutout.png"
    cutout.save(out)

    assert cutout.getpixel((0, 0))[3] == 0
    assert cutout.getpixel((32, 32))[3] == 255
    assert validate_image(out).ok


def test_remove_checkerboard_background_fails_on_plain_background() -> None:
    image = Image.new("RGB", (64, 64), (245, 245, 245))

    with pytest.raises(RuntimeError, match="No baked checkerboard"):
        remove_checkerboard_background(image)
