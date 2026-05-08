from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from assetcut.alpha import clear_rgb_where_alpha_zero, looks_like_baked_checkerboard
from assetcut.image_io import ensure_rgba

BoolMask = NDArray[np.bool_]


@dataclass(frozen=True)
class CheckerboardMask:
    background: BoolMask
    ratio: float


def detect_checkerboard_background(
    image: Image.Image,
    min_background_ratio: float = 0.18,
    expand_pixels: int = 1,
) -> CheckerboardMask | None:
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    alpha = arr[:, :, 3]
    height, width = alpha.shape

    if width < 16 or height < 16 or np.any(alpha < 255):
        return None

    if not looks_like_baked_checkerboard(rgba):
        return None

    rgb = arr[:, :, :3].astype(np.int16)
    channel_spread = rgb.max(axis=2) - rgb.min(axis=2)
    brightness = rgb.mean(axis=2)
    pale_neutral = (channel_spread <= 18) & (brightness >= 180)

    pale_ratio = float(np.count_nonzero(pale_neutral)) / float(pale_neutral.size)
    if pale_ratio < min_background_ratio:
        return None

    count, labels = cv2.connectedComponents(pale_neutral.astype(np.uint8), connectivity=8)
    if count <= 1:
        return None

    border_labels = np.concatenate(
        [
            labels[0, :],
            labels[-1, :],
            labels[:, 0],
            labels[:, -1],
        ]
    )
    border_labels = border_labels[border_labels != 0]
    if border_labels.size == 0:
        return None

    background = np.isin(labels, np.unique(border_labels))
    ratio = float(np.count_nonzero(background)) / float(background.size)
    if ratio < min_background_ratio:
        return None

    if expand_pixels > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        expanded = cv2.dilate(
            background.astype(np.uint8),
            kernel,
            iterations=expand_pixels,
        )
        background = expanded.astype(bool)

    return CheckerboardMask(background=background, ratio=ratio)


def remove_checkerboard_background(
    image: Image.Image,
    expand_pixels: int = 1,
) -> Image.Image:
    mask = detect_checkerboard_background(image, expand_pixels=expand_pixels)
    if mask is None:
        raise RuntimeError(
            "No baked checkerboard background was detected. "
            "Use --backend rembg for non-checkerboard backgrounds."
        )

    arr = np.array(ensure_rgba(image), dtype=np.uint8)
    arr[mask.background, :3] = 0
    arr[mask.background, 3] = 0
    arr[~mask.background, 3] = 255
    return clear_rgb_where_alpha_zero(Image.fromarray(arr, mode="RGBA"))
