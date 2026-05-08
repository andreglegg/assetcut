from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from assetcut.alpha import add_transparent_padding, clear_rgb_where_alpha_zero, trim_to_alpha
from assetcut.config import ProcessingOptions
from assetcut.image_io import load_image, save_png_rgba
from assetcut.models import get_backend
from assetcut.postprocess import apply_processing
from assetcut.validate import ValidationReport, validate_image


@dataclass(frozen=True)
class ProcessResult:
    input_path: Path
    output_path: Path
    validation: ValidationReport | None


def process_image(
    input_path: Path,
    output_path: Path,
    backend_name: str,
    model_name: str | None,
    options: ProcessingOptions,
    should_validate: bool,
) -> ProcessResult:
    source = load_image(input_path)
    backend = get_backend(backend_name)
    cutout = backend.remove(source, model_name=model_name)

    processed: Image.Image = apply_processing(cutout, options)

    if options.trim:
        processed = trim_to_alpha(processed, threshold=options.alpha_threshold)

    if options.pad > 0:
        processed = add_transparent_padding(processed, options.pad)

    processed = clear_rgb_where_alpha_zero(processed)
    saved_path = save_png_rgba(processed, output_path)

    report = validate_image(saved_path) if should_validate else None
    return ProcessResult(input_path=input_path, output_path=saved_path, validation=report)
