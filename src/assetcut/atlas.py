from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from assetcut.image_io import ensure_rgba, iter_image_files, load_image


@dataclass(frozen=True)
class AtlasEntry:
    source: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class AtlasResult:
    image: Image.Image
    entries: list[AtlasEntry]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "width": self.image.size[0],
            "height": self.image.size[1],
            "frames": [asdict(entry) for entry in self.entries],
        }


def build_atlas(folder: Path, max_size: int = 4096, padding: int = 8) -> AtlasResult:
    files = iter_image_files(folder, recursive=False)
    images: list[tuple[Path, Image.Image]] = [
        (path, ensure_rgba(load_image(path))) for path in files
    ]

    x = padding
    y = padding
    row_height = 0
    atlas_width = max_size
    entries: list[AtlasEntry] = []

    placements: list[tuple[Path, Image.Image, int, int]] = []
    for path, image in images:
        width, height = image.size
        if width + padding * 2 > max_size or height + padding * 2 > max_size:
            raise ValueError(f"Image too large for atlas {max_size}: {path}")

        if x + width + padding > max_size:
            x = padding
            y += row_height + padding
            row_height = 0

        if y + height + padding > max_size:
            raise ValueError(f"Atlas would exceed max size {max_size}")

        placements.append((path, image, x, y))
        entries.append(AtlasEntry(source=path.name, x=x, y=y, width=width, height=height))
        x += width + padding
        row_height = max(row_height, height)

    required_height = max(padding * 2, y + row_height + padding)
    atlas = Image.new("RGBA", (atlas_width, required_height), (0, 0, 0, 0))

    for _path, image, px, py in placements:
        atlas.alpha_composite(image, (px, py))

    return AtlasResult(image=atlas, entries=entries)
