from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from assetcut import mcp_install
from assetcut.cli import app


def test_install_claude_desktop_updates_json_config(tmp_path: Path) -> None:
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"existing": {"command": "other"}}, "preferences": {}}),
        encoding="utf-8",
    )

    result = mcp_install.install_claude_desktop(
        "/tmp/assetcut-mcp",
        config_path=config_path,
        backup=False,
    )

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert result.ok is True
    assert payload["mcpServers"]["existing"]["command"] == "other"
    assert payload["mcpServers"]["assetcut"]["command"] == "/tmp/assetcut-mcp"


def test_install_codex_upserts_toml_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[features]",
                "js_repl = true",
                "",
                "[mcp_servers.other]",
                'command = "other-mcp"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    mcp_install.install_codex("/tmp/assetcut-mcp", config_path=config_path, backup=False)
    mcp_install.install_codex("/tmp/new-assetcut-mcp", config_path=config_path, backup=False)

    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert payload["features"]["js_repl"] is True
    assert payload["mcp_servers"]["other"]["command"] == "other-mcp"
    assert payload["mcp_servers"]["assetcut"]["command"] == "/tmp/new-assetcut-mcp"
    assert config_path.read_text(encoding="utf-8").count("[mcp_servers.assetcut]") == 1


def test_install_claude_code_adds_missing_server() -> None:
    calls: list[list[str]] = []

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[1:4] == ["mcp", "get", "assetcut"]:
            return subprocess.CompletedProcess(args, 1, "", "not found")
        return subprocess.CompletedProcess(args, 0, "added", "")

    result = mcp_install.install_claude_code(
        "/tmp/assetcut-mcp",
        claude_command="/tmp/claude",
        runner=runner,
    )

    assert result.ok is True
    assert calls == [
        ["/tmp/claude", "mcp", "get", "assetcut"],
        ["/tmp/claude", "mcp", "add", "-s", "user", "assetcut", "--", "/tmp/assetcut-mcp"],
    ]


def test_install_claude_code_is_idempotent_when_command_matches() -> None:
    calls: list[list[str]] = []

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(
            args,
            0,
            "Command: /tmp/assetcut-mcp\nStatus: connected",
            "",
        )

    result = mcp_install.install_claude_code(
        "/tmp/assetcut-mcp",
        claude_command="/tmp/claude",
        runner=runner,
    )

    assert result.ok is True
    assert calls == [["/tmp/claude", "mcp", "get", "assetcut"]]


def test_mcp_install_cli_writes_client_configs(tmp_path: Path) -> None:
    claude_config = tmp_path / "claude.json"
    codex_config = tmp_path / "codex.toml"
    server = str((tmp_path / "assetcut-mcp").resolve())

    desktop_result = CliRunner().invoke(
        app,
        [
            "mcp",
            "install",
            "claude-desktop",
            "--server",
            server,
            "--claude-desktop-config",
            str(claude_config),
        ],
    )
    codex_result = CliRunner().invoke(
        app,
        [
            "mcp",
            "install",
            "codex",
            "--server",
            server,
            "--codex-config",
            str(codex_config),
        ],
    )

    assert desktop_result.exit_code == 0, desktop_result.output
    assert codex_result.exit_code == 0, codex_result.output
    assert json.loads(claude_config.read_text(encoding="utf-8"))["mcpServers"]["assetcut"] == {
        "command": server
    }
    assert tomllib.loads(codex_config.read_text(encoding="utf-8"))["mcp_servers"]["assetcut"] == {
        "command": server
    }


def test_mcp_install_cli_dry_run_does_not_write(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    result = CliRunner().invoke(
        app,
        [
            "mcp",
            "install",
            "codex",
            "--server",
            "/tmp/assetcut-mcp",
            "--codex-config",
            str(config_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Would configure: codex" in result.output
    assert not config_path.exists()
