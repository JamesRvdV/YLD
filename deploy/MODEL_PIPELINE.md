# Kitchen-specific model worker

The API queues a model job. A separate host-side worker claims it and runs two disposable containers. The Codex container sees opaque dish IDs, dates, sold portions and covers, with the last 14 services withheld. It is instructed to call the checked-in `inspect` and `trial` commands, comparing uniform and recency-weighted weekday ridge models across bounded windows and penalties. Its final choice is constrained by `model_selection.schema.json` and validated again by the worker. Codex has a shell inside that isolated container, so container isolation and the promotion gates remain necessary. The trainer container receives the full numeric history, has **no network**, and emits a JSON artifact containing only bounded numeric coefficients and uncertainty. The worker checks the artifact against the approved algorithm, reproduces its coefficients, and replays the held-out 14 services against YLD's existing forecast. Only dishes with at least a 3% and 0.1-portion mean absolute error improvement are activated. All other dishes continue on the standard forecast.

The upload modal accepts a menu-cost sheet and a sales report, previews their
matched dishes, and queues training in the same database transaction as an
eligible import. `model_jobs.stage` records `queued`, `analyzing`, `training`,
`validating`, `promoting`, or `complete`; the UI polls this field every five
seconds. Its progress bar advances only when a recorded stage completes. The
animated edge signals activity and does not estimate time remaining.

No model-supplied source code, pickle, shell command, or executable artifact reaches the API. The API validates the stored artifact on every plan request and falls back to the standard forecast if it is corrupt. Replacing a CSV or correcting sales or covers from an existing service archives the active model; adding a new service or correcting prepared portions keeps it available. A worker run is rejected if its training inputs change while it trains. The workspace owner can revert an active model from the dashboard.

## Build and start

Build the three images from the repository root on the host that runs the worker.
The agent and trainer use the dependency-free `deploy/model-runtime/uv.lock` for
Python; the agent's Codex CLI still comes from npm:

```sh
docker build -f deploy/model-agent.Dockerfile -t yld-model-agent:1 .
docker build -f deploy/model-trainer.Dockerfile -t yld-model-trainer:1 .
docker build -f deploy/model-proxy.Dockerfile -t yld-model-proxy:1 .
```

Create an **internal** Docker network and start the included CONNECT proxy on it. Connect only the proxy to an external network; do not connect the agent container to that external network. The proxy allows HTTPS tunnelling only to `api.openai.com:443`:

```sh
docker network create --internal yld-agent-internal
docker run -d --restart unless-stopped --name yld-model-proxy --network yld-agent-internal --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,nosuid,nodev,size=16m yld-model-proxy:1
docker network connect bridge yld-model-proxy
```

Set `YLD_AGENT_NETWORK=yld-agent-internal` and `YLD_AGENT_PROXY=http://yld-model-proxy:3128` in the worker environment. The worker verifies that the network is internal before every Codex run and passes proxy settings only to that container. The agent gets the API key, fixed inspect/trial tooling, a read-only numeric snapshot, and a writable temporary directory. It gets no database credentials, Docker socket, API server source, or restaurant names. Agent and trainer containers run as the dedicated non-root host worker UID/GID so that it can read and clean up their bind-mounted outputs. They retain a read-only root filesystem, dropped capabilities, no new privileges, a PID limit, a 512 MiB memory limit, a one-CPU limit, and a 10-minute command timeout. The trainer uses `--network none`. Codex runs with its nested shell sandbox disabled because bubblewrap cannot create user namespaces under these Docker limits; the disposable Docker container is the execution boundary. Do not run that Codex command outside the restricted container.

Run the worker **on the host**, under a dedicated account with access to its Docker daemon and the YLD database. Docker daemon access is highly privileged; do not mount its socket into the public API or either disposable container. A rootless Docker daemon is preferable. Use a separate environment file based on [model-worker.env.example](model-worker.env.example), mode `0600`, with `CODEX_API_KEY` configured. Do not put that key in the frontend or API container environment. The production VM uses Postgres with the applied `20260926065355_yld_model_training_registry.sql` migration; set the worker's `DATABASE_URL` to the same restricted backend role as the API. A local SQLite deployment can instead set `YLD_DB_PATH` to the host path for the same database mounted at `/data/yld.db` in the API container.

From the repository root, with [uv](https://docs.astral.sh/uv/getting-started/installation/) installed:

```sh
set -a
. /absolute/path/to/model-worker.env
set +a
uv run --locked python -m api.model_worker --once
```

Run without `--once` under a service manager to poll continuously. The worker marks runs interrupted for over 30 minutes as failed. Enable `YLD_MODEL_WORKER_ENABLED=1` **in the API container** only after the worker is running. This allows eligible owner imports to queue runs; the API itself never starts Docker or receives the OpenAI key.

## Gates and limits

| Gate | Requirement |
| --- | --- |
| Import | Existing CSV validation; 100 dishes and 20,000 rows maximum. |
| Queue | Owner and CSRF check; at least one dish with 56 services; one pending run and a one-hour request cooldown per workspace. |
| Codex output | Strict JSON schema plus exact-key, enum, type and length validation. |
| Artifact | Versioned JSON only; known workspace dish IDs; finite, bounded coefficients and uncertainty; 100 KiB maximum. |
| Reproducibility | Worker recomputes every trainer coefficient from the input snapshot. |
| Chronological evaluation | Last 14 services per eligible dish were withheld from Codex; each prediction uses only earlier sales and a past-only cover estimate. Candidate must beat standard MAE by at least 3% and 0.1 portions. |
| Promotion | Re-hash workspace history while holding the workspace write lock; atomically archive the previous version and activate the new one. |
| Production | Validate the artifact on every use; fall back to the standard forecast for unmodeled dishes or invalid artifacts. |

The gate assesses **sales forecast error**. It does not establish actual waste reduction, because sold portions can hide stockouts and prepared minus sold may include food carried forward. YLD's historic waste simulation continues to use its standard forecast and is labelled separately from the trained model comparison.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -m unittest tests.test_model_pipeline -v
npm run build
```

Run a real Codex job after configuring a test API key and restricted Docker network, then inspect `/api/models/status` and the dashboard. No API key is included in this repository or its tests; the automated suite exercises the same worker gates with a deterministic agent selection and verifies the networkless trainer container separately.
