# Konta administratorów

**Ustawienia → Użytkownicy** (`/admin/settings/users`) — zarządzanie kontami do panelu.
Każdy admin ma wymuszone **2FA (TOTP)** i przy pierwszym logowaniu przechodzi
obowiązkowy enrollment (kod QR + kody odzyskiwania).

## Operacje

- **Nowy użytkownik** — podajesz login i e-mail; portal generuje **hasło tymczasowe**
  (pokazane raz — przekaż bezpiecznym kanałem). Przy pierwszym logowaniu nowy admin
  ustawi TOTP.
- **Moje hasło** — zmiana własnego hasła (obecne → nowe ×2, min. 10 znaków). TOTP bez zmian.
- **Reset TOTP** — kasuje 2FA użytkownika; przy następnym logowaniu przejdzie ponowną
  konfigurację (gdy zgubił telefon/aplikację).
- **Dezaktywuj / Aktywuj** — czasowo wyłącza konto bez usuwania (i z powrotem).
- **Usuń** — trwałe usunięcie konta (kasuje też jego TOTP). Wpisy w audycie zostają.

## Zabezpieczenia

- Nie da się **usunąć własnego konta** ani **dezaktywować siebie** (przy swoim koncie
  widnieje tylko „to Twoje konto").
- Nie da się **usunąć ostatniego aktywnego administratora** — chroni przed zamknięciem
  się na zewnątrz.
- Każda operacja (utworzenie, dezaktywacja, aktywacja, usunięcie, reset TOTP, zmiana
  hasła) jest **audytowana** (`/admin/audit`).

## Zapomniane hasło / zablokowany dostęp

Panelowy **Reset TOTP** wymaga, by ktoś **był zalogowany** i zresetował konto innego
admina. Gdy jednak **nikt nie może się zalogować** (np. jedyny admin zapomniał hasła
i/lub zgubił authenticator), użyj narzędzi ratunkowych **na konsoli VM1** (jako root,
przez SSH lub lokalnie). To dwa niezależne narzędzia — użyj jednego albo obu.

**Reset hasła:**

```
sudo portal-admin-password.sh --list                 # pokaż loginy
sudo portal-admin-password.sh <login>                # ustaw nowe hasło (pyta 2x)
sudo portal-admin-password.sh <login> --random       # wygeneruj losowe i pokaż raz
```

**Reset TOTP** (gdy admin stracił telefon/aplikację — samo hasło NIE wystarczy,
logowanie nadal żąda kodu TOTP):

```
sudo portal-admin-totp-reset.sh --list               # loginy + status TOTP
sudo portal-admin-totp-reset.sh <login>              # kasuje 2FA (pyta o potwierdzenie)
```

Po resecie TOTP admin przy następnym logowaniu **paruje 2FA od nowa** — dostaje
świeży kod QR i **nowe kody odzyskiwania**.

**Zapomniane hasło + zgubiony authenticator** (pełne odblokowanie) — oba naraz:

```
sudo portal-admin-password.sh <login>
sudo portal-admin-totp-reset.sh <login>
```

Oba narzędzia hashują/audytują tak samo jak panel; każdy reset jest widoczny
w audycie (`/admin/audit`).
