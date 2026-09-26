"""Create the private host worker environment from YLD's existing DB config.

Run from ~/yld on arro-prod-vm. This never prints the database URL and does
not replace an existing worker environment (which may contain an API key).
"""

from pathlib import Path


root = Path.cwd()
target = root / "model-worker.env"
if target.exists():
    raise SystemExit("model-worker.env already exists; leaving it untouched")

database_lines = [
    line for line in (root / ".env").read_text().splitlines()
    if line.startswith("DATABASE_URL=") and line.removeprefix("DATABASE_URL=").strip()
]
if len(database_lines) != 1:
    raise SystemExit("Expected one nonempty DATABASE_URL in ~/yld/.env")

content = "\n".join([
    database_lines[0],
    "CODEX_API_KEY=",
    "YLD_AGENT_NETWORK=yld-agent-internal",
    "YLD_AGENT_PROXY=http://yld-model-proxy:3128",
    "YLD_AGENT_IMAGE=yld-model-agent:1",
    "YLD_TRAINER_IMAGE=yld-model-trainer:1",
    "",
])
target.write_text(content)
target.chmod(0o600)
print("Created private model-worker.env with a blank CODEX_API_KEY")
