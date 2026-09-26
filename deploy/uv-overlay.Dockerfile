# Move an already-running YLD image to the locked uv environment while retaining
# its application code and frontend assets.
ARG BASE_IMAGE=yld:email-20260926-1
FROM ${BASE_IMAGE}
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-cache && rm -f api/requirements.txt
ENV PATH="/app/.venv/bin:$PATH"
