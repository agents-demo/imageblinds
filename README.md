# ImageBlinds

A small JS GUI: pick a `.jpg` photo, send it to an
[openjiuwen agent-core](https://github.com/openJiuwen-ai/agent-core) vision agent, and show
the model's textual description of the image. Modeled after
[taketwo](https://github.com/agents-demo/taketwo) (multimodal `DeepAgent` reading images via
`read_file` with `enable_read_image_multimodal=True`).

## Setup

```bash
uv sync                      # installs deps incl. openjiuwen from git
cp .env.example .env         # then fill in API_BASE / API_KEY / VISION_MODEL_NAME
```

Requires Python 3.11–3.13.

## Run

```bash
uv run uvicorn imageblinds.server:app --reload
```

Open http://localhost:8000 — pick `chair.jpg` / `fridge.jpg` (or any JPG), press **Analyze**.

## Tests (offline, no model calls)

```bash
uv run pytest -q
uv run ruff check .
```
