from __future__ import annotations

from io import BytesIO
from typing import BinaryIO, cast

from PIL import Image

from assetcut.image_io import ensure_rgba


def _coerce_rembg_result(result: object) -> Image.Image:
    if isinstance(result, Image.Image):
        return ensure_rgba(result)

    if isinstance(result, bytes):
        image = Image.open(BytesIO(result))
        image.load()
        return ensure_rgba(image)

    if hasattr(result, "read"):
        image = Image.open(cast(BinaryIO, result))
        image.load()
        return ensure_rgba(image)

    raise RuntimeError(f"rembg returned unsupported output type: {type(result).__name__}")


class RembgBackend:
    name = "rembg"

    def remove(self, image: Image.Image, model_name: str | None = None) -> Image.Image:
        try:
            from rembg import new_session, remove
        except Exception as exc:
            raise RuntimeError(
                "The rembg backend is not installed. Run: pip install -e '.[rembg]'"
            ) from exc

        source = ensure_rgba(image)
        try:
            if model_name:
                session = new_session(model_name)
                result = remove(source, session=session)
            else:
                result = remove(source)
        except Exception as exc:
            raise RuntimeError(f"rembg failed to remove the background: {exc}") from exc

        return _coerce_rembg_result(result)
