from __future__ import annotations

from assetcut.models.alpha_backend import AlphaBackend
from assetcut.models.base import BackgroundBackend
from assetcut.models.checkerboard_backend import CheckerboardBackend
from assetcut.models.placeholder_backends import birefnet_backend, inspyrenet_backend
from assetcut.models.rembg_backend import RembgBackend


def get_backend(name: str) -> BackgroundBackend:
    normalized = name.strip().lower()
    if normalized == "alpha":
        return AlphaBackend()
    if normalized == "checkerboard":
        return CheckerboardBackend()
    if normalized == "rembg":
        return RembgBackend()
    if normalized == "inspyrenet":
        return inspyrenet_backend()
    if normalized == "birefnet":
        return birefnet_backend()
    raise ValueError(f"Unknown backend: {name}")
