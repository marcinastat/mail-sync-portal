-- mail_db (VM2) — domeny/skrzynki wirtualne dla Postfix + Dovecot, oraz
-- lokalny audit log wywołań provisioning API.
-- Uruchamiane jednorazowo przez scripts/vm2/20-postgresql.sh (idempotentnie:
-- CREATE ... IF NOT EXISTS / ON CONFLICT DO NOTHING wszędzie gdzie ma to sens).

CREATE TABLE IF NOT EXISTS virtual_domains (
    id          serial PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS virtual_mailboxes (
    id                serial PRIMARY KEY,
    domain_id         integer NOT NULL REFERENCES virtual_domains(id) ON DELETE RESTRICT,
    local_part        text NOT NULL,
    password_hash     text NOT NULL,       -- format zgodny z Dovecot (SHA512-CRYPT)
    quota_bytes       bigint NOT NULL DEFAULT 0,  -- 0 = bez limitu
    maildir           text NOT NULL,       -- względem /var/mail/vhosts/<domain>/<local_part>/
    is_active         boolean NOT NULL DEFAULT true,
    password_overridden boolean NOT NULL DEFAULT false, -- ustawiane przez reset-password
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (domain_id, local_part)
);

CREATE INDEX IF NOT EXISTS idx_virtual_mailboxes_domain ON virtual_mailboxes(domain_id);

-- Append-only audit log — REVOKE UPDATE/DELETE stosowane niżej dla roli aplikacyjnej.
CREATE TABLE IF NOT EXISTS audit_log (
    id            bigserial PRIMARY KEY,
    occurred_at   timestamptz NOT NULL DEFAULT now(),
    actor         text NOT NULL,     -- CN certyfikatu klienta wywołującego API (np. vm1-portal-client)
    action        text NOT NULL,     -- np. "mailbox.create", "mailbox.reset_password", "system.update"
    target_type   text,
    target_id     text,
    details       jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_ip     inet,
    prev_hash     text NOT NULL,
    row_hash      text NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_occurred_at ON audit_log(occurred_at);

-- Funkcja pomocnicza: aktualizuje updated_at przy każdej zmianie wiersza.
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_virtual_mailboxes_touch ON virtual_mailboxes;
CREATE TRIGGER trg_virtual_mailboxes_touch
    BEFORE UPDATE ON virtual_mailboxes
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
