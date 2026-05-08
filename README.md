# AssetCut

AssetCut is a local Python CLI for removing image backgrounds from game assets and exporting real transparent PNGs.

It is built for sprites, props, UI elements, icons, and generated assets that often contain baked checkerboard backgrounds or fake transparency.

## Features

- Remove backgrounds from one image or a folder.
- Detect baked checkerboard transparency and cut it cleanly.
- Export PNG RGBA with real alpha.
- Validate transparency and catch bad cutouts.
- Trim, pad, hard-threshold, and clean alpha edges.
- Generate preview contact sheets on light and dark backgrounds.
- Expose a Python API and optional MCP server for local automation.

## Install

Use Python 3.11 or 3.12.

```bash
git clone <repo-url>
cd assetcut

python3.12 -m venv .venv

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev,rembg]"

source .venv/bin/activate
```

The first `rembg` run may download model weights into its local cache.

## Quick Start

Show available commands:

```bash
assetcut --help
assetcut cut --help
assetcut validate --help
assetcut preview --help
assetcut doctor --help
```

Cut one image:

```bash
assetcut cut input.png
```

This writes:

```text
input-cutout.png
input-cutout-report.json
```

Create a preview while cutting:

```bash
assetcut cut input.png --preview
```

Print structured JSON:

```bash
assetcut cut input.png --json
```

Plan without writing files:

```bash
assetcut cut input.png --dry-run --json
```

Batch process a folder:

```bash
assetcut cut ./raw-assets --out ./cutouts
```

## Quality Presets

```bash
assetcut cut input.png --quality crisp
assetcut cut input.png --quality soft
assetcut cut input.png --quality pixel
```

`crisp` is the default and is usually best for generated game assets with hard silhouettes.

## Useful Commands

Validate a cutout:

```bash
assetcut validate input-cutout.png
```

Create a preview contact sheet:

```bash
assetcut preview input.png --cutout input-cutout.png
assetcut preview ./cutouts
```

Use an explicit backend:

```bash
assetcut remove input.png --backend checkerboard --out output.png --trim --pad 32 --validate
assetcut remove input.png --backend rembg --out output.png --trim --pad 32 --validate
```

Check local dependencies:

```bash
assetcut doctor
```

## Python API

```python
from assetcut import api

result = api.cut_image("input.png", preview=True)
batch = api.cut_folder("raw-assets", output_folder="cutouts")
report = api.validate("input-cutout.png")
preview = api.preview("input.png", cutout_path="input-cutout.png")
doctor = api.doctor()
```

API functions return JSON-serializable dictionaries. Failures use structured errors:

```json
{
  "ok": false,
  "error": {
    "code": "output_exists",
    "message": "Output already exists: input-cutout.png. Use --overwrite to replace it.",
    "path": "input-cutout.png"
  }
}
```

## MCP Server

Install the optional MCP extra:

```bash
.venv/bin/python -m pip install -e ".[mcp,rembg]"
```

Run the stdio server:

```bash
assetcut-mcp
```

Human-facing MCP help:

```bash
assetcut-mcp --help
assetcut-mcp --tools
assetcut-mcp --client-config
```

Install AssetCut into local MCP clients:

```bash
assetcut mcp install all
assetcut mcp doctor
```

Install one client at a time:

```bash
assetcut mcp install claude-code
assetcut mcp install claude-desktop
assetcut mcp install codex
```

Preview changes without writing config:

```bash
assetcut mcp install all --dry-run
```

MCP clients such as Claude Desktop or Codex start `assetcut-mcp` as a local stdio
server. After launch, the client asks the server for its tool list and receives
the tool names, descriptions, and input schemas automatically.

Claude Desktop MCP client configuration:

```json
{
  "mcpServers": {
    "assetcut": {
      "command": "/absolute/path/to/assetcut/.venv/bin/assetcut-mcp"
    }
  }
}
```

Claude Code CLI configuration:

```bash
claude mcp add -s user assetcut -- /absolute/path/to/assetcut/.venv/bin/assetcut-mcp
claude mcp list
```

Codex-style MCP client configuration:

```toml
[mcp_servers.assetcut]
command = "/absolute/path/to/assetcut/.venv/bin/assetcut-mcp"
```

Exposed tools:

- `assetcut_cut_image`
- `assetcut_cut_folder`
- `assetcut_validate`
- `assetcut_preview`
- `assetcut_doctor`

## Development

```bash
pytest
ruff check .
mypy src
```

## Notes

- AssetCut never creates fake checkerboard transparency.
- Cutouts are saved as PNG RGBA.
- Existing outputs are preserved unless `--overwrite` is passed.
- Everything runs locally; no cloud API is required.

## Credits

Developed by Andre Glegg with AI coding assistance.
