# YLD on arro-prod-vm

YLD runs in its own Compose project at `~/yld`. The container is named
`yld-api`, joins the existing `arro-edge` network, and publishes no host port.
It is limited to 384 MiB RAM, half a CPU, and 128 processes. Its root
filesystem is read-only. The current container uses SQLite in `~/yld/data`;
`~/yld/data/yld-before-import-20260926.db` is the pre-deployment backup.
The Supabase schema is prepared in the repo but is not connected on this VM.

The initial deployment uses `YLD_ENV=preview` because email delivery is not
configured yet. The Caddy hostname route is installed, but public HTTPS is
waiting for the `yld.nz` DNS A record to point to the VM.

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

Point the apex A record to the VM's reserved IP `34.116.70.110` and set `www`
as a CNAME to `yld.nz` in Crazy Domains. The Caddy route is already active;
it will obtain HTTPS certificates after DNS resolves to this VM. The route is
in `Caddyfile.yld`, and the original shared Caddyfile is backed up at
`~/yld/Caddyfile.arro-backup`. Do not restart the Arro Compose project.

Before enabling invitation email, set `YLD_ENV=production`,
`YLD_PUBLIC_URL=https://yld.nz`, `RESEND_API_KEY`, and a verified
`YLD_EMAIL_FROM` in `~/yld/.env` (mode `600`), then recreate only YLD with
`docker compose up -d --no-deps --force-recreate`.

To switch to Supabase later, apply `supabase/migrations`, add the restricted
`yld_app` pooler connection as `DATABASE_URL`, and set `YLD_REQUIRE_POSTGRES=1`.
Keep the connection string out of source control. This is a separate database
cutover and will not happen merely by changing the image.

To roll back YLD's public route, restore the original Caddyfile from the
backup, validate it, and reload Caddy. To stop only YLD, run
`docker compose down` from `~/yld`.
