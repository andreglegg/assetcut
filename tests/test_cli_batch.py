from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from pytest import MonkeyPatch
from typer.testing import CliRunner

import assetcut.cli as cli_module
from assetcut.cli import app
from assetcut.engine import ProcessResult
from assetcut.image_io import save_png_rgba


def _write_input(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), (255, 255, 255)).save(path)


def _install_fake_processor(monkeypatch: MonkeyPatch, failures: set[str] | None = None) -> None:
    failures = failures or set()

    def fake_process_image(
        input_path: Path,
        output_path: Path,
        backend_name: str,
        model_name: str | None,
        options: object,
        should_validate: bool,
    ) -> ProcessResult:
        if input_path.name in failures:
            raise RuntimeError("planned failure")
        image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        image.putpixel((1, 1), (255, 0, 0, 255))
        saved_path = save_png_rgba(image, output_path)
        return ProcessResult(input_path=input_path, output_path=saved_path, validation=None)

    monkeypatch.setattr(cli_module, "process_image", fake_process_image)


def test_batch_processes_recursive_inputs_and_writes_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    manifest = tmp_path / "manifest.json"
    _write_input(raw / "a.png")
    _write_input(raw / "b.jpg")
    _write_input(raw / "nested" / "c.webp")
    _install_fake_processor(monkeypatch)

    result = CliRunner().invoke(
        app,
        [
            "batch",
            str(raw),
            "--out",
            str(out),
            "--recursive",
            "--backend",
            "fake",
            "--manifest",
            str(manifest),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out / "a.png").exists()
    assert (out / "b.png").exists()
    assert (out / "nested" / "c.png").exists()

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["summary"] == {"found": 3, "processed": 3, "skipped": 0, "failed": 0}
    assert [record["status"] for record in payload["files"]] == [
        "processed",
        "processed",
        "processed",
    ]


def test_batch_skips_existing_outputs_without_overwrite(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    manifest = tmp_path / "manifest.json"
    _write_input(raw / "asset.png")
    out.mkdir()
    Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(out / "asset.png")

    calls: list[Path] = []

    def fake_process_image(
        input_path: Path,
        output_path: Path,
        backend_name: str,
        model_name: str | None,
        options: object,
        should_validate: bool,
    ) -> ProcessResult:
        calls.append(input_path)
        saved_path = save_png_rgba(Image.new("RGBA", (2, 2), (0, 0, 0, 0)), output_path)
        return ProcessResult(input_path=input_path, output_path=saved_path, validation=None)

    monkeypatch.setattr(cli_module, "process_image", fake_process_image)

    result = CliRunner().invoke(
        app,
        ["batch", str(raw), "--out", str(out), "--backend", "fake", "--manifest", str(manifest)],
    )

    assert result.exit_code == 0, result.output
    assert calls == []
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["summary"] == {"found": 1, "processed": 0, "skipped": 1, "failed": 0}
    assert payload["files"][0]["status"] == "skipped"


def test_batch_continues_after_failures_by_default(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    manifest = tmp_path / "manifest.json"
    _write_input(raw / "bad.png")
    _write_input(raw / "good.png")
    _install_fake_processor(monkeypatch, failures={"bad.png"})

    result = CliRunner().invoke(
        app,
        ["batch", str(raw), "--out", str(out), "--backend", "fake", "--manifest", str(manifest)],
    )

    assert result.exit_code == 0, result.output
    assert not (out / "bad.png").exists()
    assert (out / "good.png").exists()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["summary"] == {"found": 2, "processed": 1, "skipped": 0, "failed": 1}
    assert [record["status"] for record in payload["files"]] == ["failed", "processed"]
