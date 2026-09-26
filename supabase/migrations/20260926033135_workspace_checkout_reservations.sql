-- One open Stripe Checkout Session per workspace, shared by all API processes.
CREATE TABLE yld.workspace_checkout (
  workspace_id text PRIMARY KEY REFERENCES yld.workspaces(id) ON DELETE CASCADE,
  plan text NOT NULL CHECK (plan IN ('local', 'multi_chain')),
  idempotency_key text NOT NULL,
  session_id text,
  session_url text,
  expires_at bigint NOT NULL
);
REVOKE ALL ON yld.workspace_checkout FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON yld.workspace_checkout TO yld_app;
