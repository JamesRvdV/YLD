-- Private model registry. Only the backend's restricted role can reach it.
CREATE TABLE IF NOT EXISTS yld.model_jobs (
  id text PRIMARY KEY,
  workspace_id text NOT NULL REFERENCES yld.workspaces(id),
  status text NOT NULL CHECK (status IN ('queued','running','promoted','rejected','failed')),
  created_at bigint NOT NULL,
  started_at bigint,
  finished_at bigint,
  data_hash text,
  reason text,
  metrics_json text
);
CREATE INDEX IF NOT EXISTS model_jobs_workspace ON yld.model_jobs(workspace_id,created_at);
CREATE UNIQUE INDEX IF NOT EXISTS model_jobs_one_pending ON yld.model_jobs(workspace_id) WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS yld.model_versions (
  id text PRIMARY KEY,
  workspace_id text NOT NULL REFERENCES yld.workspaces(id),
  status text NOT NULL CHECK (status IN ('active','archived')),
  artifact_json text NOT NULL,
  metrics_json text NOT NULL,
  data_hash text NOT NULL,
  created_at bigint NOT NULL,
  activated_at bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS model_versions_workspace ON yld.model_versions(workspace_id,status,created_at);
CREATE UNIQUE INDEX IF NOT EXISTS model_versions_one_active ON yld.model_versions(workspace_id) WHERE status='active';
REVOKE ALL ON yld.model_jobs, yld.model_versions FROM PUBLIC;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON yld.model_jobs, yld.model_versions FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON yld.model_jobs, yld.model_versions FROM authenticated';
  END IF;
END $$;
GRANT SELECT, INSERT, UPDATE, DELETE ON yld.model_jobs, yld.model_versions TO yld_app;
