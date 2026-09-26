CREATE TABLE IF NOT EXISTS yld.waitlist_signups (
  email text PRIMARY KEY,
  created_at bigint NOT NULL
);

GRANT SELECT, INSERT, UPDATE ON yld.waitlist_signups TO yld_app;
