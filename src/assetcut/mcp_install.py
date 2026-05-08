from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

SERVER_NAME = "assetcut"
SERVER_SCRIPT = "assetcut-mcp"

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class InstallResult:
    target: str
    ok: bool
    message: str
    config_path: Path | None = None
    command: str | None = None


@dataclass(frozen=True)
class McpStatus:
    target: str
    ok: bool
    message: str


def default_server_command() -> str:
    argv_path = Path(sys.argv[0]).expanduser()
    sibling = argv_path.with_name(SERVER_SCRIPT)
    if argv_path.name == "assetcut" and sibling.exists():
        return str(sibling.resolve())

    discovered = shutil.which(SERVER_SCRIPT)
    if discovered:
        return str(Path(discovered).resolve())

    return SERVER_SCRIPT


def default_claude_desktop_config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if sys.platform == "win32":
        base = Path.home() / "AppData/Roaming/Claude"
        return base / "claude_desktop_config.json"
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def default_codex_config_path() -> Path:
    return Path.home() / ".codex/config.toml"


def install_claude_desktop(
    server_command: str,
    config_path: Path | None = None,
    *,
    backup: bool = True,
) -> InstallResult:
    path = config_path or default_claude_desktop_config_path()
    payload = _read_json_config(path)
    servers = payload.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"mcpServers must be a JSON object in {path}")

    servers[SERVER_NAME] = {"command": server_command}
    _write_text(path, json.dumps(payload, indent=2) + "\n", backup=backup)
    return InstallResult(
        target="claude-desktop",
        ok=True,
        message="Claude Desktop config updated.",
        config_path=path,
        command=server_command,
    )


def install_codex(
    server_command: str,
    config_path: Path | None = None,
    *,
    backup: bool = True,
) -> InstallResult:
    path = config_path or default_codex_config_path()
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = upsert_codex_mcp_server(text, server_command)
    tomllib.loads(updated)
    _write_text(path, updated, backup=backup)
    return InstallResult(
        target="codex",
        ok=True,
        message="Codex config updated.",
        config_path=path,
        command=server_command,
    )


def install_claude_code(
    server_command: str,
    *,
    scope: str = "user",
    claude_command: str | None = None,
    runner: CommandRunner | None = None,
) -> InstallResult:
    command = claude_command or shutil.which("claude")
    if command is None:
        raise FileNotFoundError("Claude Code CLI was not found on PATH.")
    if scope not in {"local", "user", "project"}:
        raise ValueError("Claude Code scope must be local, user, or project.")

    run = runner or _run_command
    existing = run([command, "mcp", "get", SERVER_NAME])
    existing_output = existing.stdout + existing.stderr
    if existing.returncode == 0 and server_command in existing_output:
        return InstallResult(
            target="claude-code",
            ok=True,
            message=f"Claude Code already has AssetCut at {scope} scope.",
            command=server_command,
        )
    if existing.returncode == 0:
        removed = run([command, "mcp", "remove", SERVER_NAME, "-s", scope])
        if removed.returncode != 0:
            detail = (removed.stderr or removed.stdout).strip()
            raise RuntimeError(detail or "Claude Code MCP update failed.")

    args = [command, "mcp", "add", "-s", scope, SERVER_NAME, "--", server_command]
    completed = run(args)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(detail or "Claude Code MCP install failed.")

    return InstallResult(
        target="claude-code",
        ok=True,
        message=f"Claude Code config updated at {scope} scope.",
        command=server_command,
    )


def upsert_codex_mcp_server(text: str, server_command: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    target_header = f"[mcp_servers.{SERVER_NAME}]"
    replacement = [target_header, f'command = "{_toml_string(server_command)}"']
    inserted = False
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.strip() == target_header:
            output.extend(replacement)
            inserted = True
            index += 1
            while index < len(lines) and not _is_toml_header(lines[index]):
                index += 1
            continue
        output.append(line)
        index += 1

    if not inserted:
        if output and output[-1] != "":
            output.append("")
        output.extend(replacement)

    return "\n".join(output).rstrip() + "\n"


def check_server(server_command: str) -> McpStatus:
    try:
        completed = subprocess.run(
            [server_command, "--tools"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return McpStatus("assetcut-mcp", False, str(exc))

    if completed.returncode != 0:
        return McpStatus("assetcut-mcp", False, (completed.stderr or completed.stdout).strip())
    if "assetcut_cut_image" not in completed.stdout:
        return McpStatus("assetcut-mcp", False, "Server did not list AssetCut tools.")
    return McpStatus("assetcut-mcp", True, "Server executable responds.")


def check_claude_desktop(
    server_command: str | None = None,
    config_path: Path | None = None,
) -> McpStatus:
    path = config_path or default_claude_desktop_config_path()
    if not path.exists():
        return McpStatus("claude-desktop", False, f"Config not found: {path}")
    try:
        payload = _read_json_config(path)
        command = _json_server_command(payload)
    except Exception as exc:
        return McpStatus("claude-desktop", False, str(exc))
    return _status_for_command("claude-desktop", command, server_command)


def check_codex(server_command: str | None = None, config_path: Path | None = None) -> McpStatus:
    path = config_path or default_codex_config_path()
    if not path.exists():
        return McpStatus("codex", False, f"Config not found: {path}")
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        servers = payload.get("mcp_servers")
        if not isinstance(servers, dict):
            command = None
        else:
            server = servers.get(SERVER_NAME)
            command = server.get("command") if isinstance(server, dict) else None
    except Exception as exc:
        return McpStatus("codex", False, str(exc))
    return _status_for_command("codex", command, server_command)


def check_claude_code(server_command: str | None = None) -> McpStatus:
    command = shutil.which("claude")
    if command is None:
        return McpStatus("claude-code", False, "Claude Code CLI was not found on PATH.")
    completed = subprocess.run(
        [command, "mcp", "get", SERVER_NAME],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        return McpStatus("claude-code", False, output.strip() or "Not configured.")
    if server_command and server_command not in output:
        return McpStatus("claude-code", False, "Configured command differs from current server.")
    if "Connected" not in output:
        return McpStatus("claude-code", False, output.strip())
    return McpStatus("claude-code", True, "Claude Code reports AssetCut connected.")


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def _read_json_config(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a JSON object: {path}")
    return cast(dict[str, Any], payload)


def _write_text(path: Path, text: str, *, backup: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".assetcut-bak"))
    path.write_text(text, encoding="utf-8")


def _json_server_command(payload: dict[str, Any]) -> str | None:
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict):
        return None
    server = servers.get(SERVER_NAME)
    if not isinstance(server, dict):
        return None
    command = server.get("command")
    return command if isinstance(command, str) else None


def _status_for_command(
    target: str,
    configured_command: object,
    expected_command: str | None,
) -> McpStatus:
    if not isinstance(configured_command, str):
        return McpStatus(target, False, "AssetCut is not configured.")
    if expected_command and configured_command != expected_command:
        return McpStatus(target, False, f"Configured command differs: {configured_command}")
    return McpStatus(target, True, f"Configured: {configured_command}")


def _toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _is_toml_header(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")
