# YLD on arro-prod-vm

YLD runs in its own Compose project at `~/yld`. The container is named
`yld-api`, joins the existing `arro-edge` network, and publishes no host port.
It is limited to 384 MiB RAM, half a CPU, and 128 processes. Its writable data
is confined to `~/yld/data`; the container root filesystem is read-only.

The initial deployment uses `YLD_ENV=preview` because email delivery is not
configured yet. It is reachable only by other containers on `arro-edge` until
the Caddy hostname route is installed.

## Check the container

```sh
cd ~/yld
docker compose ps
docker exec arro-caddy wget -qO- http://yld-api:8000/api/health
docker stats --no-stream yld-api
```

## Public route

Once `yld.nz` is active at Crazy Domains, point its apex A record to the VM's
reserved IP `34.116.70.110` and set `www` as a CNAME to `yld.nz`. The proposed
Caddy route is in `Caddyfile.yld`. The VM holds a validated combined candidate
at `~/yld/Caddyfile.candidate` and a copy of the original at
`~/yld/Caddyfile.arro-backup`. Validate the candidate again and reload Caddy
only after the DNS records resolve. Do not restart the Arro Compose project.

Before enabling invitation email, set `YLD_ENV=production`,
`YLD_PUBLIC_URL=https://yld.nz`, `RESEND_API_KEY`, and a verified
`YLD_EMAIL_FROM` in `~/yld/.env` (mode `600`), then recreate only YLD with
`docker compose up -d --no-deps --force-recreate`.

To roll back YLD's public route, restore the original Caddyfile from the
backup, validate it, and reload Caddy. To stop only YLD, run
`docker compose down` from `~/yld`.
