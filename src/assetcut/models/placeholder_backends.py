from __future__ import annotations

from PIL import Image


class MissingOptionalBackend:
    def __init__(self, name: str, install_hint: str) -> None:
        self.name = name
        self.install_hint = install_hint

    def remove(self, image: Image.Image, model_name: str | None = None) -> Image.Image:
        raise RuntimeError(
            f"The {self.name} backend is not implemented or not installed. {self.install_hint}"
        )


def inspyrenet_backend() -> MissingOptionalBackend:
    return MissingOptionalBackend(
        name="inspyrenet",
        install_hint=(
            "Install optional dependency and implement adapter: "
            "pip install -e '.[inspyrenet]'"
        ),
    )


def birefnet_backend() -> MissingOptionalBackend:
    return MissingOptionalBackend(
        name="birefnet",
        install_hint="Add BiRefNet weights and implement the backend adapter in a later milestone.",
    )
