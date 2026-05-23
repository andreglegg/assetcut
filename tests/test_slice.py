from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from assetcut import api
from assetcut.slice import run_slice, slice_auto, slice_grid


def two_tile_sheet() -> Image.Image:
    """Magenta sheet with two separated opaque tiles."""
    image = Image.new("RGB", (64, 32), (248, 34, 248))
    for y in range(6, 26):
        for x in range(6, 26):
            image.putpixel((x, y), (200, 170, 120))
        for x in range(38, 58):
            image.putpixel((x, y), (60, 70, 90))
    return image


def transparent_two_tile_sheet() -> Image.Image:
    rgba = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    for y in range(6, 26):
        for x in range(6, 26):
            rgba.putpixel((x, y), (200, 170, 120, 255))
        for x in range(38, 58):
            rgba.putpixel((x, y), (60, 70, 90, 255))
    return rgba


def test_slice_auto_finds_each_connected_tile() -> None:
    result = slice_auto(transparent_two_tile_sheet(), min_area=16)
    assert result.mode == "auto"
    assert len(result.tiles) == 2
    # Trimmed tight to 20x20 content.
    assert all(tile.image.size == (20, 20) for tile in result.tiles)


def test_slice_auto_reading_order_left_to_right() -> None:
    result = slice_auto(transparent_two_tile_sheet(), min_area=16)
    assert result.tiles[0].x < result.tiles[1].x


def test_slice_auto_min_area_drops_specks() -> None:
    rgba = transparent_two_tile_sheet()
    rgba.putpixel((1, 1), (255, 255, 255, 255))
    result = slice_auto(rgba, min_area=16)
    assert len(result.tiles) == 2


def test_slice_grid_drops_empty_cells() -> None:
    result = slice_grid(
        transparent_two_tile_sheet(),
        tile_width=32,
        tile_height=32,
        drop_empty=True,
    )
    assert result.columns == 2
    assert result.rows == 1
    assert len(result.tiles) == 2


def test_slice_grid_keeps_empty_when_requested() -> None:
    empty = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    result = slice_grid(empty, tile_width=32, tile_height=32, drop_empty=False)
    assert len(result.tiles) == 2


def test_slice_grid_rejects_oversized_tiles() -> None:
    with pytest.raises(ValueError, match="does not fit"):
        slice_grid(transparent_two_tile_sheet(), tile_width=128, tile_height=128)


def test_run_slice_auto_dekeys_and_writes_files(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    two_tile_sheet().save(sheet)
    result = run_slice(sheet, mode="auto", backend="auto", min_area=16, overwrite=True)

    assert result.backend == "chroma"
    assert result.tile_count == 2
    assert (result.output_folder / "sheet_000.png").exists()
    assert (result.output_folder / "sheet_001.png").exists()

    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["count"] == 2
    assert manifest["frames"][0]["file"] == "sheet_000.png"


def test_run_slice_grid_requires_tile_size(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    two_tile_sheet().save(sheet)
    with pytest.raises(ValueError, match="tile size"):
        run_slice(sheet, mode="grid", overwrite=True)


def test_run_slice_refuses_to_overwrite_without_flag(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    two_tile_sheet().save(sheet)
    run_slice(sheet, mode="auto", min_area=16, overwrite=True)
    with pytest.raises(FileExistsError):
        run_slice(sheet, mode="auto", min_area=16, overwrite=False)


def test_run_slice_grid_keeps_uniform_cells_by_default(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    two_tile_sheet().save(sheet)
    run_slice(sheet, mode="grid", tile_width=32, tile_height=32, overwrite=True)
    for index in (0, 1):
        tile = Image.open(tmp_path / "sheet-tiles" / f"sheet_{index:03d}.png")
        assert tile.size == (32, 32)


def test_run_slice_grid_trims_when_requested(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    two_tile_sheet().save(sheet)
    run_slice(
        sheet, mode="grid", tile_width=32, tile_height=32, trim_tiles=True, overwrite=True
    )
    tile = Image.open(tmp_path / "sheet-tiles" / "sheet_000.png")
    assert tile.size == (20, 20)


def test_slice_grid_manifest_records_source_cell_geometry(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    two_tile_sheet().save(sheet)
    result = run_slice(
        sheet, mode="grid", tile_width=32, tile_height=32, trim_tiles=True, overwrite=True
    )
    manifest = json.loads(result.manifest_path.read_text())
    frame = manifest["frames"][0]
    # Frame rect describes the 32x32 source cell even though the saved tile is trimmed.
    assert frame["width"] == 32
    assert frame["height"] == 32
    assert Image.open(tmp_path / "sheet-tiles" / frame["file"]).size == (20, 20)


def test_run_slice_overwrite_removes_stale_tiles(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    two_tile_sheet().save(sheet)
    run_slice(sheet, mode="auto", min_area=16, overwrite=True)
    assert (tmp_path / "sheet-tiles" / "sheet_001.png").exists()

    one_tile = Image.new("RGB", (64, 32), (248, 34, 248))
    for y in range(6, 26):
        for x in range(6, 26):
            one_tile.putpixel((x, y), (200, 170, 120))
    one_tile.save(sheet)
    result = run_slice(sheet, mode="auto", min_area=16, overwrite=True)

    assert result.tile_count == 1
    assert not (tmp_path / "sheet-tiles" / "sheet_001.png").exists()


def test_api_slice_sheet_parses_tile_and_key_color(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    two_tile_sheet().save(sheet)
    response = api.slice_sheet(
        input_path=str(sheet),
        mode="grid",
        tile="32x32",
        key_color="f822f8",
        overwrite=True,
    )
    assert response["ok"] is True
    assert response["tiles"] == 2
    assert response["backend"] == "chroma"


def test_api_slice_sheet_reports_error_for_bad_tile(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    two_tile_sheet().save(sheet)
    response = api.slice_sheet(input_path=str(sheet), mode="grid", tile="abc", overwrite=True)
    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_argument"
