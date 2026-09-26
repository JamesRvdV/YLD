# uv rollout on arro-prod-vm

The running YLD image is `yld:email-uv-8131a84`. It layers the uv-locked
environment from commit `8131a84` onto `yld:email-20260926-1`, retaining
that release's application code and frontend assets. It was built with
`deploy/uv-overlay.Dockerfile`. Future images can use the main `Dockerfile`
once the email release source is committed.

The previous Compose file is at
`~/yld/compose.before-email-uv-8131a84.yaml`. The SQLite backup made just
before the switch is at `~/yld/data/yld-before-email-uv-8131a84.db`.
The original email image remains available on the VM for rollback.
