from __future__ import annotations

from PIL import Image

from assetcut.checkerboard import remove_checkerboard_background


class CheckerboardBackend:
    name = "checkerboard"

    def remove(self, image: Image.Image, model_name: str | None = None) -> Image.Image:
        if model_name not in {None, "crisp"}:
            raise RuntimeError(
                "The checkerboard backend only supports the optional model name 'crisp'."
            )
        return remove_checkerboard_background(image, expand_pixels=1)
