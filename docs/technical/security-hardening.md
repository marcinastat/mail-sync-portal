# Utwardzenie i audyt bezpieczeństwa

Podsumowanie warstw zabezpieczeń zweryfikowanych na żywym środowisku.

## Sieć i izolacja

- **firewalld** na obu VM w domyślnej strefie `drop`. VM2 wpuszcza 143/993/587/8443
  **wyłącznie z IP VM1** (rich rules), SSH z podsieci administracyjnej. VM2 nie jest
  osiągalna bezpośrednio z podsieci admina — jedyną drogą do danych jest VM1.
- **nginx allow/deny** per ścieżka — konfigurowalne z portalu strefy dostępu osobno dla
  `/admin` i webmaila (patrz [Strefy dostępu sieci](/admin/docs/user/network-access-zones)).
- **PostgreSQL** nasłuchuje tylko na `127.0.0.1` (obie VM); role aplikacyjne
  (`portal_app`, `roundcube_app`, `mail_app`) uwierzytelniają się **`scram-sha-256`**
  (nie `md5`) — patrz `pg_hba.conf` (VM1 `scripts/vm1/20-postgresql.sh`, VM2
  `scripts/vm2/20-postgresql.sh`).
- **VM2 API** wymaga **mTLS** — połączenie bez certyfikatu klienta jest odrzucane.

## TLS (nginx, VM1)

- Tylko **TLSv1.2 i TLSv1.3** (1.0/1.1 odrzucane).
- Zestaw szyfrów „Mozilla intermediate": wyłącznie AEAD (GCM/ChaCha20) na ECDHE/DHE
  (PFS), bez CBC/RC4/3DES. `ssl_prefer_server_ciphers on`, bez ticketów sesji.
- Nagłówki bezpieczeństwa (poziom serwera, `always`): `Strict-Transport-Security`
  (`max-age=31536000; includeSubDomains`), `Content-Security-Policy` (jeden zestaw dla
  Roundcube i `/admin` — blokuje ładowanie skryptów z obcych domen, `object-src 'none'`,
  `frame-ancestors 'self'`, `base-uri`/`form-action 'self'`; `'unsafe-inline'`/`'unsafe-eval'`
  pod Roundcube/Alpine.js), `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
  `Referrer-Policy`.
- `server_tokens off` (nginx) i **`expose_php = Off`** (PHP) — wersje nie są ujawniane
  (nagłówek `X-Powered-By` usunięty).
- Uwaga: HSTS działa przy dostępie po nazwie hosta z zaufanym certem; przy dostępie po
  samym IP przeglądarki go ignorują (patrz [cykl życia TLS](/admin/docs/technical/tls-lifecycle)).

## SSH

- **Root tylko kluczem, użytkownicy hasłem**: `PermitRootLogin prohibit-password`
  + `PasswordAuthentication yes` (drop-in `/etc/ssh/sshd_config.d/00-portal-hardening.conf`).
  Zwykli użytkownicy mogą logować się hasłem (chroni ich fail2ban jail `sshd`), root
  wyłącznie kluczem. Ograniczenie roota instalowane **tylko** gdy root ma już wgrany
  klucz publiczny (guard przed lockoutem roota); logowanie hasłem użytkowników pozostaje
  włączone niezależnie.
- Dodatkowe utwardzenie w tym samym drop-inie: `X11Forwarding no`, `LoginGraceTime 30`,
  `MaxAuthTries 4`, idle-timeout `ClientAliveInterval 300` / `ClientAliveCountMax 2`.
- Instalacja usuwa luźny drop-in z obrazu (`01-permitrootlogin.conf: PermitRootLogin yes`),
  żeby nie było „miny" na wypadek zniknięcia pliku `00-*`.
- Zestaw MAC/Ciphers/Kex świadomie zostawiony pod **systemową crypto-policy** (`DEFAULT`) —
  wymuszanie w drop-inie jest nieskuteczne (crypto-policy czytana wcześniej), a globalne
  usunięcie HMAC-SHA1 mogłoby zerwać imapsync do starszych serwerów źródłowych.

## Piaskownica usług (systemd)

- Usługi portalu i API działają z `ProtectSystem` (strict/full), `ProtectHome`,
  `PrivateTmp`, wąskimi `ReadWritePaths`. Sekrety dostarczane przez
  `LoadCredentialEncrypted` (systemd-creds), nigdy jako plaintext na dysku.
- Operacje uprzywilejowane (branding, TLS, strefy sieci, aktualizacje, kasowanie
  maildira) idą przez **wąskie helpery root** dopuszczone w `sudoers.d` do konkretnych
  komend. Helpery leżą poza drzewem należącym do konta usługi (`/usr/local/sbin` lub
  root-owned `/opt/.../bin`), żeby konto usługi nie mogło ich podmienić i eskalować.
- `dnf` (aktualizacje) uruchamiany przez `systemd-run` — poza piaskownicą usługi, która
  inaczej blokuje zapis do `/usr` i `/var`.
- **Anti-tamper**: kod i venv aplikacji są **read-only dla usługi** — portal
  (`ReadOnlyPaths=/opt/portal-app`, z wyjątkiem `.../static`), VM2 API (`/opt/vm2-api` poza
  `ReadWritePaths`). Deploy (rsync/skrypty) działa dalej, bo leci poza namespace usługi;
  ewentualny RCE w aplikacji nie nadpisze własnego kodu (utrudniona trwałość).
- **Moduły SELinux** (enforcing): `portal_nginx_gunicorn` (nginx→gunicorn po gnieździe,
  VM1) oraz `portal_mail_pgsql` (Dovecot `dovecot_auth_t`→PostgreSQL, VM2 — bez niego
  logowanie na skrzynki pada „Temporary authentication failure"). Ładowane przez skrypty
  instalacyjne (`50-portal-app.sh`, `30-postfix-dovecot.sh`).
- **`rspamd` przypięty** (`dnf versionlock`) — repo rspamd.com ma stary klucz GPG odrzucany
  przez surowszy weryfikator OpenPGP EL10, więc bez pinu `dnf update` (tryb „all") sypie
  się na GPG. Pin pozwala łatać system (w tym jądro), a `gpgcheck` zostaje włączony.

## Aplikacja

- Panel wymaga logowania + **obowiązkowego TOTP**. Nieudane logowania trafiają do logu
  parsowanego przez **fail2ban** (jaile: `sshd`, `portal-admin-auth`, `roundcube-auth`,
  `nginx-limit-req`; VM2: `sshd`). Status blokad (jaile + zbanowane IP obu serwerów)
  widać w **Raportach** (read-only); diagnostyka i odbanowanie: [Runbook fail2ban](/admin/docs/technical/runbooks/fail2ban).
- Adres klienta do audytu i fail2ban pochodzi z nagłówka `X-Real-IP` (nginx proxuje przez
  gniazdo UNIX, więc `request.client` jest puste).
- Hasła źródłowe szyfrowane w bazie (Fernet, klucz z systemd-creds). Audit log jest
  append-only z hash-chainingiem.
- Silnik imapsync nie zawiera flag mutujących źródło — nie da się ich włączyć konfiguracją.

## Powierzchnia ataku

- VM2 Dovecot: tylko IMAP/IMAPS (POP3 wyłączony, `protocols = imap lmtp`).
- Nieużywane porty pozostają za zaporą (`drop`), ale nasłuchujące usługi ograniczamy
  do faktycznie potrzebnych.
