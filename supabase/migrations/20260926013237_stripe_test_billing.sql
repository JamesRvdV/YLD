-- Billing data belongs to the private application schema, never the Data API.
CREATE TABLE yld.workspace_billing (
  workspace_id text PRIMARY KEY REFERENCES yld.workspaces(id) ON DELETE CASCADE,
  stripe_customer_id text NOT NULL UNIQUE,
  stripe_subscription_id text NOT NULL UNIQUE,
  plan text NOT NULL CHECK (plan IN ('local', 'multi_chain')),
  status text NOT NULL,
  last_event_created bigint NOT NULL,
  updated_at bigint NOT NULL
);
REVOKE ALL ON yld.workspace_billing FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON yld.workspace_billing TO yld_app;
