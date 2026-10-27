# comfy_mcp

An MCP server that lets an AI agent (Claude Code, Cline, or any MCP client) generate images on a remote ComfyUI machine and save them into the local workspace.

The model is a swappable workflow file. Drop an exported ComfyUI API workflow into `workflows/` and the agent can use it by name. No code change needed.

## Tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `list_workflows` | none | Names of the workflow files in `workflows/` |
| `generate_image` | `prompt`, `output_dir` (absolute path), `workflow` (default `sdxl`), `negative_prompt` (default `text, watermark`) | Absolute paths of the saved images |

Each call gets a fresh random seed, so ComfyUI does not return a cached image. Jobs time out after 280 s.

## Requirements

* Python 3.10 or newer (the `mcp` package does not support 3.9, which macOS ships).
* A reachable ComfyUI server with the models your workflows name. The bundled `sdxl.json` needs `sd_xl_base_1.0.safetensors` and `sd_xl_refiner_1.0.safetensors`.

## Setup

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Register it with Claude Code (user scope, so every project sees it):

```sh
claude mcp add comfyui -s user -e COMFY_HOST=http://<gpu-host>:8188 \
  -- <path-to-repo>/.venv/bin/python <path-to-repo>/server.py
```

Or in Cline's MCP settings:

```json
"comfyui": {
  "command": "<path-to-repo>/.venv/bin/python",
  "args": ["<path-to-repo>/server.py"],
  "env": { "COMFY_HOST": "http://<gpu-host>:8188" },
  "timeout": 300
}
```

`COMFY_HOST` defaults to `http://localhost:8188`.

## Adding a workflow

1. Build the graph in ComfyUI and export it with Workflow > Export (API).
2. Set the positive prompt node's `text` to `%PROMPT%` and the negative prompt node's `text` to `%NEGATIVE%`.
3. Save it as `workflows/<name>.json`. `list_workflows` picks it up on the next call.

## Security

ComfyUI has no authentication. Do not bind it to `0.0.0.0` on an untrusted network. The setup this was built for binds ComfyUI to the GPU machine's Tailscale IP, with a firewall rule limited to `100.64.0.0/10`, so only tailnet devices can reach it.

## Design notes

`comfy_mcp_guide/README.md` covers why each design choice was made: ComfyUI over A1111 or raw `diffusers`, placeholder substitution over node IDs, the mcp 2.x `FastMCP` to `MCPServer` rename, and the seed randomization.

## License

MIT
