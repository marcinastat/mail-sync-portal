# Sieć i granice zaufania

```
[Podsieć admin/VPN, ADMIN_SUBNET_CIDR]
   |  443/tcp (HTTPS)   22/tcp (SSH)
   v
VM1 (portal)
   | 993/tcp (IMAPS), 587/tcp (submission), 8443/tcp (provisioning API) -> tylko do VM2_IP
   | 993/tcp wychodzące -> zewnętrzne serwery IMAP źródłowe
   v
VM2 (serwer poczty) — firewalld akceptuje 143/993/587/8443 WYŁĄCZNIE z VM1_IP
```

## Reguły firewalld

| Host | Port | Źródło | Cel |
|---|---|---|---|
| VM1 | 22, 443 | `ADMIN_SUBNET_CIDR` | SSH, panel/Roundcube |
| VM2 | 143, 993, 587 | `VM1_IP/32` | IMAP/IMAPS, submission SMTP (Roundcube) |
| VM2 | 8443 | `VM1_IP/32` | provisioning API (mTLS) |

Domyślna polityka na obu VM: `drop` (patrz `scripts/vm1/80-firewall-rules.sh`, `scripts/vm2/60-firewall-rules.sh`). Ruch wychodzący nie jest ograniczany przez firewalld (tylko INPUT/FORWARD).

## mTLS VM1 ↔ VM2

Lokalne CA generowane przez `scripts/lib/mtls.sh` (nigdy nie commitowane, katalog `ca/` w `.gitignore`). VM2 wystawia jeden certyfikat kliencki (`vm1-client`) — to jedyny podmiot, który TLS-owo może w ogóle nawiązać połączenie z provisioning API; adres IP jest dodatkową warstwą (obrona w głąb), nie jedynym zabezpieczeniem.

## Dlaczego VM2 nie jest osiągalna z podsieci admina

Jedynym punktem dostępu do danych pocztowych jest VM1 (Roundcube + silnik synchronizacji) — to świadomy wybór architektoniczny, nie przeoczenie. Ogranicza to powierzchnię ataku do jednej, dobrze audytowanej maszyny.
