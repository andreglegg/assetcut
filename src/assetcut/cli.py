from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.table import Table

from assetcut import __version__
from assetcut import api as assetcut_api
from assetcut.alpha import add_transparent_padding, trim_to_alpha
from assetcut.atlas import build_atlas
from assetcut.batch import BatchRecord, BatchSummary
from assetcut.config import AssetMode, EdgeClean, ProcessingOptions, QualityPreset, options_for_mode
from assetcut.cut import (
    CutBatchResult,
    CutResult,
    default_output_path,
    run_cut_batch,
    run_cut_file,
    select_backend_for_path,
    with_batch_preview,
    with_file_preview,
)
from assetcut.engine import process_image
from assetcut.image_io import iter_image_files, load_image, save_png_rgba
from assetcut.preview import (
    create_file_preview,
    create_folder_preview,
    default_preview_path,
)
from assetcut.validate import ValidationReport, validate_folder, validate_image

app = typer.Typer(
    name="assetcut",
    help="Remove backgrounds from game assets and export real transparent PNGs.",
    no_args_is_help=True,
)
console = Console()


def _merged_options(
    mode: AssetMode,
    edge_clean: EdgeClean | None,
    trim: bool | None,
    pad: int | None,
    remove_halo: bool,
    hard_alpha: bool,
    keep_largest: bool,
    alpha_threshold: int,
) -> ProcessingOptions:
    if pad is not None and pad < 0:
        raise typer.BadParameter("--pad must be greater than or equal to 0.")
    if alpha_threshold < -1 or alpha_threshold > 255:
        raise typer.BadParameter("--alpha-threshold must be between 0 and 255.")

    defaults = options_for_mode(mode)
    return ProcessingOptions(
        mode=mode,
        edge_clean=edge_clean if edge_clean is not None else defaults.edge_clean,
        trim=trim if trim is not None else defaults.trim,
        pad=pad if pad is not None else defaults.pad,
        remove_halo=remove_halo or defaults.remove_halo,
        hard_alpha=hard_alpha or defaults.hard_alpha,
        keep_largest=keep_largest or defaults.keep_largest,
        alpha_threshold=alpha_threshold if alpha_threshold >= 0 else defaults.alpha_threshold,
    )


def _print_validation(report: ValidationReport) -> None:
    status = "OK" if report.ok else "FAILED"
    console.print(f"[bold]{status}[/bold] {report.path}")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Message")
    for check in report.checks:
        table.add_row(check.name, check.status, check.message)
    console.print(table)
    for warning in report.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")


def _exit_with_error(exc: Exception) -> NoReturn:
    console.print(f"[red]Error:[/red] {exc}")
    raise typer.Exit(code=1) from exc


def _print_cut_result(result: CutResult) -> None:
    console.print(result.reason)
    console.print(f"Backend: [bold]{result.backend_name}[/bold]")
    console.print(f"[green]Wrote[/green] {result.output_path}")
    console.print(f"[green]Report[/green] {result.report_path}")
    if result.preview_path:
        console.print(f"[green]Preview[/green] {result.preview_path}")
    console.print(f"PNG RGBA: {'yes' if result.validation_ok else 'failed validation'}")
    console.print(f"Real alpha: {'yes' if result.validation_ok else 'failed validation'}")


def _print_cut_batch_result(result: CutBatchResult) -> None:
    console.print(f"[green]Output folder[/green] {result.output_folder}")
    console.print(f"[green]Manifest[/green] {result.manifest_path}")
    if result.preview_path:
        console.print(f"[green]Preview[/green] {result.preview_path}")
    console.print(
        "Batch summary: "
        f"{result.summary.processed} processed, "
        f"{result.summary.skipped} skipped, "
        f"{result.summary.failed} failed "
        f"({result.summary.found} found)."
    )


def _reveal_path(path: Path) -> None:
    if sys.platform == "darwin":
        command = ["open", str(path)] if path.is_dir() else ["open", "-R", str(path)]
        subprocess.run(command, check=False)
        return
    console.print(f"Reveal is only supported on macOS. Output: {path}")


def _print_json(payload: object) -> None:
    console.print_json(json.dumps(payload, indent=2))


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", help="Show AssetCut version."),
    ] = False,
) -> None:
    if version:
        console.print(__version__)
        raise typer.Exit()


@app.command()
def cut(
    path: Annotated[Path, typer.Argument(help="Input image or folder.")],
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Output PNG path or folder."),
    ] = None,
    quality: Annotated[
        QualityPreset,
        typer.Option("--quality", help="Cutout quality preset."),
    ] = QualityPreset.crisp,
    backend: Annotated[
        str,
        typer.Option("--backend", help="Backend name or auto."),
    ] = "auto",
    recursive: Annotated[
        bool,
        typer.Option("--recursive/--flat", help="Process folder subdirectories."),
    ] = True,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite outputs.")] = False,
    fail_fast: Annotated[
        bool,
        typer.Option("--fail-fast", help="Stop folder cuts on first failure."),
    ] = False,
    report: Annotated[
        Path | None,
        typer.Option("--report", help="Single-image report JSON path."),
    ] = None,
    manifest: Annotated[
        Path | None,
        typer.Option("--manifest", help="Folder manifest JSON path."),
    ] = None,
    preview_output: Annotated[
        bool,
        typer.Option("--preview", help="Create a QA preview image after cutting."),
    ] = False,
    preview_path: Annotated[
        Path | None,
        typer.Option("--preview-out", help="Preview PNG path."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print structured JSON output."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan outputs and backend without writing files."),
    ] = False,
    reveal: Annotated[bool, typer.Option("--reveal", help="Reveal output in Finder.")] = False,
    open_output: Annotated[bool, typer.Option("--open", help="Alias for --reveal.")] = False,
) -> None:
    """Friendly cutout command with auto backend selection and reports."""
    try:
        if dry_run:
            response = (
                assetcut_api.cut_folder(
                    input_folder=path,
                    output_folder=out,
                    manifest_path=manifest,
                    quality=quality,
                    backend=backend,
                    recursive=recursive,
                    preview=preview_output,
                    preview_path=preview_path,
                    dry_run=True,
                )
                if path.is_dir()
                else assetcut_api.cut_image(
                    input_path=path,
                    output_path=out,
                    report_path=report,
                    quality=quality,
                    backend=backend,
                    preview=preview_output,
                    preview_path=preview_path,
                    dry_run=True,
                )
            )
            if json_output:
                _print_json(response)
            else:
                _print_json(response)
            raise typer.Exit(code=0 if response.get("ok") else 1)

        if path.is_dir():
            batch_result = run_cut_batch(
                input_folder=path,
                out=out,
                manifest=manifest,
                quality=quality,
                backend=backend,
                recursive=recursive,
                overwrite=overwrite,
                fail_fast=fail_fast,
            )
            if preview_output:
                generated_preview = create_folder_preview(
                    folder=batch_result.output_folder,
                    output_path=default_preview_path(batch_result.output_folder, preview_path),
                    recursive=True,
                )
                batch_result = with_batch_preview(batch_result, generated_preview)
            if json_output:
                _print_json(batch_result.to_dict())
            else:
                _print_cut_batch_result(batch_result)
            if reveal or open_output:
                _reveal_path(batch_result.output_folder)
            raise typer.Exit(code=1 if batch_result.summary.failed else 0)

        cut_result = run_cut_file(
            input_path=path,
            out=out,
            report=report,
            quality=quality,
            backend=backend,
            overwrite=overwrite,
        )
        if preview_output:
            generated_preview = create_file_preview(
                input_path=path,
                output_path=default_preview_path(path, preview_path),
                cutout_path=cut_result.output_path,
            )
            cut_result = with_file_preview(cut_result, generated_preview)
        if json_output:
            _print_json(cut_result.to_dict())
        else:
            _print_cut_result(cut_result)
        if reveal or open_output:
            _reveal_path(cut_result.output_path)
        raise typer.Exit(code=0 if cut_result.validation_ok else 1)
    except typer.Exit:
        raise
    except Exception as exc:
        if json_output:
            _print_json(assetcut_api.error_response(exc))
            raise typer.Exit(code=1) from exc
        _exit_with_error(exc)


@app.command()
def doctor() -> None:
    """Check local dependency availability."""
    console.print("[bold]AssetCut doctor[/bold]")
    console.print(f"Version: {__version__}")

    checks: list[tuple[str, bool, str]] = []
    checks.append(("alpha backend", True, "built in"))
    checks.append(("checkerboard backend", True, "built in"))

    try:
        import PIL  # noqa: F401

        checks.append(("Pillow", True, "installed"))
    except Exception as exc:
        checks.append(("Pillow", False, str(exc)))

    try:
        import cv2  # noqa: F401

        checks.append(("OpenCV", True, "installed"))
    except Exception as exc:
        checks.append(("OpenCV", False, str(exc)))

    try:
        import rembg  # noqa: F401

        checks.append(("rembg", True, "installed"))
    except Exception:
        checks.append(("rembg", False, "optional backend missing, run: pip install -e '.[rembg]'"))

    try:
        import transparent_background  # noqa: F401

        checks.append(("transparent-background", True, "installed"))
    except Exception:
        checks.append(
            (
                "transparent-background",
                False,
                "optional InSPyReNet backend missing",
            )
        )

    table = Table(show_header=True, header_style="bold")
    table.add_column("Dependency")
    table.add_column("Available")
    table.add_column("Note")
    for name, ok, note in checks:
        table.add_row(name, "yes" if ok else "no", note)
    console.print(table)


@app.command()
def remove(
    input_path: Annotated[Path, typer.Argument(help="Input image path.")],
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Output PNG path."),
    ] = None,
    backend: Annotated[str, typer.Option("--backend", help="Backend name or auto.")] = "auto",
    model: Annotated[str | None, typer.Option("--model", help="Backend model name.")] = None,
    mode: Annotated[
        AssetMode,
        typer.Option("--mode", help="Asset processing profile."),
    ] = AssetMode.prop,
    edge_clean: Annotated[
        EdgeClean | None,
        typer.Option("--edge-clean", help="Alpha edge cleanup strength."),
    ] = None,
    trim: Annotated[
        bool | None,
        typer.Option("--trim/--no-trim", help="Trim alpha bounds."),
    ] = None,
    pad: Annotated[
        int | None,
        typer.Option("--pad", help="Transparent padding after trim."),
    ] = None,
    remove_halo: Annotated[
        bool,
        typer.Option("--remove-halo", help="Clean RGB matte at edges."),
    ] = False,
    hard_alpha: Annotated[
        bool,
        typer.Option("--hard-alpha", help="Threshold alpha to binary."),
    ] = False,
    keep_largest: Annotated[
        bool,
        typer.Option("--keep-largest", help="Keep only largest foreground island."),
    ] = False,
    alpha_threshold: Annotated[
        int,
        typer.Option("--alpha-threshold", help="Alpha threshold for mask operations."),
    ] = -1,
    validate: Annotated[
        bool,
        typer.Option("--validate", help="Validate output after save."),
    ] = False,
    report: Annotated[
        Path | None,
        typer.Option("--report", help="Write validation report JSON."),
    ] = None,
) -> None:
    """Remove background from one image."""
    backend_name = backend
    reason: str | None = None
    if backend.strip().lower() == "auto":
        try:
            selection = select_backend_for_path(input_path, requested_backend=backend)
        except Exception as exc:
            _exit_with_error(exc)
        backend_name = selection.name
        reason = selection.reason
        if edge_clean is None and backend_name in {"alpha", "checkerboard"}:
            edge_clean = EdgeClean.none

    options = _merged_options(
        mode=mode,
        edge_clean=edge_clean,
        trim=trim,
        pad=pad,
        remove_halo=remove_halo,
        hard_alpha=hard_alpha,
        keep_largest=keep_largest,
        alpha_threshold=alpha_threshold,
    )

    try:
        output_path = default_output_path(input_path, out)
        result = process_image(
            input_path=input_path,
            output_path=output_path,
            backend_name=backend_name,
            model_name=model,
            options=options,
            should_validate=validate or report is not None,
        )
    except Exception as exc:
        _exit_with_error(exc)

    if reason:
        console.print(reason)
        console.print(f"Backend: [bold]{backend_name}[/bold]")
    console.print(f"[green]Wrote[/green] {result.output_path}")

    if result.validation:
        _print_validation(result.validation)
        if report:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result.validation.to_dict(), indent=2), encoding="utf-8")


@app.command()
def batch(
    input_folder: Annotated[Path, typer.Argument(help="Input folder.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output folder.")],
    backend: Annotated[str, typer.Option("--backend", help="Backend name.")] = "rembg",
    model: Annotated[str | None, typer.Option("--model", help="Backend model name.")] = None,
    recursive: Annotated[bool, typer.Option("--recursive", help="Process subfolders.")] = False,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Overwrite existing outputs."),
    ] = False,
    fail_fast: Annotated[bool, typer.Option("--fail-fast", help="Stop at first failure.")] = False,
    mode: Annotated[
        AssetMode,
        typer.Option("--mode", help="Asset processing profile."),
    ] = AssetMode.prop,
    edge_clean: Annotated[EdgeClean | None, typer.Option("--edge-clean")] = None,
    trim: Annotated[bool | None, typer.Option("--trim/--no-trim")] = None,
    pad: Annotated[int | None, typer.Option("--pad")] = None,
    remove_halo: Annotated[bool, typer.Option("--remove-halo")] = False,
    hard_alpha: Annotated[bool, typer.Option("--hard-alpha")] = False,
    keep_largest: Annotated[bool, typer.Option("--keep-largest")] = False,
    alpha_threshold: Annotated[int, typer.Option("--alpha-threshold")] = -1,
    validate: Annotated[bool, typer.Option("--validate")] = False,
    manifest: Annotated[Path | None, typer.Option("--manifest")] = None,
) -> None:
    """Remove backgrounds from a folder of images."""
    options = _merged_options(
        mode=mode,
        edge_clean=edge_clean,
        trim=trim,
        pad=pad,
        remove_halo=remove_halo,
        hard_alpha=hard_alpha,
        keep_largest=keep_largest,
        alpha_threshold=alpha_threshold,
    )

    files = iter_image_files(input_folder, recursive=recursive)
    out.mkdir(parents=True, exist_ok=True)

    records: list[BatchRecord] = []
    processed = 0
    skipped = 0
    failures = 0

    for file in files:
        relative = file.relative_to(input_folder)
        output_path = (out / relative).with_suffix(".png")
        if output_path.exists() and not overwrite:
            console.print(f"[yellow]Skip existing[/yellow] {output_path}")
            skipped += 1
            records.append(
                BatchRecord(
                    input=str(file),
                    output=str(output_path),
                    status="skipped",
                    ok=True,
                )
            )
            continue

        try:
            result = process_image(
                input_path=file,
                output_path=output_path,
                backend_name=backend,
                model_name=model,
                options=options,
                should_validate=validate,
            )
            processed += 1
            ok = result.validation.ok if result.validation else True
            if not ok:
                failures += 1
            console.print(
                f"[green]Wrote[/green] {result.output_path}"
                if ok
                else f"[yellow]Wrote with validation issues[/yellow] {result.output_path}"
            )
            records.append(
                BatchRecord(
                    input=str(file),
                    output=str(result.output_path),
                    status="processed",
                    ok=ok,
                    validation=result.validation.to_dict() if result.validation else None,
                )
            )
            if fail_fast and not ok:
                raise typer.Exit(code=1)
        except typer.Exit:
            raise
        except Exception as exc:
            failures += 1
            console.print(f"[red]Failed[/red] {file}: {exc}")
            records.append(
                BatchRecord(
                    input=str(file),
                    output=str(output_path),
                    status="failed",
                    ok=False,
                    error=str(exc),
                )
            )
            if fail_fast:
                raise typer.Exit(code=1) from exc

    summary = BatchSummary(
        found=len(files),
        processed=processed,
        skipped=skipped,
        failed=failures,
    )

    if manifest:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "summary": summary.to_dict(),
                    "files": [record.to_dict() for record in records],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    console.print(
        "Batch summary: "
        f"{summary.processed} processed, "
        f"{summary.skipped} skipped, "
        f"{summary.failed} failed "
        f"({summary.found} found)."
    )


@app.command(name="validate")
def validate_cmd(
    path: Annotated[Path, typer.Argument(help="PNG file or folder.")],
    recursive: Annotated[bool, typer.Option("--recursive", help="Validate subfolders.")] = False,
    report: Annotated[Path | None, typer.Option("--report", help="Write JSON report.")] = None,
) -> None:
    """Validate real transparency."""
    if path.is_dir():
        reports = validate_folder(path, recursive=recursive)
        for item in reports:
            _print_validation(item)
        payload: object = [item.to_dict() for item in reports]
        exit_code = 0 if all(item.ok for item in reports) else 1
    else:
        item = validate_image(path)
        _print_validation(item)
        payload = item.to_dict()
        exit_code = 0 if item.ok else 1

    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    raise typer.Exit(code=exit_code)


@app.command()
def trim(
    input_path: Annotated[Path, typer.Argument(help="Input PNG path.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output PNG path.")],
    pad: Annotated[int, typer.Option("--pad", help="Transparent padding.")] = 0,
    alpha_threshold: Annotated[int, typer.Option("--alpha-threshold")] = 1,
) -> None:
    """Trim transparent bounds and optionally add padding."""
    try:
        image = load_image(input_path)
        trimmed = trim_to_alpha(image, threshold=alpha_threshold)
        padded = add_transparent_padding(trimmed, pad)
        save_png_rgba(padded, out)
    except Exception as exc:
        _exit_with_error(exc)
    console.print(f"[green]Wrote[/green] {out}")


@app.command()
def atlas(
    folder: Annotated[Path, typer.Argument(help="Folder of PNG cutouts.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output atlas PNG.")],
    json_path: Annotated[Path, typer.Option("--json", help="Output atlas JSON.")],
    max_size: Annotated[int, typer.Option("--max-size", help="Maximum atlas width/height.")] = 4096,
    padding: Annotated[int, typer.Option("--padding", help="Pixels between frames.")] = 8,
) -> None:
    """Pack cutout PNG files into a simple atlas."""
    result = build_atlas(folder, max_size=max_size, padding=padding)
    save_png_rgba(result.image, out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result.to_json_dict(), indent=2), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {out}")
    console.print(f"[green]Wrote[/green] {json_path}")


@app.command()
def preview(
    path: Annotated[Path, typer.Argument(help="Input image, cutout, or folder.")],
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Output preview PNG path."),
    ] = None,
    cutout: Annotated[
        Path | None,
        typer.Option("--cutout", help="Cutout PNG for a before/after preview."),
    ] = None,
    recursive: Annotated[
        bool,
        typer.Option("--recursive/--flat", help="Include folder subdirectories."),
    ] = True,
    max_items: Annotated[
        int,
        typer.Option("--max-items", help="Maximum folder images to include."),
    ] = 40,
) -> None:
    """Create a light/dark preview contact sheet."""
    try:
        output_path = default_preview_path(path, out)
        if path.is_dir():
            result = create_folder_preview(
                folder=path,
                output_path=output_path,
                recursive=recursive,
                max_items=max_items,
            )
        else:
            result = create_file_preview(
                input_path=path,
                output_path=output_path,
                cutout_path=cutout,
            )
    except Exception as exc:
        _exit_with_error(exc)

    console.print(f"[green]Wrote[/green] {result}")


@app.command()
def compare(
    input_path: Annotated[Path, typer.Argument(help="Input image path.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output folder.")],
    backends: Annotated[
        str,
        typer.Option("--backends", help="Comma-separated backends."),
    ] = "rembg",
) -> None:
    """Run multiple backends and save separate outputs."""
    out.mkdir(parents=True, exist_ok=True)
    names = [name.strip() for name in backends.split(",") if name.strip()]
    options = options_for_mode(AssetMode.prop)

    for name in names:
        output_path = out / f"{input_path.stem}.{name}.png"
        process_image(
            input_path=input_path,
            output_path=output_path,
            backend_name=name,
            model_name=None,
            options=options,
            should_validate=True,
        )
        console.print(f"[green]Wrote[/green] {output_path}")
