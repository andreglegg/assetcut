from __future__ import annotations

from pathlib import Path

from PIL import Image

from assetcut.atlas import build_atlas


def test_build_atlas(tmp_path: Path) -> None:
    for index in range(3):
        image = Image.new("RGBA", (16, 16), (index * 20, 0, 0, 255))
        image.save(tmp_path / f"asset_{index}.png")

    result = build_atlas(tmp_path, max_size=128, padding=4)

    assert result.image.mode == "RGBA"
    assert len(result.entries) == 3
    assert result.entries[0].source == "asset_0.png"
