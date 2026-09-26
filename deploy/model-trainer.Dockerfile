FROM python:3.11-slim
WORKDIR /opt/yld
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/
COPY deploy/model-runtime/pyproject.toml deploy/model-runtime/uv.lock ./
RUN UV_PYTHON_DOWNLOADS=never uv sync --locked --python python3 --no-cache
COPY api/modeling.py api/json_contract.py api/train_container.py api/model_selection.schema.json api/model_artifact.schema.json ./api/
ENV PATH="/opt/yld/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
