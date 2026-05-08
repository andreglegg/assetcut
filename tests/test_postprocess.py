from __future__ import annotations

import numpy as np
from PIL import Image

from assetcut.config import EdgeClean
from assetcut.postprocess import clean_alpha_edges, keep_largest_component, remove_edge_halo


def test_edge_clean_modifies_existing_alpha_without_expanding_shape() -> None:
    image = Image.new("RGBA", (7, 7), (0, 0, 0, 0))
    for y in range(2, 5):
        for x in range(2, 5):
            image.putpixel((x, y), (255, 0, 0, 255))

    cleaned = clean_alpha_edges(image, EdgeClean.light)
    alpha = np.asarray(cleaned.getchannel("A"))

    assert alpha[0, 0] == 0
    assert alpha[1, 1] == 0
    assert alpha[2, 2] < 255
    assert alpha[3, 3] == 255


def test_keep_largest_component_removes_small_islands() -> None:
    image = Image.new("RGBA", (8, 4), (0, 0, 0, 0))
    for y in range(3):
        for x in range(3):
            image.putpixel((x, y), (255, 0, 0, 255))
    image.putpixel((7, 3), (0, 255, 0, 255))

    out = keep_largest_component(image)

    assert out.getpixel((1, 1))[3] == 255
    assert out.getpixel((7, 3))[3] == 0


def test_remove_edge_halo_replaces_pale_edge_rgb_from_opaque_pixels() -> None:
    image = Image.new("RGBA", (7, 7), (0, 0, 0, 0))
    for y in range(2, 5):
        for x in range(2, 5):
            image.putpixel((x, y), (245, 245, 245, 128))
    image.putpixel((3, 3), (220, 20, 20, 255))

    out = remove_edge_halo(image)
    red, green, blue, alpha = out.getpixel((2, 3))

    assert alpha == 128
    assert red > green
    assert red > blue
