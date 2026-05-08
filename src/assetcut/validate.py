from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from assetcut.alpha import (
    alpha_stats,
    edge_matte_warning,
    looks_like_baked_checkerboard,
    transparent_rgb_is_clean,
)
from assetcut.image_io import ensure_rgba, load_image


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    path: str
    ok: bool
    mode: str
    width: int
    height: int
    alpha: dict[str, int | bool]
    checks: list[CheckResult]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def validate_image(path: Path, strict_checkerboard: bool = False) -> ValidationReport:
    checks: list[CheckResult] = []
    warnings: list[str] = []

    try:
        image = load_image(path)
    except Exception as exc:
        return ValidationReport(
            path=str(path),
            ok=False,
            mode="unreadable",
            width=0,
            height=0,
            alpha={
                "has_alpha": False,
                "min": 255,
                "max": 255,
                "transparent_pixels": 0,
                "semi_transparent_pixels": 0,
                "opaque_pixels": 0,
                "total_pixels": 0,
            },
            checks=[
                CheckResult(
                    name="readable",
                    status="fail",
                    message=f"Could not read image: {exc}",
                )
            ],
            warnings=[],
        )

    width, height = image.size
    is_png = path.suffix.lower() == ".png" and image.format == "PNG"
    checks.append(
        CheckResult(
            name="png_file",
            status="pass" if is_png else "fail",
            message="Output should be PNG for real alpha cutouts.",
        )
    )

    rgba = ensure_rgba(image)
    source_stats = alpha_stats(image)
    mode_ok = image.mode in {"RGBA", "LA"}

    checks.append(
        CheckResult(
            name="rgba",
            status="pass" if mode_ok and rgba.mode == "RGBA" else "fail",
            message=f"Image mode is {image.mode}; validated mode is {rgba.mode}.",
        )
    )

    checks.append(
        CheckResult(
            name="real_alpha",
            status="pass" if source_stats.has_real_transparency else "fail",
            message="Image must contain fully transparent pixels, not only a fake background.",
        )
    )

    checkerboard = looks_like_baked_checkerboard(image)
    checker_status = (
        "fail" if checkerboard and strict_checkerboard else "warn" if checkerboard else "pass"
    )
    checks.append(
        CheckResult(
            name="baked_checkerboard",
            status=checker_status,
            message=(
                "Checkerboard-like pixels detected."
                if checkerboard
                else "No obvious checkerboard."
            ),
        )
    )
    if checkerboard:
        warnings.append("Image may contain baked checkerboard transparency.")

    transparent_rgb_clean = transparent_rgb_is_clean(rgba)
    checks.append(
        CheckResult(
            name="transparent_rgb_clean",
            status="pass" if transparent_rgb_clean else "fail",
            message=(
                "RGB is cleared under fully transparent pixels."
                if transparent_rgb_clean
                else "RGB data exists under fully transparent pixels."
            ),
        )
    )

    matte_warning = edge_matte_warning(rgba)
    if matte_warning:
        checks.append(
            CheckResult(
                name="edge_matte",
                status="warn",
                message=matte_warning,
            )
        )
        warnings.append(matte_warning)
    else:
        checks.append(
            CheckResult(
                name="edge_matte",
                status="pass",
                message="No obvious white or gray matte on semi-transparent edges.",
            )
        )

    if source_stats.transparent_pixels == 0:
        warnings.append("No fully transparent pixels found.")

    if source_stats.semi_transparent_pixels > 0 and source_stats.transparent_pixels == 0:
        warnings.append("Image has semi-transparent pixels but no fully transparent background.")

    ok = all(check.status != "fail" for check in checks)

    return ValidationReport(
        path=str(path),
        ok=ok,
        mode=rgba.mode,
        width=width,
        height=height,
        alpha={
            "has_alpha": source_stats.has_alpha,
            "min": source_stats.min_alpha,
            "max": source_stats.max_alpha,
            "transparent_pixels": source_stats.transparent_pixels,
            "semi_transparent_pixels": source_stats.semi_transparent_pixels,
            "opaque_pixels": source_stats.opaque_pixels,
            "total_pixels": source_stats.total_pixels,
        },
        checks=checks,
        warnings=warnings,
    )


def validate_folder(folder: Path, recursive: bool) -> list[ValidationReport]:
    from assetcut.image_io import iter_image_files

    return [validate_image(path) for path in iter_image_files(folder, recursive=recursive)]
