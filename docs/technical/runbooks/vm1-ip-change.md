# Runbook: zmiana adresu IP VM1

VM2 (serwer poczty) wpuszcza ruch z portalu **wyłącznie z IP VM1**. Gdy VM1 dostanie nowy adres, VM2 odrzuca jej połączenia: pulpit pokazuje „brak połączenia z VM2”, synchronizacje padają (imapsync nie łączy się z host2), a Roundcube nie może się zalogować do skrzynek.

Poprawki robi się **na VM2**. VM1 sama tego nie naprawi, bo VM2 już jej nie wpuszcza.

## Gdzie VM2 trzyma adres VM1

| Miejsce (VM2) | Do czego służy | Co zrobić |
|---|---|---|
| firewalld, rich rules `source address='<IP VM1>/32'` na portach 143, 993, 587, 8443 | IMAP (imapsync, Roundcube), submission (Roundcube), provisioning API | dodać reguły dla nowego IP i **usunąć** reguły dla starego |
| unit `vm2-provisioning-api`, zmienna `VM2_API_ALLOWED_CLIENT_IP` | allowlista API (druga warstwa obok mTLS); inny adres dostaje `403` | wpisać nowe IP i zrestartować usługę |
| `config/install.conf` (`VM1_IP`) na **obu** VM | tylko przy ponownym uruchomieniu skryptów (`60-firewall-rules.sh`, `50-provisioning-api.sh`) | wpisać nowe IP |

Bez zmian zostaje:
- **certyfikat mTLS klienta VM1**: identyfikuje portal, a nie adres, więc nie zawiera IP;
- **certyfikat HTTPS panelu**: self-signed ma tylko `CN=VM1_HOSTNAME` (bez IP); certyfikat z DNS-01 lub wgrany ręcznie też jest wystawiony na nazwę;
- **Postfix na VM2**: `mynetworks` to tylko `127.0.0.0/8`;
- **strefy dostępu sieci** w panelu: dotyczą adresów **klientów** (przeglądarek), a nie samej VM1;
- **konfiguracja portalu** (`portal_db`): nie przechowuje własnego IP.

Ponowne uruchomienie `60-firewall-rules.sh` nie wystarczy: skrypt tylko **dodaje** reguły dla nowego IP i nie usuwa starych. Porty VM2 zostałyby otwarte dla maszyny, która w przyszłości dostanie stary adres VM1. Dlatego reguły podmienia się ręcznie, jak niżej.

## Procedura

### Na VM2 (root)

Zaloguj się po SSH ze stacji w podsieci administracyjnej (`ADMIN_SUBNET_CIDR`) albo z konsoli hypervisora.

```bash
OLD=10.0.0.10                 # dotychczasowe IP VM1
NEW=10.0.0.11                 # nowe IP VM1
cd /mail-sync-portal          # klon repo na VM2

# 1. install.conf: żeby kolejne uruchomienia skryptów miały dobre IP
sed -i "s/^VM1_IP=.*/VM1_IP=\"$NEW\"/" config/install.conf
source config/install.conf    # daje $VM2_API_PORT

# 2. firewalld: reguły dla nowego IP, usunięcie reguł starego
firewall-cmd --get-default-zone          # powinno być: drop
firewall-cmd --list-rich-rules           # stan przed
for p in 143 993 587 "$VM2_API_PORT"; do
  firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='${NEW}/32' port port='$p' protocol='tcp' accept"
  firewall-cmd --permanent --remove-rich-rule="rule family='ipv4' source address='${OLD}/32' port port='$p' protocol='tcp' accept"
done
firewall-cmd --reload
firewall-cmd --list-rich-rules           # stan po: porty 143/993/587/8443 tylko dla $NEW

# 3. Allowlista provisioning API
sed -i "s/^Environment=VM2_API_ALLOWED_CLIENT_IP=.*/Environment=VM2_API_ALLOWED_CLIENT_IP=$NEW/" \
    /etc/systemd/system/vm2-provisioning-api.service
systemctl daemon-reload
systemctl restart vm2-provisioning-api
systemctl show vm2-provisioning-api -p Environment | tr ' ' '\n' | grep ALLOWED_CLIENT_IP   # musi pokazać $NEW
```

Komunikaty `ALREADY_ENABLED` / `NOT_ENABLED` przy pętli są niegroźne: reguła już była dodana albo usunięta.

Unit jest zmieniany ręcznie (`sed`), więc przy następnym uruchomieniu `50-provisioning-api.sh` funkcja `render_template` zrobi kopię `.bak-<data>` i wypisze WARN. To normalne: plik zostanie wyrenderowany z `install.conf`, już z nowym IP.

### Na VM1 (root)

```bash
cd /mail-sync-portal
sed -i "s/^VM1_IP=.*/VM1_IP=\"10.0.0.11\"/" config/install.conf
source config/install.conf    # daje $VM2_HOSTNAME

# Test provisioning API (mTLS + allowlista IP)
curl -s -o /dev/null -w '%{http_code}\n' \
     --cert /etc/portal/vm1-client/client.crt --key /etc/portal/vm1-client/client.key \
     --cacert /etc/portal/vm1-client/ca.crt "https://$VM2_HOSTNAME:8443/health"

# Test portów IMAPS / submission (Minimal nie ma nc, wystarczy bash)
for p in 993 587; do timeout 5 bash -c "</dev/tcp/$VM2_HOSTNAME/$p" && echo "port $p OK"; done
```

Jak czytać wynik testu `/health`:

| Kod | Znaczenie | Co poprawić |
|---|---|---|
| `200` | wszystko działa | nic |
| `403` | firewall przepuszcza, ale API odrzuca adres | krok 3 (allowlista) na VM2 |
| `000` / timeout | firewall VM2 odrzuca ruch albo VM2 jest nieosiągalna | krok 2 (firewalld) na VM2, routing |

Restart usług na VM1 nie jest potrzebny.

## Weryfikacja w panelu

1. **Pulpit**: kafelek VM2 (dysk, skan poczty) znów pokazuje dane.
2. **Skrzynki**: na dowolnej skrzynce kliknij „Synchronizuj teraz” i sprawdź w podglądzie na żywo, że imapsync łączy się z host2.
3. **Roundcube**: logowanie na skrzynkę (lub „Otwórz w Roundcube”, jeśli włączone) działa.

Synchronizacje uruchomione między zmianą IP a poprawką na VM2 kończą się błędem. Widać je w **Raporty → Nieudane synchronizacje**. Następny cykl harmonogramu przejdzie normalnie; możesz też od razu kliknąć „Synchronizuj teraz”.

## Poza serwerami

- **Adres panelu**: administratorzy, którzy wchodzą na panel lub Roundcube po IP, muszą użyć nowego adresu. Jeśli wchodzą po nazwie (`VM1_HOSTNAME`), popraw rekord A w wewnętrznym DNS albo wpisy w `hosts` na stacjach.
- **Serwery źródłowe z allowlistą IP**: jeśli któryś dostawca poczty wpuszcza imapsync tylko z określonego adresu, a zmienił się też **publiczny** adres wyjściowy (NAT), trzeba go zgłosić dostawcy. Sama zmiana adresu wewnętrznego VM1 ich nie dotyczy.

## Zmiana planowana (bez przestoju firewalla)

Jeśli zmianę IP znasz z wyprzedzeniem:
1. **Przed** zmianą: na VM2 dodaj tylko reguły firewalld dla nowego IP (krok 2 bez `--remove-rich-rule`). Przez chwilę oba adresy są wpuszczane.
2. Zmień IP VM1.
3. Na VM2 wykonaj krok 3 (allowlista przyjmuje jeden adres, więc dopiero teraz) i usuń reguły starego IP.

Przerwa w API trwa wtedy tylko między zmianą adresu a restartem `vm2-provisioning-api`.

## Typowe problemy

- **Nowe IP VM1 jest poza `ADMIN_SUBNET_CIDR`**: panel działa (mTLS idzie przez reguły z kroku 2), ale VM1 nie połączy się z VM2 po SSH, bo SSH na VM2 jest wpuszczany tylko z podsieci administracyjnej. Przestaną wtedy działać `sync-to-vm2.sh`, `fetch-vm2-client-cert.sh` i pobieranie hasła master w `55-webmail-sso.sh`. Rozwiązanie: VM1 w podsieci admina albo dodatkowa reguła SSH na VM2 dla nowego IP.
- **Zmieniła się cała podsieć (także stacje administratorów)**: to szersza zmiana. Trzeba poprawić `ADMIN_SUBNET_CIDR` w `install.conf` obu VM i reguły SSH/HTTPS w firewalld (`scripts/vm1/80-firewall-rules.sh`, `scripts/vm2/60-firewall-rules.sh`; stare reguły też usunąć ręcznie). Uważaj na odcięcie się od SSH: najpierw dodaj nowe reguły, sprawdź połączenie, dopiero potem usuń stare. Sprawdź też strefy dostępu w panelu (Ustawienia → Strefy dostępu sieci).
- **Zmieniło się IP VM2, a nie VM1**: zobacz [Runbook: zmiana adresu IP VM2](/admin/docs/technical/runbooks/vm2-ip-change).

## Zapobieganie

Daj VM1 stały adres: statyczną konfigurację w systemie albo rezerwację DHCP w routerze (powiązanie z adresem MAC karty sieciowej VM).
