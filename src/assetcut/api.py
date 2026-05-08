from __future__ import annotations

import importlib.util
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from assetcut.config import QualityPreset
from assetcut.cut import (
    default_batch_output_folder,
    default_manifest_path,
    default_output_path,
    default_report_path,
    run_cut_batch,
    run_cut_file,
    select_backend_for_path,
    with_batch_preview,
    with_file_preview,
)
from assetcut.image_io import iter_image_files
from assetcut.preview import (
    create_file_preview,
    create_folder_preview,
    default_preview_path,
)
from assetcut.validate import validate_folder, validate_image

DEFAULT_MAX_BATCH_FILES = 500


@dataclass(frozen=True)
class ErrorPayload:
    code: str
    message: str
    path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunFileResult:
    ok: bool
    dry_run: bool
    input: str
    output: str
    report: str
    preview: str | None
    backend: str
    reason: str
    output_exists: bool
    report_exists: bool
    preview_exists: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunFolderResult:
    ok: bool
    dry_run: bool
    input_folder: str
    output_folder: str
    manifest: str
    preview: str | None
    recursive: bool
    file_count: int
    max_files: int
    manifest_exists: bool
    preview_exists: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def cut_image(
    input_path: str | Path,
    output_path: str | Path | None = None,
    report_path: str | Path | None = None,
    quality: str | QualityPreset = QualityPreset.crisp,
    backend: str = "auto",
    overwrite: bool = False,
    preview: bool = False,
    preview_path: str | Path | None = None,
    dry_run: bool = False,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    try:
        input_file = _resolve_input_path(input_path, base_dir=base_dir, must_be_dir=False)
        assert input_file is not None
        output_file = _resolve_output_path(output_path, base_dir=base_dir)
        report_file = _resolve_output_path(report_path, base_dir=base_dir)
        preview_file = _resolve_output_path(preview_path, base_dir=base_dir)
        quality_preset = _quality(quality)

        if dry_run:
            return dry_run_cut_image(
                input_file,
                output_path=output_file,
                report_path=report_file,
                quality=quality_preset,
                backend=backend,
                preview=preview,
                preview_path=preview_file,
            ).to_dict()

        result = run_cut_file(
            input_path=input_file,
            out=output_file,
            report=report_file,
            quality=quality_preset,
            backend=backend,
            overwrite=overwrite,
        )
        if preview:
            generated_preview = create_file_preview(
                input_path=input_file,
                output_path=default_preview_path(input_file, preview_file),
                cutout_path=result.output_path,
            )
            result = with_file_preview(result, generated_preview)
        return result.to_dict()
    except Exception as exc:
        return error_response(exc)


def cut_folder(
    input_folder: str | Path,
    output_folder: str | Path | None = None,
    manifest_path: str | Path | None = None,
    quality: str | QualityPreset = QualityPreset.crisp,
    backend: str = "auto",
    recursive: bool = True,
    overwrite: bool = False,
    fail_fast: bool = False,
    preview: bool = False,
    preview_path: str | Path | None = None,
    dry_run: bool = False,
    max_files: int = DEFAULT_MAX_BATCH_FILES,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    try:
        folder = _resolve_input_path(input_folder, base_dir=base_dir, must_be_dir=True)
        assert folder is not None
        output_dir = _resolve_output_path(output_folder, base_dir=base_dir)
        manifest_file = _resolve_output_path(manifest_path, base_dir=base_dir)
        preview_file = _resolve_output_path(preview_path, base_dir=base_dir)
        quality_preset = _quality(quality)
        files = iter_image_files(folder, recursive=recursive)
        _check_batch_size(files, max_files=max_files)

        if dry_run:
            return dry_run_cut_folder(
                folder,
                output_folder=output_dir,
                manifest_path=manifest_file,
                recursive=recursive,
                preview=preview,
                preview_path=preview_file,
                max_files=max_files,
                file_count=len(files),
            ).to_dict()

        result = run_cut_batch(
            input_folder=folder,
            out=output_dir,
            manifest=manifest_file,
            quality=quality_preset,
            backend=backend,
            recursive=recursive,
            overwrite=overwrite,
            fail_fast=fail_fast,
        )
        if preview:
            generated_preview = create_folder_preview(
                folder=result.output_folder,
                output_path=default_preview_path(result.output_folder, preview_file),
                recursive=True,
            )
            result = with_batch_preview(result, generated_preview)
        return result.to_dict()
    except Exception as exc:
        return error_response(exc)


def dry_run_cut_image(
    input_path: Path,
    output_path: Path | None,
    report_path: Path | None,
    quality: QualityPreset,
    backend: str,
    preview: bool,
    preview_path: Path | None,
) -> DryRunFileResult:
    output = default_output_path(input_path, output_path)
    report = default_report_path(output, report_path)
    preview_out = default_preview_path(input_path, preview_path) if preview else None
    selection = select_backend_for_path(input_path, requested_backend=backend)
    return DryRunFileResult(
        ok=True,
        dry_run=True,
        input=str(input_path),
        output=str(output),
        report=str(report),
        preview=str(preview_out) if preview_out else None,
        backend=selection.name,
        reason=selection.reason,
        output_exists=output.exists(),
        report_exists=report.exists(),
        preview_exists=preview_out.exists() if preview_out else False,
    )


def dry_run_cut_folder(
    input_folder: Path,
    output_folder: Path | None,
    manifest_path: Path | None,
    recursive: bool,
    preview: bool,
    preview_path: Path | None,
    max_files: int,
    file_count: int | None = None,
) -> DryRunFolderResult:
    output = default_batch_output_folder(input_folder, output_folder)
    manifest = default_manifest_path(output, manifest_path)
    preview_out = default_preview_path(output, preview_path) if preview else None
    count = (
        len(iter_image_files(input_folder, recursive=recursive))
        if file_count is None
        else file_count
    )
    _check_batch_size([Path()] * count, max_files=max_files)
    return DryRunFolderResult(
        ok=True,
        dry_run=True,
        input_folder=str(input_folder),
        output_folder=str(output),
        manifest=str(manifest),
        preview=str(preview_out) if preview_out else None,
        recursive=recursive,
        file_count=count,
        max_files=max_files,
        manifest_exists=manifest.exists(),
        preview_exists=preview_out.exists() if preview_out else False,
    )


def validate(
    path: str | Path,
    recursive: bool = True,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    try:
        resolved = _resolve_input_path(path, base_dir=base_dir, must_be_dir=None)
        assert resolved is not None
        if resolved.is_dir():
            reports = [
                report.to_dict() for report in validate_folder(resolved, recursive=recursive)
            ]
            return {
                "ok": all(bool(report["ok"]) for report in reports),
                "path": str(resolved),
                "recursive": recursive,
                "reports": reports,
            }
        report = validate_image(resolved)
        return report.to_dict()
    except Exception as exc:
        return error_response(exc)


def preview(
    path: str | Path,
    output_path: str | Path | None = None,
    cutout_path: str | Path | None = None,
    recursive: bool = True,
    max_items: int = 40,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    try:
        input_path = _resolve_input_path(path, base_dir=base_dir, must_be_dir=None)
        assert input_path is not None
        output = _resolve_output_path(output_path, base_dir=base_dir)
        cutout = _resolve_input_path(cutout_path, base_dir=base_dir, must_be_dir=False)
        preview_out = default_preview_path(input_path, output)

        if input_path.is_dir():
            result = create_folder_preview(
                folder=input_path,
                output_path=preview_out,
                recursive=recursive,
                max_items=max_items,
            )
        else:
            result = create_file_preview(
                input_path=input_path,
                output_path=preview_out,
                cutout_path=cutout,
            )
        return {
            "ok": True,
            "input": str(input_path),
            "output": str(result),
            "cutout": str(cutout) if cutout else None,
            "recursive": recursive,
        }
    except Exception as exc:
        return error_response(exc)


def doctor() -> dict[str, Any]:
    checks = {
        "pillow": importlib.util.find_spec("PIL") is not None,
        "opencv": importlib.util.find_spec("cv2") is not None,
        "rembg": importlib.util.find_spec("rembg") is not None,
        "transparent_background": importlib.util.find_spec("transparent_background") is not None,
        "alpha_backend": True,
        "checkerboard_backend": True,
    }
    return {"ok": checks["pillow"] and checks["opencv"], "checks": checks}


def _resolve_input_path(
    path: str | Path | None,
    base_dir: str | Path | None,
    must_be_dir: bool | None,
) -> Path | None:
    if path is None:
        return None
    resolved = _resolve_local_path(path, base_dir=base_dir)
    if must_be_dir is True and not resolved.is_dir():
        raise NotADirectoryError(f"Input path is not a folder: {resolved}")
    if must_be_dir is False and not resolved.is_file():
        raise FileNotFoundError(f"Input image does not exist: {resolved}")
    if must_be_dir is None and not resolved.exists():
        raise FileNotFoundError(f"Input path does not exist: {resolved}")
    return resolved


def _resolve_output_path(path: str | Path | None, base_dir: str | Path | None) -> Path | None:
    if path is None:
        return None
    return _resolve_local_path(path, base_dir=base_dir)


def _resolve_local_path(path: str | Path, base_dir: str | Path | None) -> Path:
    candidate = Path(path).expanduser()
    base = Path.cwd() if base_dir is None else Path(base_dir).expanduser().resolve()
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    if base_dir is not None and not _is_relative_to(resolved, base):
        raise PermissionError(f"Path is outside allowed base directory: {resolved}")
    return resolved


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _quality(value: str | QualityPreset) -> QualityPreset:
    if isinstance(value, QualityPreset):
        return value
    return QualityPreset(value)


def _check_batch_size(files: list[Path], max_files: int) -> None:
    if max_files < 1:
        raise ValueError(f"max_files must be at least 1: {max_files}")
    if len(files) > max_files:
        raise ValueError(f"Batch has {len(files)} files, over the max_files limit of {max_files}.")


def error_response(exc: Exception) -> dict[str, Any]:
    payload = _error_payload(exc)
    return {"ok": False, "error": payload.to_dict()}


def _error_payload(exc: Exception) -> ErrorPayload:
    message = str(exc)
    path = _path_from_message(message)
    if isinstance(exc, FileExistsError):
        return ErrorPayload(code="output_exists", message=message, path=path)
    if isinstance(exc, FileNotFoundError):
        return ErrorPayload(code="not_found", message=message, path=path)
    if isinstance(exc, NotADirectoryError):
        return ErrorPayload(code="not_directory", message=message, path=path)
    if isinstance(exc, PermissionError):
        return ErrorPayload(code="path_outside_base", message=message, path=path)
    if isinstance(exc, ValueError):
        return ErrorPayload(code="invalid_argument", message=message, path=path)
    return ErrorPayload(code="processing_failed", message=message, path=path)


def _path_from_message(message: str) -> str | None:
    if ": " not in message:
        return None
    possible_path = message.rsplit(": ", 1)[-1]
    if "/" in possible_path or possible_path.endswith(".png") or possible_path.endswith(".json"):
        return possible_path
    return None
