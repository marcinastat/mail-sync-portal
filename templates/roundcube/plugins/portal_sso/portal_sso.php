<?php

/**
 * portal_sso — jednorazowe logowanie do skrzynki z panelu /admin („Otwórz w
 * Roundcube") BEZ podawania hasła skrzynki.
 *
 * Przepływ: panel tworzy jednorazowy token (hash w portal_db.webmail_sso_tokens),
 * przekierowuje na /?_sso=<token>. Ta wtyczka:
 *   1) waliduje token (hash, TTL, jednorazowość — atomowe UPDATE ... RETURNING),
 *   2) sprawdza IP klienta wobec listy sieci ADMINA (allow z admin-access.conf),
 *   3) loguje jako MASTER USER Dovecota: <skrzynka>*<master> + hasło mastera,
 *      dzięki czemu admin widzi skrzynkę bez znajomości jej hasła.
 *
 * Bezpieczeństwo: token krótkożyjący i jednorazowy; wyzwalacz tylko spod /admin
 * (strefa admina); dodatkowo TU sprawdzamy IP admina (defense-in-depth, bo samo
 * lądowanie jest pod / = strefa webmaila). Każde otwarcie jest audytowane po
 * stronie panelu. Błąd na dowolnym etapie => zwykły ekran logowania (nie psujemy
 * normalnego Roundcube).
 */
class portal_sso extends rcube_plugin
{
    public $task = 'login|logout|mail|settings|addressbook';

    private $do_login = false;
    private $login_user = null;

    function init()
    {
        $this->add_hook('startup', array($this, 'startup'));
        $this->add_hook('authenticate', array($this, 'authenticate'));
    }

    function startup($args)
    {
        $rcmail = rcmail::get_instance();
        // Bez parametru _sso NIC nie zmieniamy — respektujemy istniejącą sesję
        // (zwykłe korzystanie z Roundcube działa normalnie).
        $token = rcube_utils::get_input_value('_sso', rcube_utils::INPUT_GET);
        if (empty($token)) {
            return $args;
        }

        try {
            $this->load_config();
            $mailbox = $this->consume_token($rcmail, $token);
            if ($mailbox === null) {
                return $args; // token nieważny/zużyty/wygasł -> zwykłe logowanie
            }
            if (!$this->ip_allowed($rcmail)) {
                rcube::write_log('portal_sso', 'Odrzucono SSO: IP spoza sieci admina (' . $this->client_ip() . ')');
                return $args;
            }
            // KLUCZOWE: token wskazuje KONKRETNĄ skrzynkę. Jeśli w tej przeglądarce
            // jest już otwarta INNA sesja (np. poprzednie „Otwórz w Roundcube"),
            // trzeba ją zabić i zalogować świeżo TĘ skrzynkę — inaczej Roundcube
            // pokazałby starą sesję i widziałbyś cudzą pocztę (bug).
            if (!empty($_SESSION['user_id'])) {
                $rcmail->kill_session();
            }
            $this->login_user = $mailbox;
            $this->do_login = true;
            $args['action'] = 'login';
        } catch (Exception $e) {
            rcube::write_log('portal_sso', 'Blad SSO: ' . $e->getMessage());
        }
        return $args;
    }

    function authenticate($args)
    {
        if ($this->do_login && $this->login_user) {
            $rcmail = rcmail::get_instance();
            $master = $rcmail->config->get('portal_sso_master_user');
            $pass = $rcmail->config->get('portal_sso_master_pass');
            // Login jako master user Dovecota: <skrzynka>*<master>.
            $args['user'] = $this->login_user . '*' . $master;
            $args['pass'] = $pass;
            $args['cookiecheck'] = false;
            $args['valid'] = true;
            rcube::write_log('portal_sso', 'SSO login jako ' . $this->login_user);
        }
        return $args;
    }

    /** Atomowo „zużywa" token: zwraca adres skrzynki albo null. */
    private function consume_token($rcmail, $token)
    {
        $dsn = $rcmail->config->get('portal_sso_dsn');
        $user = $rcmail->config->get('portal_sso_db_user');
        $pass = $rcmail->config->get('portal_sso_db_pass');
        $pdo = new PDO($dsn, $user, $pass, array(PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION));
        $hash = hash('sha256', $token);
        // UPDATE ... WHERE used_at IS NULL ... RETURNING => tylko JEDNO żądanie
        // może przestawić used_at z NULL (gwarancja jednorazowości bez wyścigu).
        $stmt = $pdo->prepare(
            "UPDATE webmail_sso_tokens SET used_at = now() " .
            "WHERE token_hash = :h AND used_at IS NULL AND expires_at > now() " .
            "RETURNING mailbox_address"
        );
        $stmt->execute(array(':h' => $hash));
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        return $row ? $row['mailbox_address'] : null;
    }

    private function client_ip()
    {
        // nginx podaje realne IP w X-Real-IP (proxy przez gniazdo/adres lokalny).
        if (!empty($_SERVER['HTTP_X_REAL_IP'])) {
            return trim($_SERVER['HTTP_X_REAL_IP']);
        }
        return isset($_SERVER['REMOTE_ADDR']) ? $_SERVER['REMOTE_ADDR'] : '';
    }

    /** IP klienta musi być w którejś z sieci admina (allow z admin-access.conf).
     *  Brak reguł = brak ograniczenia (spójnie z nginx). */
    private function ip_allowed($rcmail)
    {
        $file = $rcmail->config->get('portal_sso_admin_acl_file');
        if (empty($file) || !is_readable($file)) {
            return true; // brak pliku => strefa admina nie ogranicza => nie blokujemy
        }
        $cidrs = array();
        foreach (file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
            if (preg_match('/^\s*allow\s+([0-9a-fA-F:.\/]+)\s*;/', $line, $m)) {
                $cidrs[] = $m[1];
            }
        }
        if (empty($cidrs)) {
            return true; // sama „deny all" bez allow nie wystąpi tu sensownie; brak allow => nie ograniczamy
        }
        $ip = $this->client_ip();
        foreach ($cidrs as $cidr) {
            if ($this->cidr_match_v4($ip, $cidr)) {
                return true;
            }
        }
        return false;
    }

    private function cidr_match_v4($ip, $cidr)
    {
        if (strpos($cidr, '/') === false) {
            $cidr .= '/32';
        }
        list($subnet, $bits) = explode('/', $cidr, 2);
        $ipl = ip2long($ip);
        $subl = ip2long($subnet);
        if ($ipl === false || $subl === false) {
            return false; // nie IPv4 — bezpieczniej NIE dopasować
        }
        $bits = (int) $bits;
        if ($bits <= 0) {
            return true;
        }
        $mask = -1 << (32 - $bits);
        return ($ipl & $mask) === ($subl & $mask);
    }
}
