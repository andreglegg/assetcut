from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from assetcut.alpha import alpha_stats
from assetcut.batch import BatchRecord, BatchSummary
from assetcut.checkerboard import detect_checkerboard_background
from assetcut.config import ProcessingOptions, QualityPreset, options_for_quality
from assetcut.engine import process_image
from assetcut.image_io import iter_image_files, load_image


@dataclass(frozen=True)
class BackendSelection:
    name: str
    reason: str


@dataclass(frozen=True)
class CutResult:
    input_path: Path
    output_path: Path
    report_path: Path
    preview_path: Path | None
    backend_name: str
    reason: str
    validation_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.validation_ok,
            "input": str(self.input_path),
            "output": str(self.output_path),
            "report": str(self.report_path),
            "preview": str(self.preview_path) if self.preview_path else None,
            "backend": self.backend_name,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CutBatchResult:
    output_folder: Path
    manifest_path: Path
    preview_path: Path | None
    summary: BatchSummary
    records: list[BatchRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.summary.failed == 0,
            "output_folder": str(self.output_folder),
            "manifest": str(self.manifest_path),
            "preview": str(self.preview_path) if self.preview_path else None,
            "summary": self.summary.to_dict(),
            "files": [record.to_dict() for record in self.records],
        }


def with_file_preview(result: CutResult, preview_path: Path) -> CutResult:
    return CutResult(
        input_path=result.input_path,
        output_path=result.output_path,
        report_path=result.report_path,
        preview_path=preview_path,
        backend_name=result.backend_name,
        reason=result.reason,
        validation_ok=result.validation_ok,
    )


def with_batch_preview(result: CutBatchResult, preview_path: Path) -> CutBatchResult:
    return CutBatchResult(
        output_folder=result.output_folder,
        manifest_path=result.manifest_path,
        preview_path=preview_path,
        summary=result.summary,
        records=result.records,
    )


def default_output_path(input_path: Path, out: Path | None = None) -> Path:
    filename = f"{input_path.stem}-cutout.png"
    if out is None:
        return input_path.with_name(filename)
    if out.suffix and out.suffix.lower() != ".png":
        raise ValueError(f"Output path must end in .png or be a folder: {out}")
    if out.suffix.lower() == ".png":
        return out
    return out / filename


def default_report_path(output_path: Path, report: Path | None = None) -> Path:
    if report is not None:
        return report
    return output_path.with_name(f"{output_path.stem}-report.json")


def default_batch_output_folder(input_folder: Path, out: Path | None = None) -> Path:
    if out is not None:
        return out
    return input_folder.with_name(f"{input_folder.name}-cutouts")


def default_manifest_path(output_folder: Path, manifest: Path | None = None) -> Path:
    if manifest is not None:
        return manifest
    return output_folder / "manifest.json"


def select_backend(image: Image.Image, requested_backend: str = "auto") -> BackendSelection:
    normalized = requested_backend.strip().lower()
    if normalized != "auto":
        return BackendSelection(name=normalized, reason=f"Using requested backend: {normalized}")

    if detect_checkerboard_background(image) is not None:
        return BackendSelection(
            name="checkerboard",
            reason="Detected baked checkerboard background.",
        )

    stats = alpha_stats(image)
    if stats.has_real_transparency:
        return BackendSelection(
            name="alpha",
            reason="Input already has real alpha; skipped background model.",
        )

    return BackendSelection(
        name="rembg",
        reason="No real alpha or checkerboard background detected; using rembg.",
    )


def select_backend_for_path(path: Path, requested_backend: str = "auto") -> BackendSelection:
    return select_backend(load_image(path), requested_backend=requested_backend)


def options_for_cut(quality: QualityPreset, backend_name: str) -> ProcessingOptions:
    options = options_for_quality(quality)
    if backend_name in {"alpha", "checkerboard"} and quality != QualityPreset.pixel:
        return ProcessingOptions(
            mode=options.mode,
            edge_clean=options.edge_clean,
            trim=options.trim,
            pad=options.pad,
            remove_halo=False,
            hard_alpha=options.hard_alpha,
            keep_largest=options.keep_largest,
            alpha_threshold=options.alpha_threshold,
        )
    return options


def run_cut_file(
    input_path: Path,
    out: Path | None,
    report: Path | None,
    quality: QualityPreset,
    backend: str,
    overwrite: bool,
) -> CutResult:
    selection = select_backend_for_path(input_path, requested_backend=backend)
    output_path = default_output_path(input_path, out)
    report_path = default_report_path(output_path, report)

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}. Use --overwrite to replace it."
        )
    if report_path.exists() and not overwrite:
        raise FileExistsError(
            f"Report already exists: {report_path}. Use --overwrite to replace it."
        )

    process_result = process_image(
        input_path=input_path,
        output_path=output_path,
        backend_name=selection.name,
        model_name=None,
        options=options_for_cut(quality, selection.name),
        should_validate=True,
    )
    if process_result.validation is None:
        raise RuntimeError("Internal error: cut did not produce a validation report.")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(process_result.validation.to_dict(), indent=2),
        encoding="utf-8",
    )

    return CutResult(
        input_path=input_path,
        output_path=process_result.output_path,
        report_path=report_path,
        preview_path=None,
        backend_name=selection.name,
        reason=selection.reason,
        validation_ok=process_result.validation.ok,
    )


def run_cut_batch(
    input_folder: Path,
    out: Path | None,
    manifest: Path | None,
    quality: QualityPreset,
    backend: str,
    recursive: bool,
    overwrite: bool,
    fail_fast: bool,
) -> CutBatchResult:
    output_folder = default_batch_output_folder(input_folder, out)
    manifest_path = default_manifest_path(output_folder, manifest)
    files = iter_image_files(input_folder, recursive=recursive)

    records: list[BatchRecord] = []
    processed = 0
    skipped = 0
    failed = 0

    for input_file in files:
        relative = input_file.relative_to(input_folder)
        output_path = (output_folder / relative).with_suffix(".png")
        output_path = output_path.with_name(f"{output_path.stem}-cutout.png")
        report_path = output_path.with_name(f"{output_path.stem}-report.json")

        if output_path.exists() and not overwrite:
            skipped += 1
            records.append(
                BatchRecord(
                    input=str(input_file),
                    output=str(output_path),
                    status="skipped",
                    ok=True,
                )
            )
            continue

        try:
            result = run_cut_file(
                input_path=input_file,
                out=output_path,
                report=report_path,
                quality=quality,
                backend=backend,
                overwrite=True,
            )
            processed += 1
            if not result.validation_ok:
                failed += 1
            records.append(
                BatchRecord(
                    input=str(input_file),
                    output=str(result.output_path),
                    status="processed",
                    ok=result.validation_ok,
                    validation=_cut_record_metadata(result),
                )
            )
            if fail_fast and not result.validation_ok:
                break
        except Exception as exc:
            failed += 1
            records.append(
                BatchRecord(
                    input=str(input_file),
                    output=str(output_path),
                    status="failed",
                    ok=False,
                    error=str(exc),
                )
            )
            if fail_fast:
                break

    summary = BatchSummary(
        found=len(files),
        processed=processed,
        skipped=skipped,
        failed=failed,
    )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "summary": summary.to_dict(),
                "files": [record.to_dict() for record in records],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return CutBatchResult(
        output_folder=output_folder,
        manifest_path=manifest_path,
        preview_path=None,
        summary=summary,
        records=records,
    )


def _cut_record_metadata(result: CutResult) -> dict[str, Any]:
    return {
        "backend": result.backend_name,
        "reason": result.reason,
        "report": str(result.report_path),
    }
