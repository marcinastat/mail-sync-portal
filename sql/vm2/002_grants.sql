-- Uprawnienia roli aplikacyjnej mail_app. Uruchamiane po 001_schema.sql,
-- z podstawioną nazwą roli przez scripts/vm2/20-postgresql.sh (psql -v app_role=...).
-- audit_log jest append-only: appka może tylko SELECT/INSERT, nigdy UPDATE/DELETE.

GRANT SELECT, INSERT, UPDATE ON virtual_domains TO :app_role;
-- DELETE na virtual_mailboxes potrzebne do usuwania skrzynki z panelu
-- (provisioning API: DELETE FROM virtual_mailboxes). Bez tego kasowanie skrzynki
-- pada „permission denied for table virtual_mailboxes".
GRANT SELECT, INSERT, UPDATE, DELETE ON virtual_mailboxes TO :app_role;
-- Dovecot (jako mail_app) czyta aliasy przy każdym logowaniu; zarządzanie
-- (dodawanie/usuwanie aliasów) też idzie tą rolą.
GRANT SELECT, INSERT, UPDATE, DELETE ON virtual_domain_aliases TO :app_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :app_role;

GRANT SELECT, INSERT ON audit_log TO :app_role;
REVOKE UPDATE, DELETE ON audit_log FROM :app_role;
