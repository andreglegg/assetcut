from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from pytest import MonkeyPatch
from typer.testing import CliRunner

import assetcut.cli as cli_module
import assetcut.engine
from assetcut.cli import app
from assetcut.engine import ProcessResult
from assetcut.image_io import save_png_rgba
from assetcut.validate import validate_image


class FakeBackend:
    name = "fake"

    def remove(self, image: Image.Image, model_name: str | None = None) -> Image.Image:
        out = Image.new("RGBA", image.size, (0, 0, 0, 0))
        out.putpixel((1, 1), (255, 0, 0, 255))
        return out


def test_remove_cli_writes_rgba_png_and_report(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    input_path = tmp_path / "source.jpg"
    output_path = tmp_path / "nested" / "out.png"
    report_path = tmp_path / "report.json"
    Image.new("RGB", (8, 8), (255, 255, 255)).save(input_path)

    monkeypatch.setattr(assetcut.engine, "get_backend", lambda _name: FakeBackend())

    result = CliRunner().invoke(
        app,
        [
            "remove",
            str(input_path),
            "--out",
            str(output_path),
            "--backend",
            "fake",
            "--mode",
            "ui",
            "--edge-clean",
            "none",
            "--no-trim",
            "--pad",
            "0",
            "--validate",
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    assert Image.open(output_path).mode == "RGBA"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["path"] == str(output_path)


def test_remove_auto_selects_alpha_backend_and_default_output(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    input_path = tmp_path / "sprite.png"
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    image.putpixel((4, 4), (255, 0, 0, 255))
    image.save(input_path)
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
        saved_path = save_png_rgba(image, output_path)
        return ProcessResult(
            input_path=input_path,
            output_path=saved_path,
            validation=validate_image(saved_path) if should_validate else None,
        )

    monkeypatch.setattr(cli_module, "process_image", fake_process_image)

    result = CliRunner().invoke(app, ["remove", str(input_path), "--validate"])

    assert result.exit_code == 0, result.output
    assert backends == ["alpha"]
    assert (tmp_path / "sprite-cutout.png").exists()
    assert "Backend: alpha" in result.output


def test_remove_cli_reports_clear_errors(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    input_path = tmp_path / "source.png"
    output_path = tmp_path / "out.jpg"
    Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(input_path)
    monkeypatch.setattr(assetcut.engine, "get_backend", lambda _name: FakeBackend())

    result = CliRunner().invoke(
        app,
        [
            "remove",
            str(input_path),
            "--out",
            str(output_path),
            "--backend",
            "fake",
        ],
    )

    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Output path must end in .png" in result.output
