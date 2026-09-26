-- Import mappings are private workspace configuration read only by the YLD backend.
CREATE TABLE IF NOT EXISTS yld.workspace_import_mappings (
    workspace_id text NOT NULL REFERENCES yld.workspaces(id),
    source_signature text NOT NULL,
    mapping_json text NOT NULL,
    updated_at bigint NOT NULL,
    PRIMARY KEY (workspace_id, source_signature)
);
REVOKE ALL ON yld.workspace_import_mappings FROM PUBLIC;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON yld.workspace_import_mappings FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON yld.workspace_import_mappings FROM authenticated';
  END IF;
END $$;
GRANT SELECT, INSERT, UPDATE, DELETE ON yld.workspace_import_mappings TO yld_app;
