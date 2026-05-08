from __future__ import annotations

from pathlib import Path

from PIL import Image

from assetcut.validate import validate_folder, validate_image


def test_validate_real_transparent_png(tmp_path: Path) -> None:
    path = tmp_path / "real.png"
    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    image.putpixel((8, 8), (255, 0, 0, 255))
    image.save(path)

    report = validate_image(path)

    assert report.ok


def test_validate_fails_opaque_png(tmp_path: Path) -> None:
    path = tmp_path / "opaque.png"
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(path)

    report = validate_image(path)

    assert not report.ok
    assert any(check.name == "real_alpha" and check.status == "fail" for check in report.checks)


def test_validate_fails_rgb_png_without_alpha(tmp_path: Path) -> None:
    path = tmp_path / "rgb.png"
    Image.new("RGB", (16, 16), (255, 0, 0)).save(path)

    report = validate_image(path)

    assert not report.ok
    assert report.alpha["has_alpha"] is False
    assert any(check.name == "rgba" and check.status == "fail" for check in report.checks)


def test_validate_fails_hidden_rgb_under_transparency(tmp_path: Path) -> None:
    path = tmp_path / "matte.png"
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 255, 255, 0))
    image.putpixel((4, 4), (255, 0, 0, 255))
    image.save(path)

    report = validate_image(path)

    assert not report.ok
    assert any(
        check.name == "transparent_rgb_clean" and check.status == "fail"
        for check in report.checks
    )


def test_validate_warns_edge_matte(tmp_path: Path) -> None:
    path = tmp_path / "edge.png"
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for x in range(8):
        image.putpixel((x, 3), (245, 245, 245, 128))
        image.putpixel((x, 4), (30, 30, 30, 255))
    image.save(path)

    report = validate_image(path)

    assert report.ok
    assert any(check.name == "edge_matte" and check.status == "warn" for check in report.checks)


def test_validate_warns_checkerboard(tmp_path: Path) -> None:
    path = tmp_path / "checker.png"
    image = Image.new("RGB", (64, 64), (255, 255, 255))
    cell = 8
    for y in range(64):
        for x in range(64):
            value = 200 if ((x // cell) + (y // cell)) % 2 == 0 else 240
            image.putpixel((x, y), (value, value, value))
    image.save(path)

    report = validate_image(path)

    assert not report.ok
    assert report.warnings


def test_validate_folder_respects_recursive(tmp_path: Path) -> None:
    root_image = tmp_path / "root.png"
    nested = tmp_path / "nested"
    nested.mkdir()
    nested_image = nested / "child.png"

    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    image.putpixel((1, 1), (255, 0, 0, 255))
    image.save(root_image)
    image.save(nested_image)

    shallow = validate_folder(tmp_path, recursive=False)
    recursive = validate_folder(tmp_path, recursive=True)

    assert [Path(report.path).name for report in shallow] == ["root.png"]
    assert sorted(Path(report.path).name for report in recursive) == ["child.png", "root.png"]
