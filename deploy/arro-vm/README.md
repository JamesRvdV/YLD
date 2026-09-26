# YLD on arro-prod-vm

YLD runs in its own Compose project at `~/yld`. The container is named
`yld-api`, joins the existing `arro-edge` network, and publishes no host port.
It is limited to 384 MiB RAM, half a CPU, and 128 processes. Its root
filesystem is read-only. The live app uses the private `yld` schema in the
YLD Supabase Postgres project through the restricted `yld_app` role. The
SQLite file in `~/yld/data` is a legacy copy, not the live database.

The deployment uses `YLD_ENV=production` and serves public HTTPS at `yld.nz`.
The private `~/yld/.env` contains the Resend API key and
`YLD_EMAIL_FROM="YLD <hello@yld.nz>"`. Resend must show the domain as verified
for sending before invitation emails will be accepted.

Once HTTPS is working, bootstrap the only admin account with a private one-use
password setup link from the YLD container:

```sh
docker exec yld-api python -m api.invite --email axel.mckenna7@gmail.com --workspace 'Admin Kitchen'
```

Open that URL privately and set a password. The admin then sends all other
invitation emails from `/admin`. Do not post the setup URL in public channels
or server logs.

## Check the container

```sh
cd ~/yld
docker compose ps
docker exec arro-caddy wget -qO- http://yld-api:8000/api/health
docker stats --no-stream yld-api
```

## Public route

The apex and `www` A records point to the VM's reserved IP `34.116.70.110`
in Crazy Domains. Caddy redirects `www` to the apex. The route is in
`Caddyfile.yld`, and the original shared Caddyfile is backed up at
`~/yld/Caddyfile.arro-backup`. Do not restart the Arro Compose project.

After changing YLD settings in `~/yld/.env` (mode `600`), recreate only YLD
with `docker compose up -d --no-deps --force-recreate api`.

## Model agent

The API and agent workspace run as `yld:agent-20260926-3`. Sales upload,
mapping, readiness charts, the live left-to-right model pipeline, and held-out
forecast results share one screen. The private
Postgres schema has the model registry, import mapping, and waitlist migrations.
`yld-model-proxy` is attached to an internal Docker network and allows outbound
CONNECT traffic only to `api.openai.com:443`; the agent and trainer images are
loaded on the VM. The trusted host-side worker source and locked Python
environment are at `~/yld/model-worker`. A systemd unit is installed as
`yld-model-worker` but is not enabled until a rotated `CODEX_API_KEY` is placed
in `~/yld/model-worker.env` (mode `600`). Do not reuse the key posted in chat.

After adding that key to the existing blank `CODEX_API_KEY=` line, start the
worker and then enable the training control in the API:

```sh
sudo systemctl enable --now yld-model-worker
systemctl is-active yld-model-worker
# Set YLD_MODEL_WORKER_ENABLED=1 in ~/yld/.env without changing other secrets.
cd ~/yld
docker compose up -d --no-deps --force-recreate api
docker compose ps
```

The API never receives the OpenAI key or Docker socket. The worker uses the
same restricted Postgres connection as the API. See [MODEL_PIPELINE.md](../MODEL_PIPELINE.md)
for sandbox, training, gate, and rollback details. To stop new training, set
`YLD_MODEL_WORKER_ENABLED=0` in the API environment and recreate only `api`;
then stop `yld-model-worker`.

The pre-agent Compose file is at `~/yld/compose.before-agent-20260926.yaml`.
To roll back the API/UI image, copy it over `~/yld/compose.yaml` and run
`docker compose up -d --no-deps --force-recreate api`.

To roll back YLD's public route, restore the original Caddyfile from the
backup, validate it, and reload Caddy. To stop only YLD, run
`docker compose down` from `~/yld`.
