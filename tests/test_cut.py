from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from pytest import MonkeyPatch
from typer.testing import CliRunner

import assetcut.cut as cut_module
from assetcut.cli import app
from assetcut.config import QualityPreset
from assetcut.cut import default_output_path, run_cut_file, select_backend_for_path
from assetcut.engine import ProcessResult
from assetcut.image_io import save_png_rgba
from assetcut.validate import validate_image


def _checkerboard_image(path: Path) -> None:
    image = Image.new("RGB", (64, 64), (255, 255, 255))
    for y in range(64):
        for x in range(64):
            value = 210 if ((x // 8) + (y // 8)) % 2 == 0 else 245
            image.putpixel((x, y), (value, value, value))
    for y in range(20, 44):
        for x in range(20, 44):
            image.putpixel((x, y), (180, 20, 20))
    image.save(path)


def _alpha_image(path: Path) -> None:
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    image.putpixel((4, 4), (255, 0, 0, 255))
    image.save(path)


def _install_fake_processor(monkeypatch: MonkeyPatch) -> list[str]:
    backends: list[str] = []

    def fake_process_image(
        input_path: Path,
        output_path: Path,
        backend_name: str,
        model_name: str | None,
        options: object,
        should_validate: bool,
    ) -> ProcessResult:
        backends.append(backend_name)
        image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        image.putpixel((4, 4), (255, 0, 0, 255))
        saved_path = save_png_rgba(image, output_path)
        return ProcessResult(
            input_path=input_path,
            output_path=saved_path,
            validation=validate_image(saved_path),
        )

    monkeypatch.setattr(cut_module, "process_image", fake_process_image)
    return backends


def test_auto_backend_selection_detects_checkerboard_and_alpha(tmp_path: Path) -> None:
    checker = tmp_path / "checker.png"
    alpha = tmp_path / "alpha.png"
    _checkerboard_image(checker)
    _alpha_image(alpha)

    assert select_backend_for_path(checker).name == "checkerboard"
    assert select_backend_for_path(alpha).name == "alpha"


def test_default_output_path_accepts_file_or_folder(tmp_path: Path) -> None:
    input_path = tmp_path / "sprite.png"

    assert default_output_path(input_path) == tmp_path / "sprite-cutout.png"
    assert default_output_path(input_path, tmp_path / "out.png") == tmp_path / "out.png"
    assert default_output_path(input_path, tmp_path / "cutouts") == (
        tmp_path / "cutouts" / "sprite-cutout.png"
    )


def test_cut_cli_writes_default_output_and_report(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    input_path = tmp_path / "sprite.png"
    _alpha_image(input_path)
    backends = _install_fake_processor(monkeypatch)

    result = CliRunner().invoke(app, ["cut", str(input_path)])

    assert result.exit_code == 0, result.output
    assert backends == ["alpha"]
    assert (tmp_path / "sprite-cutout.png").exists()
    report_path = tmp_path / "sprite-cutout-report.json"
    assert json.loads(report_path.read_text(encoding="utf-8"))["ok"] is True
    assert "Input already has real alpha" in result.output


def test_cut_cli_json_output_and_preview(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    input_path = tmp_path / "sprite.png"
    preview_path = tmp_path / "qa.png"
    _alpha_image(input_path)
    _install_fake_processor(monkeypatch)

    result = CliRunner().invoke(
        app,
        [
            "cut",
            str(input_path),
            "--json",
            "--preview",
            "--preview-out",
            str(preview_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["backend"] == "alpha"
    assert payload["preview"] == str(preview_path)
    assert preview_path.exists()


def test_cut_file_refuses_existing_report_without_overwrite(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    input_path = tmp_path / "sprite.png"
    out = tmp_path / "sprite-cutout.png"
    report = tmp_path / "sprite-cutout-report.json"
    _alpha_image(input_path)
    report.write_text("{}", encoding="utf-8")
    _install_fake_processor(monkeypatch)

    try:
        run_cut_file(
            input_path=input_path,
            out=out,
            report=report,
            quality=QualityPreset.crisp,
            backend="auto",
            overwrite=False,
        )
    except FileExistsError as exc:
        assert "Report already exists" in str(exc)
    else:
        raise AssertionError("Expected FileExistsError")


def test_cut_cli_open_alias_reveals_output(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    input_path = tmp_path / "sprite.png"
    _alpha_image(input_path)
    _install_fake_processor(monkeypatch)
    revealed: list[Path] = []
    monkeypatch.setattr("assetcut.cli._reveal_path", revealed.append)

    result = CliRunner().invoke(app, ["cut", str(input_path), "--open"])

    assert result.exit_code == 0, result.output
    assert revealed == [tmp_path / "sprite-cutout.png"]


def test_cut_cli_processes_folder_with_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _alpha_image(raw / "a.png")
    _alpha_image(raw / "b.png")
    out = tmp_path / "cutouts"
    _install_fake_processor(monkeypatch)

    result = CliRunner().invoke(app, ["cut", str(raw), "--out", str(out), "--flat"])

    assert result.exit_code == 0, result.output
    assert (out / "a-cutout.png").exists()
    assert (out / "b-cutout.png").exists()
    payload = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"] == {"found": 2, "processed": 2, "skipped": 0, "failed": 0}
    assert payload["files"][0]["validation"]["backend"] == "alpha"


def test_cut_cli_folder_json_and_preview(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _alpha_image(raw / "a.png")
    out = tmp_path / "cutouts"
    preview_path = tmp_path / "batch-preview.png"
    _install_fake_processor(monkeypatch)

    result = CliRunner().invoke(
        app,
        [
            "cut",
            str(raw),
            "--out",
            str(out),
            "--flat",
            "--json",
            "--preview",
            "--preview-out",
            str(preview_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["preview"] == str(preview_path)
    assert preview_path.exists()
