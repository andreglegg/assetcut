from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EdgeClean(StrEnum):
    none = "none"
    light = "light"
    medium = "medium"
    strong = "strong"


class AssetMode(StrEnum):
    sprite = "sprite"
    prop = "prop"
    ui = "ui"
    meshy = "meshy"
    pixel = "pixel"


class QualityPreset(StrEnum):
    crisp = "crisp"
    soft = "soft"
    pixel = "pixel"


@dataclass(frozen=True)
class ProcessingOptions:
    mode: AssetMode = AssetMode.prop
    edge_clean: EdgeClean = EdgeClean.medium
    trim: bool = False
    pad: int = 0
    remove_halo: bool = False
    hard_alpha: bool = False
    keep_largest: bool = False
    alpha_threshold: int = 8


def options_for_mode(mode: AssetMode) -> ProcessingOptions:
    if mode == AssetMode.sprite:
        return ProcessingOptions(mode=mode, edge_clean=EdgeClean.medium, trim=True, pad=16)
    if mode == AssetMode.prop:
        return ProcessingOptions(
            mode=mode,
            edge_clean=EdgeClean.medium,
            trim=True,
            pad=32,
            remove_halo=True,
        )
    if mode == AssetMode.ui:
        return ProcessingOptions(mode=mode, edge_clean=EdgeClean.light, trim=True, pad=24)
    if mode == AssetMode.meshy:
        return ProcessingOptions(
            mode=mode,
            edge_clean=EdgeClean.light,
            trim=True,
            pad=64,
            remove_halo=True,
        )
    if mode == AssetMode.pixel:
        return ProcessingOptions(
            mode=mode,
            edge_clean=EdgeClean.none,
            trim=True,
            pad=8,
            hard_alpha=True,
            alpha_threshold=127,
        )
    return ProcessingOptions(mode=mode)


def options_for_quality(quality: QualityPreset) -> ProcessingOptions:
    if quality == QualityPreset.crisp:
        return ProcessingOptions(
            mode=AssetMode.prop,
            edge_clean=EdgeClean.none,
            trim=True,
            pad=32,
            remove_halo=True,
            alpha_threshold=8,
        )
    if quality == QualityPreset.soft:
        return ProcessingOptions(
            mode=AssetMode.prop,
            edge_clean=EdgeClean.medium,
            trim=True,
            pad=32,
            remove_halo=True,
            alpha_threshold=8,
        )
    if quality == QualityPreset.pixel:
        return ProcessingOptions(
            mode=AssetMode.pixel,
            edge_clean=EdgeClean.none,
            trim=True,
            pad=8,
            hard_alpha=True,
            alpha_threshold=127,
        )
    return options_for_quality(QualityPreset.crisp)
