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
