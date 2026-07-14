# Utwardzenie i audyt bezpieczeństwa

Podsumowanie warstw zabezpieczeń zweryfikowanych na żywym środowisku.

## Sieć i izolacja

- **firewalld** na obu VM w domyślnej strefie `drop`. VM2 wpuszcza 143/993/587/8443
  **wyłącznie z IP VM1** (rich rules), SSH z podsieci administracyjnej. VM2 nie jest
  osiągalna bezpośrednio z podsieci admina — jedyną drogą do danych jest VM1.
- **nginx allow/deny** per ścieżka — konfigurowalne z portalu strefy dostępu osobno dla
  `/admin` i webmaila (patrz [Strefy dostępu sieci](/admin/docs/user/network-access-zones)).
- **PostgreSQL** nasłuchuje tylko na `127.0.0.1` (obie VM).
- **VM2 API** wymaga **mTLS** — połączenie bez certyfikatu klienta jest odrzucane.

## TLS (nginx, VM1)

- Tylko **TLSv1.2 i TLSv1.3** (1.0/1.1 odrzucane).
- Zestaw szyfrów „Mozilla intermediate": wyłącznie AEAD (GCM/ChaCha20) na ECDHE/DHE
  (PFS), bez CBC/RC4/3DES. `ssl_prefer_server_ciphers on`, bez ticketów sesji.
- Nagłówki bezpieczeństwa (poziom serwera, `always`): `Strict-Transport-Security`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`.
- `server_tokens off` — wersja nginx nie jest ujawniana.
- Uwaga: HSTS działa przy dostępie po nazwie hosta z zaufanym certem; przy dostępie po
  samym IP przeglądarki go ignorują (patrz [cykl życia TLS](/admin/docs/technical/tls-lifecycle)).

## SSH

- **Tylko klucze**: `PasswordAuthentication no`, root `prohibit-password` (drop-in
  `/etc/ssh/sshd_config.d/00-portal-hardening.conf`). Instalowane przez skrypty
  hardeningu **tylko** gdy root ma już wgrany klucz publiczny (guard przed lockoutem).

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

## Aplikacja

- Panel wymaga logowania + **obowiązkowego TOTP**. Nieudane logowania trafiają do logu
  parsowanego przez **fail2ban** (jaile: `sshd`, `portal-admin-auth`, `roundcube-auth`,
  `nginx-limit-req`).
- Adres klienta do audytu i fail2ban pochodzi z nagłówka `X-Real-IP` (nginx proxuje przez
  gniazdo UNIX, więc `request.client` jest puste).
- Hasła źródłowe szyfrowane w bazie (Fernet, klucz z systemd-creds). Audit log jest
  append-only z hash-chainingiem.
- Silnik imapsync nie zawiera flag mutujących źródło — nie da się ich włączyć konfiguracją.

## Powierzchnia ataku

- VM2 Dovecot: tylko IMAP/IMAPS (POP3 wyłączony, `protocols = imap lmtp`).
- Nieużywane porty pozostają za zaporą (`drop`), ale nasłuchujące usługi ograniczamy
  do faktycznie potrzebnych.
