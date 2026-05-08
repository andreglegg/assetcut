from __future__ import annotations

from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from assetcut.alpha import clear_rgb_where_alpha_zero, hard_alpha
from assetcut.config import EdgeClean, ProcessingOptions
from assetcut.image_io import ensure_rgba


def clean_alpha_edges(image: Image.Image, level: EdgeClean) -> Image.Image:
    rgba = ensure_rgba(image)
    if level == EdgeClean.none:
        return rgba

    arr = np.array(rgba, dtype=np.uint8)
    alpha = arr[:, :, 3]

    if level == EdgeClean.light:
        kernel_size = 3
        blur_sigma = 0.45
        iterations = 0
    elif level == EdgeClean.medium:
        kernel_size = 3
        blur_sigma = 0.75
        iterations = 1
    else:
        kernel_size = 5
        blur_sigma = 0.95
        iterations = 1

    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
    cleaned: NDArray[np.uint8] = alpha.copy()

    if iterations > 0:
        cleaned = cast(
            NDArray[np.uint8],
            cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=iterations),
        )
        cleaned = cast(
            NDArray[np.uint8],
            cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1),
        )

    cleaned = cast(
        NDArray[np.uint8],
        cv2.GaussianBlur(cleaned, (kernel_size, kernel_size), blur_sigma),
    )
    cleaned = np.where(alpha > 0, cleaned, 0).astype(np.uint8)
    arr[:, :, 3] = np.clip(cleaned, 0, 255).astype(np.uint8)

    return clear_rgb_where_alpha_zero(Image.fromarray(arr, mode="RGBA"))


def keep_largest_component(image: Image.Image, threshold: int = 8) -> Image.Image:
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    alpha = arr[:, :, 3]
    mask = (alpha >= threshold).astype(np.uint8)

    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 2:
        return rgba

    areas = stats[1:, cv2.CC_STAT_AREA]
    largest_label = int(np.argmax(areas)) + 1
    keep = labels == largest_label
    arr[~keep, 3] = 0
    arr[~keep, :3] = 0

    return Image.fromarray(arr, mode="RGBA")


def remove_edge_halo(image: Image.Image) -> Image.Image:
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    alpha = arr[:, :, 3]

    opaque = alpha >= 245
    edge = (alpha > 0) & (alpha < 245)

    if not np.any(edge) or not np.any(opaque):
        return clear_rgb_where_alpha_zero(rgba)

    rgb = arr[:, :, :3].copy()
    unknown = (~opaque).astype(np.uint8) * 255

    repaired_channels: list[np.ndarray] = []
    for channel_index in range(3):
        channel = rgb[:, :, channel_index]
        repaired = cv2.inpaint(channel, unknown, 3, cv2.INPAINT_TELEA)
        repaired_channels.append(repaired)

    repaired_rgb = np.stack(repaired_channels, axis=2)
    arr[edge, :3] = repaired_rgb[edge, :3]
    arr[alpha == 0, :3] = 0

    return Image.fromarray(arr, mode="RGBA")


def apply_processing(image: Image.Image, options: ProcessingOptions) -> Image.Image:
    out = ensure_rgba(image)

    if options.keep_largest:
        out = keep_largest_component(out, threshold=options.alpha_threshold)

    if options.edge_clean != EdgeClean.none:
        out = clean_alpha_edges(out, options.edge_clean)

    if options.remove_halo:
        out = remove_edge_halo(out)

    if options.hard_alpha:
        out = hard_alpha(out, options.alpha_threshold)

    return clear_rgb_where_alpha_zero(out)
