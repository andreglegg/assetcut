from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("mcp")

from assetcut import mcp_server  # noqa: E402


def _checkerboard_asset(path: Path) -> None:
    image = Image.new("RGB", (64, 64), (255, 255, 255))
    for y in range(64):
        for x in range(64):
            value = 210 if ((x // 8) + (y // 8)) % 2 == 0 else 245
            image.putpixel((x, y), (value, value, value))
    for y in range(20, 44):
        for x in range(20, 44):
            image.putpixel((x, y), (180, 20, 20))
    image.save(path)


def test_mcp_doctor_tool_returns_structured_result() -> None:
    result = mcp_server.assetcut_doctor()

    assert result["ok"] is True
    assert result["checks"]["checkerboard_backend"] is True


def test_mcp_help_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        mcp_server.main(["--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "assetcut-mcp" in output
    assert "--tools" in output
    assert "--client-config" in output


def test_mcp_tools_output_lists_registered_tools(capsys: pytest.CaptureFixture[str]) -> None:
    mcp_server.main(["--tools"])

    output = capsys.readouterr().out
    assert "assetcut_cut_image" in output
    assert "assetcut_cut_folder" in output
    assert "assetcut_validate" in output
    assert "assetcut_preview" in output
    assert "assetcut_doctor" in output


def test_mcp_client_config_is_generic_json() -> None:
    payload = json.loads(mcp_server.render_client_config(command="/tmp/assetcut-mcp"))

    assert payload == {"mcpServers": {"assetcut": {"command": "/tmp/assetcut-mcp"}}}


def test_mcp_cut_image_tool_supports_dry_run(tmp_path: Path) -> None:
    input_path = tmp_path / "asset.png"
    _checkerboard_asset(input_path)

    result = mcp_server.assetcut_cut_image(str(input_path), dry_run=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["backend"] == "checkerboard"
    assert not (tmp_path / "asset-cutout.png").exists()


def test_mcp_validate_tool_returns_error_for_missing_path(tmp_path: Path) -> None:
    result = mcp_server.assetcut_validate(str(tmp_path / "missing.png"))

    assert result["ok"] is False
    assert result["error"]["code"] == "not_found"
