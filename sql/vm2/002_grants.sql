-- Uprawnienia roli aplikacyjnej mail_app. Uruchamiane po 001_schema.sql,
-- z podstawioną nazwą roli przez scripts/vm2/20-postgresql.sh (psql -v app_role=...).
-- audit_log jest append-only: appka może tylko SELECT/INSERT, nigdy UPDATE/DELETE.

GRANT SELECT, INSERT, UPDATE ON virtual_domains TO :app_role;
GRANT SELECT, INSERT, UPDATE ON virtual_mailboxes TO :app_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :app_role;

GRANT SELECT, INSERT ON audit_log TO :app_role;
REVOKE UPDATE, DELETE ON audit_log FROM :app_role;
