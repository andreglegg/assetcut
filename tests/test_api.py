from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from assetcut import api
from assetcut.cli import app


def _checkerboard_asset(path: Path) -> None:
    image = Image.new("RGB", (64, 64), (255, 255, 255))
    for y in range(64):
        for x in range(64):
            value = 210 if ((x // 8) + (y // 8)) % 2 == 0 else 245
            image.putpixel((x, y), (value, value, value))
    for y in range(20, 44):
        for x in range(20, 44):
            image.putpixel((x, y), (180, 20, 20))
    image.save(path)


def test_cut_image_api_integration_checkerboard_with_preview(tmp_path: Path) -> None:
    input_path = tmp_path / "trap.png"
    output_path = tmp_path / "trap-cutout.png"
    report_path = tmp_path / "trap-report.json"
    preview_path = tmp_path / "trap-preview.png"
    _checkerboard_asset(input_path)

    result = api.cut_image(
        input_path,
        output_path=output_path,
        report_path=report_path,
        preview=True,
        preview_path=preview_path,
    )

    assert result["ok"] is True
    assert result["backend"] == "checkerboard"
    assert result["output"] == str(output_path)
    assert result["report"] == str(report_path)
    assert result["preview"] == str(preview_path)
    assert output_path.exists()
    assert report_path.exists()
    assert preview_path.exists()


def test_cut_image_api_dry_run_does_not_write(tmp_path: Path) -> None:
    input_path = tmp_path / "trap.png"
    output_path = tmp_path / "trap-cutout.png"
    _checkerboard_asset(input_path)

    result = api.cut_image(input_path, output_path=output_path, dry_run=True, preview=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["backend"] == "checkerboard"
    assert result["output_exists"] is False
    assert not output_path.exists()
    assert not (tmp_path / "trap-preview.png").exists()


def test_cut_image_api_returns_structured_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.png"

    result = api.cut_image(missing)

    assert result["ok"] is False
    assert result["error"]["code"] == "not_found"
    assert result["error"]["path"] == str(missing)


def test_api_rejects_paths_outside_base_dir(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.png"

    result = api.cut_image(outside, base_dir=tmp_path)

    assert result["ok"] is False
    assert result["error"]["code"] == "path_outside_base"


def test_cut_folder_api_enforces_max_files(tmp_path: Path) -> None:
    folder = tmp_path / "raw"
    folder.mkdir()
    _checkerboard_asset(folder / "a.png")
    _checkerboard_asset(folder / "b.png")

    result = api.cut_folder(folder, max_files=1)

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_argument"
    assert "max_files" in result["error"]["message"]


def test_cut_cli_dry_run_json_does_not_write(tmp_path: Path) -> None:
    input_path = tmp_path / "trap.png"
    _checkerboard_asset(input_path)

    result = CliRunner().invoke(app, ["cut", str(input_path), "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["backend"] == "checkerboard"
    assert not (tmp_path / "trap-cutout.png").exists()
