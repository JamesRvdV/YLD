FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates && rm -rf /var/lib/apt/lists/*
RUN npm install -g @openai/codex@0.157.0
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/
WORKDIR /opt/yld
COPY deploy/model-runtime/pyproject.toml deploy/model-runtime/uv.lock ./
RUN UV_PYTHON_DOWNLOADS=never uv sync --locked --python python3 --no-cache
COPY api/modeling.py api/json_contract.py api/agent_tools.py api/model_selection.schema.json api/model_artifact.schema.json ./api/
ENV PATH="/opt/yld/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
