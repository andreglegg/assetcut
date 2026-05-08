from __future__ import annotations

from typing import Any

from assetcut import api

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised only without optional extra.
    raise RuntimeError("Install MCP support with: pip install -e '.[mcp]'") from exc


mcp = FastMCP("AssetCut", json_response=True)


@mcp.tool()
def assetcut_cut_image(
    input_path: str,
    output_path: str | None = None,
    report_path: str | None = None,
    quality: str = "crisp",
    backend: str = "auto",
    overwrite: bool = False,
    preview: bool = False,
    preview_path: str | None = None,
    dry_run: bool = False,
    base_dir: str | None = None,
) -> dict[str, Any]:
    """Remove a background from one local image and write a real transparent PNG."""
    return api.cut_image(
        input_path=input_path,
        output_path=output_path,
        report_path=report_path,
        quality=quality,
        backend=backend,
        overwrite=overwrite,
        preview=preview,
        preview_path=preview_path,
        dry_run=dry_run,
        base_dir=base_dir,
    )


@mcp.tool()
def assetcut_cut_folder(
    input_folder: str,
    output_folder: str | None = None,
    manifest_path: str | None = None,
    quality: str = "crisp",
    backend: str = "auto",
    recursive: bool = True,
    overwrite: bool = False,
    fail_fast: bool = False,
    preview: bool = False,
    preview_path: str | None = None,
    dry_run: bool = False,
    max_files: int = api.DEFAULT_MAX_BATCH_FILES,
    base_dir: str | None = None,
) -> dict[str, Any]:
    """Cut a folder of local images and write PNG cutouts plus a manifest."""
    return api.cut_folder(
        input_folder=input_folder,
        output_folder=output_folder,
        manifest_path=manifest_path,
        quality=quality,
        backend=backend,
        recursive=recursive,
        overwrite=overwrite,
        fail_fast=fail_fast,
        preview=preview,
        preview_path=preview_path,
        dry_run=dry_run,
        max_files=max_files,
        base_dir=base_dir,
    )


@mcp.tool()
def assetcut_validate(
    path: str,
    recursive: bool = True,
    base_dir: str | None = None,
) -> dict[str, Any]:
    """Validate that a local image or folder contains real transparent PNG cutouts."""
    return api.validate(path=path, recursive=recursive, base_dir=base_dir)


@mcp.tool()
def assetcut_preview(
    path: str,
    output_path: str | None = None,
    cutout_path: str | None = None,
    recursive: bool = True,
    max_items: int = 40,
    base_dir: str | None = None,
) -> dict[str, Any]:
    """Create a local light/dark/color preview contact sheet for cutout QA."""
    return api.preview(
        path=path,
        output_path=output_path,
        cutout_path=cutout_path,
        recursive=recursive,
        max_items=max_items,
        base_dir=base_dir,
    )


@mcp.tool()
def assetcut_doctor() -> dict[str, Any]:
    """Report local AssetCut dependency and backend availability."""
    return api.doctor()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
