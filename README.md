# AssetCut CLI

AssetCut is a local CLI for removing backgrounds from game assets and exporting real PNG alpha. It uses a practical backend architecture so local background removal, transparent PNG validation, post-processing, batch workflows, and integrations can evolve without rewriting the command surface.

## Goal

Build a production-grade local tool for stylized game assets:

- Remove backgrounds from single images and folders.
- Export real transparent PNGs with RGBA alpha.
- Detect fake transparency, including baked checkerboard backgrounds.
- Clean white, gray, or color halos from asset edges.
- Trim, pad, and center assets for Godot or 3D reference workflows.
- Batch process folders.
- Generate validation reports.
- Prepare atlas output for game engines.

## Local setup

Recommended Python version: 3.11 or 3.12.

```bash
cd assetcut
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,rembg]"
```

For Mac without Python 3.11:

```bash
brew install python@3.11
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,rembg]"
```

## First commands

```bash
assetcut doctor
assetcut cut ./input.png
assetcut cut ./input.png --preview
assetcut cut ./input.png --json
assetcut cut ./raw-assets --out ./cutouts
assetcut preview ./input.png --cutout ./input-cutout.png
assetcut preview ./cutouts
```

Advanced commands are still available when you want explicit control:

```bash
assetcut remove ./input.png --out ./output.png --trim --pad 32 --edge-clean medium --validate
assetcut batch ./raw-assets --out ./cutouts --trim --pad 32 --edge-clean strong --validate
assetcut validate ./cutouts
assetcut atlas ./cutouts --out ./atlas.png --json ./atlas.json --padding 8
```

## Verified Local Commands

These commands use the project venv and do not require model downloads during tests:

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev,rembg]"
.venv/bin/assetcut --help
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

For a real local cutout, start with:

```bash
.venv/bin/assetcut cut ./input.png
```

`assetcut cut` automatically detects baked checkerboard backgrounds, already-transparent PNGs,
and normal backgrounds. It writes `input-cutout.png` and `input-cutout-report.json` by default.

Use quality presets when needed:

```bash
.venv/bin/assetcut cut ./input.png --quality crisp
.venv/bin/assetcut cut ./input.png --quality soft
.venv/bin/assetcut cut ./input.png --quality pixel
```

Use `--preview` to create a QA preview as part of the cut, `--open` to reveal
the result in Finder on macOS, and `--json` when automation needs structured
output:

```bash
.venv/bin/assetcut cut ./input.png --preview --open
.venv/bin/assetcut cut ./input.png --json
```

Example JSON payload:

```json
{
  "ok": true,
  "input": "input.png",
  "output": "input-cutout.png",
  "report": "input-cutout-report.json",
  "preview": null,
  "backend": "checkerboard",
  "reason": "Detected baked checkerboard background."
}
```

Dry-run plans the backend and paths without writing files:

```bash
.venv/bin/assetcut cut ./input.png --dry-run --json
```

## Python Automation API

Scripts and integrations should call the stable API facade instead of CLI internals:

```python
from assetcut import api

result = api.cut_image("input.png", preview=True)
batch = api.cut_folder("raw-assets", output_folder="cutouts", max_files=500)
report = api.validate("input-cutout.png")
preview = api.preview("input.png", cutout_path="input-cutout.png")
doctor = api.doctor()
```

API functions return JSON-serializable dictionaries. Success responses use the
same schema as `assetcut cut --json`; failures use structured errors:

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

Path rules:

- Relative and absolute local paths are allowed.
- Pass `base_dir` to restrict all paths to a project folder.
- Output parents are created by the writer.
- Existing outputs are preserved unless `overwrite=True`.
- Batch API calls default to `max_files=500`.

## MCP Server

AssetCut ships an optional MCP stdio server for local MCP clients. Install the MCP extra:

```bash
.venv/bin/python -m pip install -e ".[mcp,rembg]"
```

Run the server command from an MCP client:

```bash
/Users/andreglegg/Apps/assetcut/.venv/bin/assetcut-mcp
```

Tools exposed:

- `assetcut_cut_image`
- `assetcut_cut_folder`
- `assetcut_validate`
- `assetcut_preview`
- `assetcut_doctor`

Example client configuration shape:

```json
{
  "mcpServers": {
    "assetcut": {
      "command": "/Users/andreglegg/Apps/assetcut/.venv/bin/assetcut-mcp"
    }
  }
}
```

The MCP tools return the same JSON-serializable result dictionaries as
`assetcut.api`, including structured errors and dry-run payloads.

For game assets with a baked checkerboard background, use the built-in deterministic
checkerboard backend for a crisper result:

```bash
.venv/bin/assetcut remove ./input.png --backend checkerboard --out ./output.png --trim --pad 32 --edge-clean none --validate
```

Create quick QA previews on light, dark, and colored mattes:

```bash
.venv/bin/assetcut preview ./input.png --cutout ./input-cutout.png
.venv/bin/assetcut preview ./cutouts
```

The first real `rembg` run may download model weights into the normal local model cache.

## Project layout

```text
assetcut/
  pyproject.toml
  src/assetcut/
    cli.py
    engine.py
    alpha.py
    image_io.py
    postprocess.py
    validate.py
    atlas.py
    models/
      base.py
      rembg_backend.py
      placeholder_backends.py
  tests/
```

## Important rules

- Never fake transparency with checkerboards.
- Never export RGB images for cutouts. Always export PNG RGBA.
- Always preserve the alpha channel.
- Always validate output files when `--validate` is passed.
- Default behavior should be safe for game assets, not generic portrait photos.
- Avoid destructive edge cleanup unless `--edge-clean strong` or `--hard-alpha` is explicitly requested.

## Game Asset Processing Notes

Use `--trim --pad 32` for most props so the saved PNG keeps stable transparent
space around the object. Use `--remove-halo` when generated assets contain a
white or gray matte around semi-transparent pixels. Use `--hard-alpha` only for
pixel art or masks where anti-aliased edges are unwanted.

## References

- rembg: https://github.com/danielgatis/rembg
- InSPyReNet: https://github.com/plemeri/InSPyReNet
- transparent-background: https://github.com/plemeri/transparent-background
- BiRefNet: https://github.com/ZhengPeng7/BiRefNet
- BRIA RMBG-2.0 licensing note: https://huggingface.co/briaai/RMBG-2.0
