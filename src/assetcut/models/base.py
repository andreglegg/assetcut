from __future__ import annotations

from typing import Protocol

from PIL import Image


class BackgroundBackend(Protocol):
    name: str

    def remove(self, image: Image.Image, model_name: str | None = None) -> Image.Image:
        """Return an RGBA image with foreground alpha."""
        ...
