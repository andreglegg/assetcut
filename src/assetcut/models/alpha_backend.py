from __future__ import annotations

from PIL import Image

from assetcut.image_io import ensure_rgba


class AlphaBackend:
    name = "alpha"

    def remove(self, image: Image.Image, model_name: str | None = None) -> Image.Image:
        if model_name is not None:
            raise RuntimeError("The alpha backend does not use model names.")
        return ensure_rgba(image)
