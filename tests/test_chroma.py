from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from assetcut.chroma import (
    detect_chroma_key,
    detect_key_color,
    parse_hex_color,
    remove_chroma_key,
)
from assetcut.cut import select_backend
from assetcut.validate import validate_image


def magenta_sheet(size: int = 64) -> Image.Image:
    """Magenta background with two solid tiles, one of them hollow."""
    image = Image.new("RGB", (size, size), (248, 34, 248))
    for y in range(8, 28):
        for x in range(8, 28):
            image.putpixel((x, y), (200, 170, 120))
    # Hollow ring tile: the enclosed center is background that must be cut too.
    for y in range(36, 56):
        for x in range(36, 56):
            edge = x in (36, 55) or y in (36, 55)
            image.putpixel((x, y), (60, 70, 90) if edge else (248, 34, 248))
    return image


def test_parse_hex_color() -> None:
    assert parse_hex_color("ff00ff") == (255, 0, 255)
    assert parse_hex_color("#00FF00") == (0, 255, 0)
    with pytest.raises(ValueError):
        parse_hex_color("xyz")


def test_detect_key_color_finds_dominant_border() -> None:
    color, fraction = detect_key_color(np.array(magenta_sheet()))
    assert abs(color[0] - 248) <= 4
    assert abs(color[1] - 34) <= 6
    assert abs(color[2] - 248) <= 4
    assert fraction > 0.95


def test_detect_chroma_key_accepts_saturated_background() -> None:
    detected = detect_chroma_key(magenta_sheet())
    assert detected is not None
    assert max(detected.color) - min(detected.color) >= 60


def test_detect_chroma_key_skips_neutral_background_when_saturation_required() -> None:
    gray = Image.new("RGB", (64, 64), (240, 240, 240))
    gray.paste((20, 20, 20), (16, 16, 48, 48))
    assert detect_chroma_key(gray) is None


def test_remove_chroma_key_cuts_background_including_hollow_center() -> None:
    cutout = remove_chroma_key(magenta_sheet())
    arr = np.array(cutout)
    assert arr[0, 0, 3] == 0  # corner background
    assert arr[18, 18, 3] == 255  # solid tile
    assert arr[45, 45, 3] == 0  # enclosed hollow center is background


def test_remove_chroma_key_is_real_transparent_png(tmp_path) -> None:
    out = tmp_path / "cut.png"
    remove_chroma_key(magenta_sheet()).save(out)
    assert validate_image(out).ok


def test_remove_chroma_key_raises_when_no_match() -> None:
    plain = Image.new("RGB", (32, 32), (10, 20, 30))
    with pytest.raises(RuntimeError, match="No background matching"):
        remove_chroma_key(plain, key_color=(255, 0, 255), tolerance=10)


def test_select_backend_auto_picks_chroma() -> None:
    selection = select_backend(magenta_sheet())
    assert selection.name == "chroma"
