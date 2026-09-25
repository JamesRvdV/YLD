-- YLD uses a private schema through a restricted backend database role.
-- The browser has no direct access to these tables through the Data API.
CREATE SCHEMA IF NOT EXISTS yld;
REVOKE ALL ON SCHEMA yld FROM PUBLIC;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'yld_app') THEN
    CREATE ROLE yld_app LOGIN NOINHERIT;
  END IF;
END $$;
ALTER ROLE yld_app SET search_path = yld;
GRANT CONNECT ON DATABASE postgres TO yld_app;
GRANT USAGE ON SCHEMA yld TO yld_app;

CREATE TABLE IF NOT EXISTS yld.workspaces (
  id text PRIMARY KEY,
  name text NOT NULL,
  created_at bigint NOT NULL,
  data_mode text NOT NULL DEFAULT 'empty'
);
CREATE TABLE IF NOT EXISTS yld.accounts (
  id text PRIMARY KEY,
  workspace_id text NOT NULL REFERENCES yld.workspaces(id),
  email text NOT NULL UNIQUE,
  name text NOT NULL,
  role text NOT NULL,
  activated_at bigint
);
CREATE TABLE IF NOT EXISTS yld.workspace_dishes (
  workspace_id text NOT NULL REFERENCES yld.workspaces(id),
  id text NOT NULL,
  name text NOT NULL,
  category text NOT NULL,
  price double precision NOT NULL,
  ingredient_cost double precision NOT NULL,
  baseline integer NOT NULL,
  shortage_cost double precision NOT NULL,
  description text NOT NULL,
  PRIMARY KEY (workspace_id, id)
);
CREATE TABLE IF NOT EXISTS yld.workspace_history (
  workspace_id text NOT NULL REFERENCES yld.workspaces(id),
  day text NOT NULL,
  dish_id text NOT NULL,
  sold integer NOT NULL,
  prepared integer NOT NULL,
  leftover integer NOT NULL,
  covers integer NOT NULL,
  prep_known integer NOT NULL DEFAULT 1,
  PRIMARY KEY (workspace_id, day, dish_id),
  FOREIGN KEY (workspace_id, dish_id) REFERENCES yld.workspace_dishes(workspace_id, id)
);
CREATE TABLE IF NOT EXISTS yld.auth_links (
  token_hash text PRIMARY KEY,
  account_id text NOT NULL REFERENCES yld.accounts(id),
  kind text NOT NULL,
  expires_at bigint NOT NULL,
  used_at bigint,
  created_at bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS auth_links_account ON yld.auth_links(account_id, created_at);
CREATE TABLE IF NOT EXISTS yld.sessions (
  token_hash text PRIMARY KEY,
  account_id text NOT NULL REFERENCES yld.accounts(id),
  csrf_token text NOT NULL,
  expires_at bigint NOT NULL,
  created_at bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_account ON yld.sessions(account_id);

REVOKE ALL ON ALL TABLES IN SCHEMA yld FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA yld TO yld_app;
