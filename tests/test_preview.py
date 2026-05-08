from __future__ import annotations

from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from assetcut.cli import app
from assetcut.preview import create_file_preview, create_folder_preview


def _cutout(path: Path, color: tuple[int, int, int, int] = (255, 0, 0, 255)) -> None:
    image = Image.new("RGBA", (16, 12), (0, 0, 0, 0))
    for y in range(3, 9):
        for x in range(4, 12):
            image.putpixel((x, y), color)
    image.save(path)


def test_create_file_preview_writes_png(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    cutout = tmp_path / "source-cutout.png"
    out = tmp_path / "preview.png"
    Image.new("RGB", (16, 12), (245, 245, 245)).save(source)
    _cutout(cutout)

    result = create_file_preview(source, out, cutout_path=cutout, tile_size=64)

    image = Image.open(result)
    assert image.mode == "RGBA"
    assert image.size == (336, 96)


def test_create_folder_preview_writes_contact_sheet(tmp_path: Path) -> None:
    folder = tmp_path / "cutouts"
    folder.mkdir()
    _cutout(folder / "a.png")
    _cutout(folder / "b.png", color=(0, 255, 0, 255))
    out = tmp_path / "folder-preview.png"

    result = create_folder_preview(folder, out, recursive=False, tile_size=64)

    assert Image.open(result).size == (336, 96)


def test_preview_cli_writes_default_file_preview(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _cutout(source)

    result = CliRunner().invoke(app, ["preview", str(source)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "source-preview.png").exists()
