# comfy_mcp guide

## 2026-10-27 - Initial build: ComfyUI on a Tailscale GPU tower, exposed to Cline over MCP

### The "Why" (Design Decisions)

* **ComfyUI as the backend.** It runs every major open-weight image model (SDXL, Flux, Chroma, Qwen-Image) behind one HTTP API, so the model is a swappable file, not a code change. Alternatives: Forge/A1111 (weaker API), raw `diffusers` scripts (one script per model architecture).
* **Portable build, not Desktop.** The tower is a headless GPU server reached over Tailscale. Desktop needs a logged-in GUI session. Portable takes `--listen` and can start at login.
* **Bind to the machine's Tailscale IP (100.x.y.z), not 0.0.0.0.** ComfyUI has no auth. Binding to the tailnet address plus a firewall rule scoped to `100.64.0.0/10` keeps it off the LAN.
* **MCP server instead of a per-project script.** Registered once in Cline, it is available in every workspace. `output_dir` is a tool argument, so each project chooses where images land.
* **Placeholder substitution (`%PROMPT%`) instead of node IDs.** Exported API workflows use numeric node IDs that change between workflows. A text placeholder makes every workflow file drop-in with no per-file config.
* **Python 3.12 from Homebrew.** macOS ships 3.9.6. The `mcp` package requires 3.10 or newer, so pip reported "no matching distribution".

### Core Concepts

* **ComfyUI API format.** A workflow exported via Workflow > Export (API) is a flat dict: `{node_id: {"class_type": ..., "inputs": {...}}}`. POST it to `/prompt` to queue it.
* **Execution caching.** ComfyUI skips nodes whose inputs did not change. Same prompt + same seed returns the old image instantly, so the server randomizes `seed` / `noise_seed` every call.
* **Job lifecycle.** `/prompt` returns a `prompt_id`. `/history/{id}` is empty until the job finishes, then lists output images. `/view?filename=&subfolder=&type=` streams each file, which is how images reach the Mac with no file sync.
* **MCP stdio transport.** Cline launches `server.py` as a subprocess and speaks JSON-RPC over stdin/stdout. `MCPServer` turns type-hinted functions into tools; the docstring becomes the tool description the agent reads.
* **mcp 2.x rename.** The SDK installed is `mcp` 2.3.0, where `FastMCP` (`mcp.server.fastmcp`) became `MCPServer` (`mcp.server.mcpserver`). Most tutorials still show the 1.x import, which fails with `ModuleNotFoundError` on 2.x.

### Implementation Breakdown

* `server.py: call()` is a stdlib HTTP helper. No `requests` dependency keeps the venv to `mcp` alone.
* `generate_image()`:
  1. Loads `workflows/<name>.json` as text and substitutes `%PROMPT%`. `json.dumps(prompt)[1:-1]` escapes quotes and newlines so the result is still valid JSON.
  2. Randomizes seeds, queues the job, polls history once per second up to 280 s. Cline's per-server `timeout` is set to 300 s so the server errors first with a useful message.
  3. Downloads each output image into `output_dir` and returns the local paths.
* `list_workflows()` lets the agent discover available models by filename, so adding `chroma.json` needs no code change.

### Config

**Primary agent: Claude Code, user scope.** Registered with `claude mcp add comfyui -s user ...`, stored in `~/.claude.json` (outside any git repo). Chosen over a shared `.agents/mcp.json` because a repo-tracked MCP file risks committing keys from other servers' `env` blocks. The local `qwen2.5-coder:14b` in Cline was dropped as the agent: it ignored Cline's tool-call format, and on a 12 GB 3080 Ti it competes with ComfyUI for VRAM.

Cline MCP settings entry (kept, works if Cline is pointed at a stronger model):

```json
"comfyui": {
  "command": "<path-to-repo>/.venv/bin/python",
  "args": ["<path-to-repo>/server.py"],
  "env": { "COMFY_HOST": "http://<gpu-host>:8188" },
  "timeout": 300
}
```

## 2026-10-27 - Negative prompt + public release

### The "Why" (Design Decisions)

* **`negative_prompt` as a tool argument.** The first apple-and-dragon run asked for "no figures" in the positive prompt. 2 of 4 images still had a person. CLIP encodes tokens, not logic, so "no person" pushes the image toward "person". The only reliable lever is the negative conditioning, which was hardcoded to `text, watermark`. After moving the people terms into the negative prompt, 0 of 7 images had a person.
* **Default stays `text, watermark`.** Existing callers get the same output as before.
* **`%NEGATIVE%` placeholder, same as `%PROMPT%`.** Keeps the "any exported workflow is drop-in" rule. A workflow without `%NEGATIVE%` still works; the argument is ignored.
* **`COMFY_HOST` default changed to `localhost:8188`.** The old default was the tower's tailnet hostname. Publishing it gains nothing. The local registration sets `COMFY_HOST` through env, so it is unaffected.
* **Public repo, MIT.** Small, self-contained, and the design notes are the part worth referencing.

### Core Concepts

* **Classifier-free guidance.** Each step, the sampler predicts noise twice: once with the positive conditioning and once with the negative. It moves along `negative + cfg * (positive - negative)`. The negative prompt is what the image is pushed away from. With `cfg = 8` the push is strong.
* **Composition limits of SDXL.** Asking for both a foreground apple and a "tiny distant dragon" failed in a consistent way: a small dragon was dropped (4 images), a visible dragon was placed next to the apple (4 images). Text weights like `(dragon:1.3)` change presence, not placement. Reliable placement needs inpainting or regional conditioning, not prompt wording.

### Implementation Breakdown

* `generate_image()` substitutes `%PROMPT%` and then `%NEGATIVE%` in the raw JSON text, both escaped with `json.dumps(x)[1:-1]`, before `json.loads`.
* `workflows/sdxl.json`: nodes 7 (base) and 16 (refiner) now read `%NEGATIVE%`. Both samplers need it, or the refiner's last 5 steps would drift back toward the excluded content.
