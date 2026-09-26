"""Create an idempotent local-only account for development."""

from __future__ import annotations

import os
import sys
import time
import uuid

from . import main


EMAIL = "dev@yld.local"
PASSWORD = "dev-password-123"
WORKSPACE_NAME = "YLD Dev Kitchen"


def run() -> None:
    if os.getenv("YLD_ENV") == "production" or os.getenv("DATABASE_URL"):
        raise RuntimeError("The development seed only supports the local SQLite database")
    main.init_db()
    now = int(time.time())
    with main.db() as conn:
        account = conn.execute("SELECT id,workspace_id FROM accounts WHERE email=?", (EMAIL,)).fetchone()
        if account:
            workspace_id = account["workspace_id"]
            conn.execute("UPDATE accounts SET name=?,role='owner',activated_at=?,password_hash=?,failed_logins=0,locked_until=0 WHERE id=?", ("Dev", now, main.hash_password(PASSWORD), account["id"]))
        else:
            workspace_id = str(uuid.uuid4())
            conn.execute("INSERT INTO workspaces(id,name,created_at,data_mode) VALUES (?,?,?,'empty')", (workspace_id, WORKSPACE_NAME, now))
            conn.execute("INSERT INTO accounts(id,workspace_id,email,name,role,activated_at,password_hash,failed_logins,locked_until) VALUES (?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), workspace_id, EMAIL, "Dev", "owner", now, main.hash_password(PASSWORD), 0, 0))
    print(f"Seeded {EMAIL} for workspace {workspace_id}")


if __name__ == "__main__":
    try:
        run()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from None
