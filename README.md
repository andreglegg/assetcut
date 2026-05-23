# AssetCut

AssetCut is a local Python CLI for removing image backgrounds from game assets and exporting real transparent PNGs.

It is built for sprites, props, UI elements, icons, and generated assets that often contain baked checkerboard backgrounds or fake transparency.

## Features

- Remove backgrounds from one image or a folder.
- Detect baked checkerboard transparency and cut it cleanly.
- Detect and cut solid chroma-key backgrounds (magenta, green screen, etc.).
- Slice sprite and tile sheets into individual transparent tile PNGs.
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
assetcut remove input.png --backend chroma --out output.png --trim --pad 32 --validate
assetcut remove input.png --backend rembg --out output.png --trim --pad 32 --validate
```

Check local dependencies:

```bash
assetcut doctor
```

## Chroma-Key Backgrounds

Many generated tile and sprite sheets ship on a flat key color such as magenta or
green. The `chroma` backend keys on color, so it removes the background everywhere
it appears, including enclosed regions like the hollow centers of frame tiles.

`assetcut cut` auto-detects vivid keys, so usually you just run:

```bash
assetcut cut sheet.png
```

Force a specific key color or widen the match when needed:

```bash
assetcut remove sheet.png --backend chroma --out sheet-cutout.png
```

## Slice Sprite and Tile Sheets

Cut a sheet into individual transparent tile PNGs plus a `manifest.json` of frame
coordinates. The background is removed first (auto chroma-key by default).

Auto mode detects each tile by the transparent gaps between them — best for mixed
or irregular layouts:

```bash
assetcut slice sheet.png --out tiles --pad 2
```

Grid mode cuts fixed cells — best for evenly spaced sheets:

```bash
assetcut slice sheet.png --out tiles --mode grid --tile 96x96 --spacing 2 --margin 0
```

Useful options:

- `--key-color ff00ff`: force the chroma key color.
- `--tolerance 60`: color match distance for the key.
- `--backend auto|chroma|alpha|none`: how to obtain transparency before slicing.
- `--keep-empty`: keep blank grid cells (grid mode).
- `--trim` / `--no-trim`: trim each tile to its content. Default is on for auto
  mode and off for grid mode, so grid cells stay uniform.
- `--pad N`: transparent padding added around each tile.
- `--min-area N`: drop specks smaller than N pixels (auto mode).

Each tile is written as `<sheet>_000.png`, `<sheet>_001.png`, and so on. The
`manifest.json` records each frame's `x`, `y`, `width`, and `height` as the source
rectangle in the original sheet (independent of trim and pad), ready for engine
import.

## Python API

```python
from assetcut import api

result = api.cut_image("input.png", preview=True)
batch = api.cut_folder("raw-assets", output_folder="cutouts")
tiles = api.slice_sheet("sheet.png", output_folder="tiles", mode="auto")
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
- `assetcut_slice`
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

## License

AssetCut is released under the [MIT License](LICENSE).

## Credits

Developed by Andre Glegg with AI coding assistance.
