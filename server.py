"""MCP server: generate images on the Tailscale GPU tower via ComfyUI."""
import json, os, pathlib, random, time, urllib.parse, urllib.request, uuid

from mcp.server.mcpserver import MCPServer

HOST = os.environ.get("COMFY_HOST", "http://localhost:8188")
WORKFLOWS = pathlib.Path(__file__).parent / "workflows"
mcp = MCPServer("comfyui")


def call(path, data=None):
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(HOST + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


@mcp.tool()
def list_workflows() -> list[str]:
    """Names of the available ComfyUI workflows (models/styles)."""
    return sorted(p.stem for p in WORKFLOWS.glob("*.json"))


@mcp.tool()
def generate_image(
    prompt: str,
    output_dir: str,
    workflow: str = "sdxl",
    negative_prompt: str = "text, watermark",
) -> list[str]:
    """Generate an image on the GPU tower and save it locally.

    output_dir must be an absolute path (e.g. <workspace>/assets/generated).
    negative_prompt lists things to keep out of the image (e.g. "person, people").
    Writing "no X" in prompt does not work: diffusion models read it as "X".
    Returns the absolute paths of the saved files.
    """
    raw = (WORKFLOWS / f"{workflow}.json").read_text()
    raw = raw.replace("%PROMPT%", json.dumps(prompt)[1:-1])
    wf = json.loads(raw.replace("%NEGATIVE%", json.dumps(negative_prompt)[1:-1]))
    # Fresh seed each run, otherwise ComfyUI returns the cached result
    for node in wf.values():
        for key in ("seed", "noise_seed"):
            if key in node.get("inputs", {}):
                node["inputs"][key] = random.randint(0, 2**32 - 1)

    body = json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode()
    pid = json.loads(call("/prompt", body))["prompt_id"]

    deadline = time.time() + 280
    while pid not in (hist := json.loads(call(f"/history/{pid}"))):
        if time.time() > deadline:
            raise TimeoutError(f"ComfyUI job {pid} still running; check {HOST}")
        time.sleep(1)

    out = pathlib.Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for node in hist[pid]["outputs"].values():
        for img in node.get("images", []):
            q = urllib.parse.urlencode({k: img[k] for k in ("filename", "subfolder", "type")})
            path = out / img["filename"]
            path.write_bytes(call(f"/view?{q}"))
            saved.append(str(path))
    return saved


if __name__ == "__main__":
    mcp.run()
