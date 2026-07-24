# FAQ

**Czy synchronizacja może coś skasować na serwerze źródłowym?**
Nie. To twarde ograniczenie w kodzie (`portal_app/services/imapsync_runner.py`) — flagi imapsync kasujące/mutujące źródło (`--delete1`, `--expunge1` itd.) nie istnieją nigdzie w kodzie i nie da się ich włączyć żadnym ustawieniem.

**Czy mogę ręcznie zmienić hasło skrzynki na serwerze docelowym?**
Tak, na stronie skrzynki (`/admin/mailboxes/<id>`) — nie musisz znać obecnego hasła. Po tej operacji hasło przestaje być automatycznie nadpisywane lustrzaną kopią hasła źródłowego przy kolejnych importach.

**Dlaczego przeglądarka pokazuje ostrzeżenie o certyfikacie?**
Domyślnie VM1 używa certyfikatu self-signed (ważnego 10 lat) — to celowe, bo VM1 nie jest wystawiona do internetu. Możesz wgrać własny certyfikat (`/admin/settings/tls`) albo skonfigurować certbota w trybie DNS-01 (`scripts/vm1/certbot-setup.sh`).

**Co się dzieje, gdy wiadomość zniknie ze skrzynki źródłowej?**
Domyślnie nic — zostaje zachowana na serwerze docelowym (to jest właśnie "drift" widoczny na pulpicie). Możesz włączyć kasowanie na docelowym per skrzynka lub grupowo, ale wymaga to jawnego potwierdzenia w formularzu.

**Co jeśli dostawca danych używa RAR zamiast ZIP/7z?**
Zainstaluj na serwerze pakiet `unrar` (EPEL) — obsługa RAR jest wtedy dostępna automatycznie. ZIP i 7z działają od razu, bez dodatkowych zależności.

**Ile skrzynek obsłuży to środowisko?**
Zaprojektowane i przetestowane założeniowo pod małą skalę (do ~50 skrzynek). Przy większej skali warto rozważyć oddzielenie instancji PostgreSQL i przegląd limitów throttlingu.

**Jak trwale usunąć skrzynkę?**
Na stronie skrzynki (`/admin/mailboxes/<id>`), w sekcji „Strefa niebezpieczna", wpisując dokładny adres skrzynki jako potwierdzenie. Usuwa to skrzynkę **docelową** na VM2 (rekord i całą zarchiwizowaną pocztę) oraz jej konfigurację w portalu. Serwer **źródłowy pozostaje nietknięty**. Operacji nie da się cofnąć — jeśli chcesz tylko wstrzymać pobieranie, zamiast usuwać wyłącz synchronizację.

**Dlaczego liczba wiadomości „u nas / źródło" się nie zgadza?**
To zwykle nie ubytek. imapsync po deduplikacji liczy unikalne wiadomości, a surowy licznik folderów źródła bywa wyższy (np. duplikaty tego samego maila na źródle, których celowo nie kopiujemy). Panel pokazuje realny stan docelowej skrzynki i znacznik „komplet · 0 brakujących"; dopóki „brakujących" = 0, wszystko jest zsynchronizowane.

**Jak ograniczyć, kto może wejść na panel/webmail?**
[Ustawienia → Strefy dostępu sieci](/admin/docs/user/network-access-zones) — osobne listy CIDR dla panelu i Roundcube.

**Jak zainstalować aktualizacje?**
[Ustawienia → Aktualizacje systemu](/admin/docs/user/system-updates) — domyślnie tylko łatki bezpieczeństwa, z health-checkiem po instalacji.

**Serwer źródłowy ma self-signed certyfikat i synchronizacja pada — co zrobić?**
Domyślnie weryfikujemy certyfikat SSL źródła. Wyłącz weryfikację w [Ustawienia → Opcje imapsync](/admin/docs/user/imapsync-options) (globalnie) albo tylko dla tej skrzynki wpisując `--sslargs1 SSL_verify_mode=0` w jej dodatkowych flagach.

**Czy mogę dodać własne parametry imapsync (np. wykluczyć folder)?**
Tak — globalnie lub per skrzynka. Ze względów bezpieczeństwa przyjmowane są tylko flagi z listy bezpiecznych; nie da się dodać flagi kasującej cokolwiek na źródle. Szczegóły: [Opcje imapsync](/admin/docs/user/imapsync-options).

**Czy logo staje się też ikoną karty przeglądarki (favicon)?**
Tak — po wgraniu logo portal automatycznie generuje z niego favicon (i ikonę Apple), skalując do właściwych rozmiarów. Wystarczy wgrać logo w [Ustawieniach → Branding](/admin/settings/branding).

**Czy poczta jest skanowana antywirusem/pod kątem phishingu?**
Tak — na VM2 działają **ClamAV** (malware, makra, sygnatury SaneSecurity/URLhaus) i **rspamd** (phishing, podejrzane linki). Skan jest **post factum** (nie w locie), okresowy: przyrostowy (tylko nowa poczta) + pełny wg harmonogramu. Ustawisz go w [Ustawienia → Skanowanie poczty](/admin/docs/user/mail-scanning) (np. pełny raz w tygodniu albo wyłączony). Wykrycia widać na pulpicie i w [raportach](/admin/reports) (z tematem/nadawcą maila) oraz jako alert `av_threat_found`.

**Mogę podejrzeć log synchronizacji na żywo?**
Tak — na stronie skrzynki, przycisk **„👁 Podgląd na żywo"** pokazuje wyjście imapsync na bieżąco (gdy sync trwa). Jest też pełna historia przebiegów i surowe logi. Patrz [Monitorowanie synchronizacji](/admin/docs/user/monitoring-sync).

**Jak otworzyć skrzynkę w Roundcube bez znajomości hasła?**
Funkcja **„Otwórz w Roundcube"** (dostęp administracyjny) jest **domyślnie wyłączona** — włączasz ją w [Ustawienia → Otwórz w Roundcube](/admin/docs/user/open-in-roundcube). Po włączeniu, na stronie skrzynki pojawia się przycisk otwierający ją w webmailu od razu zalogowaną (audytowane, tylko z sieci admina).

**Jak dodać/usunąć/zablokować konto administratora? Co gdy zapomnę hasła?**
[Ustawienia → Użytkownicy](/admin/settings/users) — tworzenie, dezaktywacja/aktywacja, usuwanie, reset TOTP, zmiana własnego hasła. Zapomniane hasło resetujesz na konsoli VM1 (`sudo portal-admin-password.sh <login>`). Szczegóły: [Konta administratorów](/admin/docs/user/admin-accounts).

**Czy mogę zrestartować serwery z panelu i jak cofnąć nieudaną aktualizację?**
Aktualizacje idą w tle z podglądem postępu; jeśli wymagany jest restart — jest przycisk w panelu. **Przed** każdą aktualizacją robiona jest kopia konfiguracji, a na konsoli maszyny jest narzędzie ratunkowe (`portal-config-recovery.sh` / `vm2-config-recovery.sh`). Szczegóły: [Aktualizacje systemu](/admin/docs/user/system-updates).

**Jak ograniczyć zużycie łącza przez synchronizację?**
Ustaw **Limit łącza (Mbit/s)** w [Ustawienia → Opcje imapsync](/admin/docs/user/imapsync-options) (0 = bez limitu). Dotyczy pojedynczego przebiegu.
