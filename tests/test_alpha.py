from __future__ import annotations

from PIL import Image

from assetcut.alpha import (
    add_transparent_padding,
    alpha_bbox,
    alpha_stats,
    edge_matte_warning,
    hard_alpha,
    looks_like_baked_checkerboard,
    transparent_rgb_is_clean,
    trim_to_alpha,
)


def test_real_alpha_stats_detects_transparency() -> None:
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    image.putpixel((4, 4), (255, 0, 0, 255))

    stats = alpha_stats(image)

    assert stats.has_real_transparency
    assert stats.transparent_pixels == 63
    assert stats.opaque_pixels == 1


def test_opaque_rgba_is_not_real_transparency() -> None:
    image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

    stats = alpha_stats(image)

    assert not stats.has_real_transparency
    assert stats.transparent_pixels == 0


def test_rgb_image_stats_reports_no_alpha() -> None:
    image = Image.new("RGB", (8, 8), (255, 0, 0))

    stats = alpha_stats(image)

    assert not stats.has_alpha
    assert not stats.has_real_transparency


def test_transparent_rgb_clean_detects_hidden_matte() -> None:
    image = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 255, 255, 0))

    assert not transparent_rgb_is_clean(image)


def test_edge_matte_warning_detects_pale_semitransparent_edges() -> None:
    image = Image.new("RGBA", (4, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (245, 245, 245, 128))
    image.putpixel((1, 0), (240, 240, 240, 128))
    image.putpixel((2, 0), (20, 20, 20, 255))

    assert edge_matte_warning(image)


def test_trim_to_alpha_crops_bounds() -> None:
    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    for y in range(3, 7):
        for x in range(2, 6):
            image.putpixel((x, y), (255, 0, 0, 255))

    trimmed = trim_to_alpha(image)

    assert trimmed.size == (4, 4)
    assert alpha_bbox(trimmed) == (0, 0, 4, 4)


def test_padding_adds_transparent_border() -> None:
    image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))

    padded = add_transparent_padding(image, 2)

    assert padded.size == (8, 8)
    assert padded.getpixel((0, 0))[3] == 0
    assert padded.getpixel((3, 3))[3] == 255


def test_hard_alpha_outputs_binary_alpha() -> None:
    image = Image.new("RGBA", (2, 1), (255, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 20))
    image.putpixel((1, 0), (255, 0, 0, 200))

    out = hard_alpha(image, threshold=127)

    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((1, 0))[3] == 255


def test_checkerboard_detection_detects_fake_transparency() -> None:
    image = Image.new("RGB", (64, 64), (255, 255, 255))
    cell = 8
    for y in range(64):
        for x in range(64):
            dark = ((x // cell) + (y // cell)) % 2 == 0
            value = 200 if dark else 240
            image.putpixel((x, y), (value, value, value))

    assert looks_like_baked_checkerboard(image)


def test_checkerboard_detection_ignores_real_alpha_detail() -> None:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for y in range(16):
        for x in range(16):
            value = 200 if ((x // 4) + (y // 4)) % 2 == 0 else 240
            image.putpixel((x + 24, y + 24), (value, value, value, 255))

    assert not looks_like_baked_checkerboard(image)
