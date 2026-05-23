from __future__ import annotations

from PIL import Image

from assetcut.chroma import parse_hex_color, remove_chroma_key


class ChromaKeyBackend:
    name = "chroma"

    def remove(self, image: Image.Image, model_name: str | None = None) -> Image.Image:
        key_color = None
        if model_name not in {None, "auto"}:
            assert model_name is not None
            key_color = parse_hex_color(model_name)
        return remove_chroma_key(image, key_color=key_color)
