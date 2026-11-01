# Runbook: zmiana adresu IP VM2

Gdy VM2 (serwer poczty) dostanie nowy adres IP (np. z DHCP po restarcie hypervisora), VM1 traci z nią połączenie: pulpit pokazuje „brak połączenia z VM2", synchronizacje padają, a Roundcube nie może się zalogować do skrzynek.

Najprościej wrócić do pracy, przełączając portal na łączenie się z VM2 **po nazwie hosta** (`VM2_HOSTNAME`), którą VM1 rozwiązuje przez `/etc/hosts`. Nie trzeba wtedy wystawiać nowego certyfikatu na VM2, a przy kolejnej zmianie IP wystarczy poprawić jedną linię w `/etc/hosts`.

## Gdzie VM1 trzyma adres VM2

| Miejsce | Do czego służy | Co zrobić |
|---|---|---|
| `portal_db`, tabela `vm2_connection`, kolumna `vm2_host` | provisioning API (mTLS, port 8443) i synchronizacja imapsync (`--host2`) | ustawić na `VM2_HOSTNAME` |
| `/etc/hosts` na VM1 (`<IP>  <VM2_HOSTNAME>`) | Roundcube (IMAP/SMTP po nazwie hosta) i, po zmianie, również API i imapsync | wpisać nowe IP |
| `config/install.conf` (`VM2_IP`) na **obu** VM | tylko przy ponownym uruchomieniu skryptów instalacyjnych | wpisać nowe IP |

`install.conf` trzeba poprawić, mimo że działające usługi z niego nie czytają: `scripts/vm1/40-roundcube.sh` przepisuje wpis w `/etc/hosts` z wartości `VM2_IP`, więc przy następnym uruchomieniu skryptów wróciłoby stare IP.

Bez zmian zostaje:
- **firewall VM2**: reguły wpuszczają ruch z IP **VM1**, a ono się nie zmieniło;
- **certyfikat Dovecota**: imapsync i Roundcube nie weryfikują certyfikatu IMAP VM2 (self-signed);
- **CA i certyfikat kliencki VM1**.

## Dlaczego po nazwie hosta, a nie po nowym IP

Certyfikat serwera provisioning API na VM2 ma w SAN **nazwę hosta i IP z chwili wystawienia**. Połączenie z nowym IP padnie na weryfikacji (`no alternative certificate subject name matches`), ale połączenie po nazwie hosta przejdzie, bo nazwa w SAN jest stała.

## Procedura (wariant zalecany, tylko VM1)

Na **VM1** jako root (w klonie repo):

```bash
NEW=10.0.0.21                 # nowe IP VM2
cd /mail-sync-portal          # klon repo na VM1

# 1. install.conf: żeby kolejne uruchomienia skryptów miały dobre IP
sed -i "s/^VM2_IP=.*/VM2_IP=\"$NEW\"/" config/install.conf
source config/install.conf    # daje $VM2_HOSTNAME

# 2. /etc/hosts: rozwiązywanie nazwy VM2 (Roundcube, API, imapsync)
sed -i "/[[:space:]]${VM2_HOSTNAME}\$/d" /etc/hosts
echo "$NEW    $VM2_HOSTNAME" >> /etc/hosts

# 3. Portal łączy się po nazwie hosta (jest w SAN certyfikatu VM2)
sudo -u postgres psql -d portal_db -tAc "SELECT vm2_host FROM vm2_connection;"   # obecna wartość
sudo -u postgres psql -d portal_db -c "UPDATE vm2_connection SET vm2_host='$VM2_HOSTNAME';"

# 4. Test mTLS do provisioning API
curl -s --cert /etc/portal/vm1-client/client.crt --key /etc/portal/vm1-client/client.key \
     --cacert /etc/portal/vm1-client/ca.crt "https://$VM2_HOSTNAME:8443/health"
```

Test powinien zwrócić status `healthy`. Panel czyta `vm2_connection` przy każdym żądaniu, a worker przy każdym zadaniu, więc **restart usług nie jest potrzebny**.

Jeśli `vm2_host` już wcześniej zawierał nazwę hosta, krok 3 niczego nie zmienia i wystarczy sam `/etc/hosts`.

Na **VM2** jako root popraw tylko `install.conf` (dla przyszłych uruchomień `50-provisioning-api.sh`, który wpisuje `VM2_IP` do SAN certyfikatu):

```bash
sed -i 's/^VM2_IP=.*/VM2_IP="10.0.0.21"/' /mail-sync-portal/config/install.conf
```

## Weryfikacja w panelu

1. **Pulpit**: kafelek VM2 (dysk, skan poczty) znów pokazuje dane.
2. **Skrzynki**: na dowolnej skrzynce kliknij „Synchronizuj teraz” i sprawdź w podglądzie na żywo, że imapsync łączy się z host2.
3. **Roundcube**: logowanie na skrzynkę (lub „Otwórz w Roundcube”, jeśli włączone) działa.

## Wariant alternatywny: zostać przy łączeniu po IP

Jeśli `vm2_host` ma dalej zawierać IP, trzeba wystawić na VM2 nowy certyfikat serwera z nowym IP w SAN:

```bash
# VM2, root, po poprawieniu VM2_IP w install.conf
cd /mail-sync-portal
FORCE_REAPPLY=1 bash scripts/vm2/50-provisioning-api.sh
```

CA zostaje to samo (skrypt go nie regeneruje), więc certyfikat kliencki VM1 dalej jest ważny i **nie trzeba** go ponownie pobierać. Następnie na VM1: kroki 1–2 jak wyżej oraz `UPDATE vm2_connection SET vm2_host='<nowe IP>';`.

## Typowe problemy

- **`curl: (60) ... no alternative certificate subject name matches`**: łączysz się po IP, a certyfikat VM2 ma stare IP. Użyj nazwy hosta (wariant zalecany) albo wystaw nowy certyfikat (wariant alternatywny).
- **Timeout przy `curl` / `Connection refused`**: sprawdź, czy VM2 w ogóle odpowiada pod nowym adresem (`ping`, `nc -zv <IP> 8443`) i czy działa `vm2-provisioning-api` (`systemctl status vm2-provisioning-api` na VM2).
- **Roundcube: „Connection to storage server failed”**: stary wpis w `/etc/hosts` na VM1. Sprawdź `getent hosts <VM2_HOSTNAME>`.
- **SSH z VM1 na VM2 (`sync-to-vm2.sh`, `fetch-vm2-client-cert.sh`) ostrzega o zmienionym kluczu hosta**: nowe IP było wcześniej używane przez inną maszynę. Usuń stary wpis: `ssh-keygen -R <nowe IP>`.
- **Zmieniło się też IP VM1**: to inna sytuacja, której ten runbook nie obejmuje. Na VM2 trzeba wtedy zaktualizować reguły firewalld (`scripts/vm2/60-firewall-rules.sh`) oraz allowlistę API (`VM2_API_ALLOWED_CLIENT_IP` w unicie `vm2-provisioning-api`, renderowanym z `VM1_IP`).

## Zapobieganie

Daj VM2 stały adres: statyczną konfigurację w systemie albo rezerwację DHCP w routerze (powiązanie z adresem MAC karty sieciowej VM).
