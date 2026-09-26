ALTER TABLE yld.accounts ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE yld.accounts ADD COLUMN IF NOT EXISTS failed_logins integer NOT NULL DEFAULT 0;
ALTER TABLE yld.accounts ADD COLUMN IF NOT EXISTS locked_until bigint NOT NULL DEFAULT 0;
