# Balkona Telegram: vienkāršāka Home Assistant integrācija (source only, #1490)

## Lēmums

**Mērķis:** Home Assistant `Telegram bot` + `MQTT` integrācijas, nevis
atsevišķs RPi5 Python Telegram↔MQTT starpnieks un papildu root operatori.
Tas ilgtermiņā samazina uzturamo servisu, kredenciāļu izplatīšanu, savienojumu
un atjaunināšanas mehānismu skaitu. Tas **nav** pierādījums, ka tūlītēja
migrācija ir droša vai saglabā visas esošās komandas.

Pieņemtais GitHub avots: `RPi5_main/main@365973490fb98f8395ca45538eca061fc12d1a28`.
Reālā Home Assistant konfigurācija un Telegram integrācijas klātbūtne NAV
pārbaudīta; līdz atsevišķai LIVE autorizācijai pašreizējais RPi5
`balkons-bot.service` paliek neaiztikts.

### Oficiālā dokumentācija — HA 2026.11

- Telegram bot: https://www.home-assistant.io/integrations/telegram_bot/
  (Broadcast = tikai sūtīšana; Polling = saņemšana bez publiska HA endpointa;
  Webhooks = vajadzīga publiska HTTPS sasniedzamība).
- Telegram native actions: https://www.home-assistant.io/actions/telegram_bot.send_message/
- MQTT trigger: https://www.home-assistant.io/triggers/mqtt/
- MQTT publish action: https://www.home-assistant.io/actions/mqtt.publish/
- HA 2026.11 breaking change: https://www.home-assistant.io/blog/2026/11/04/release-202611/
  (novecojusī `notify` Telegram YAML platforma / `notify.<name>` darbības
  ir noņemtas; jālieto jauno Telegram bot integrācijas notify entītiju
  `notify.send_message` vai `telegram_bot.send_message`).

## Mērķa arhitektūra (pēc atsevišķi autorizēta un pārbaudīta cutover)

```text
ESP32/MQTT -> balkons/telegram_out -> HA MQTT trigger -> Telegram bot.send_message
Telegram /command -> HA Telegram Polling event entity -> authorized command policy
                                       |
                             HA MQTT publish -> balkons/cmd
                                       |
                          ESP32 drošības un sūkņa failsafe
```

**Svarīgi:** otrā rindiņa ir nākotnes mērķis, nevis pašreiz droši
izpildāma automātika. `balkons/cmd` ir aktuatora vadības topics:
jebkura publikācija ir atsevišķi autorizējama LIVE darbība.

## Sākuma stāvokļa komandu invarianti (no koda, nevis no live ierīces)

Pašreizējais `ops/lib/balkons-bot.py` pieņem tikai atļautas tērzētavas
ziņojumus un nodrošina:

| Komanda | Tagad | Native HA pārņemšanas nosacījums |
|---|---|---|
| `/start` | Vietēja palīdzības atbilde | Paziņojums bez MQTT aktuatora komandas |
| `/mitrums` | `balkons/cmd=mitrums` | Pārbaudīt precīzu ESP32 komandas semantiku |
| `/statuss` | `balkons/cmd=statuss` | Pārbaudīt statusa/ACK maršrutu |
| `/raw` | `balkons/cmd=raw` | Tikai pēc drošas datu atgriešanas pārbaudes |
| `/stop` | Tieša `balkons/cmd=stop` | **Drošs emergency stop nedrīkst pazust migrācijā** |
| `/laist`, `/laist_*` | Pēc stingras RPi5 `manual-safety-v1.json` pārbaudes | **DENY**, kamēr nav līdzvērtīga svaiguma/sala/sensoru/dienas limita gate |
| Cits teksts | Vietēja palīdzība | Neizpildīt kā komandu |

Esošā manuālā laistīšana neveic publikāciju, ja drošības stāvoklis
nav pieejams, nederīgs vai novecojis (>6 h), `decision != manual_permit`,
`frost_blocked` ir patiess, `sensor_coverage_ok` ir aplams,
`sensor_total != 10`, vai šodien jau laistīts. Neko no tā nedrīkst
vienkāršot līdz vienam nekontrolētam `mqtt.publish` izsaukumam. RPi5
11:00 rudens kontroliera nomaiņa ir **atsevišķs** īpašnieka LIVE lēmums.

## 1. posms — native MQTT → Telegram paziņojumi (sagatavots avotā)

`ops/homeassistant/balkons-telegram-native-notify.yaml` ir **viens
atspējots, opt-in automatizācijas paraugs**, kas:

- Klausās **tikai** `balkons/telegram_out` un nosūta tekstu ar
  `telegram_bot.send_message`, `parse_mode: plain_text`.
- Pieņem tikai netukšu un līdz 1024 zīmēm garu paziņojumu; uzlikts
  `mode: queued` ar ierobežotu rindu.
- Apzināti satur `initial_state: false` un
  `notify.replace_with_approved_telegram_chat` placeholder. Neviena
  tērzētava netiek automātiski minēta; īpašniekam jāpiesaista **precīza
  atļautā Telegram notify entītija** pēc HA evidence. Kamēr placeholder
  nav pārskatīts, šo paraugu nedrīkst aktivizēt.
- **Nesatur** `mqtt.publish`, `balkons/cmd` vadību, Telegram tokenu,
  REST pieprasījumus, skriptus vai sensoru stāvokļa izmaiņas.
- Netiek automātiski importēts HA konfigurācijā: GitHub merge to
  neinstalē, neieslēdz un neatsāk nevienu servisu.

Nākotnē, ar atsevišķu precīzu īpašnieka LIVE autorizāciju:

1. Sanitizēts, read-only HA preflight: HA versija, MQTT integrācijas
   esamība/pieslēgums, Telegram bot integrācijas tips, notify entītiju
   skaits/ID **bez tokeniem, čata ID, privātās konfigurācijas**; pārbaudīt
   aktuālo RPi5 botu un Hermes notifikāciju ceļu atsevišķi.
2. Ja vajag, atsevišķā LIVE solī konfigurēt native Telegram bot
   **Broadcast** (tikai sūtīšanai) ar HA paša drošo konfigurācijas UI;
   tas neprasa Telegram `getUpdates` un nekonfliktē ar esošo
   RPi5 `Polling`. Tas nepierāda, ka nav dublētu paziņojumu.
3. Pēc precīzas notify entītijas pārbaudes izmēģināt **vienu**
   autorizētu, nekaitīgu Telegram paziņojumu; redzēt to paredzētajā
   čatā. HTTP/API `ok=1` pats par sevi nav piegādes pierādījums.
4. **Neieslēgt** native MQTT notifikāciju automātiku paralēli
   esošajai RPi5 `balkons/telegram_out` pārsūtīšanai: citādi var
   pienākt dubultas ziņas. Abonenta pārslēgšanu veikt tikai kopā ar
   drošu 2. posma komandu migrāciju vai neatkarīgi pārbaudītu
   atomāru no-subscription variantu. Nav automātiska rollback.

## 2. posms — ienākošās komandas (vēl NAV izpildāms)

Oficiālā HA Telegram bot integrācija izveido **event entity**; komandas
saņem ar tās `state` trigger + `event_type=telegram_command` un
`trigger.to_state.attributes.command`; neizmantot novecojušu
`notify.telegram` konfigurāciju. Faktiskais event entity ID un chat
allowlist ir jāiegūst no reālas HA read-only pārbaudes. Pirms LIVE:

- Pārbaudīt konkrēto `chat_id` / `user_id` allowlist tikai HA
  aizsargātā konfigurācijā; neatklāt publiskā repo vai žurnālos.
- Precīzi testēt `/start`, `/mitrums`, `/statuss`, `/raw`,
  `/stop`, `/laist` un `/laist_2` ar offline atbildēm; 
  nepublicēt `balkons/cmd` nevienā source-only testā.
- Izveidot HA pieejamu, verificējamu un **fail-closed** drošības gate,
  kas nemaina sensoru/sala/vienas dienas policy un noraida trūkstošu
  vai vecu drošības stāvokli. Pašreizējais RPi5 fails nav HA entītija
  tikai tādēļ, ka tas ir pieminēts GitHub kodā.
- Pārbaudīt, ka `/stop` ir ātri un droši pieejams arī pārejas laikā;
  MQTT ACK/aktuatora semantika jāapstiprina no ESP32, nevis jāmin.
- **Nedarbināt divus Telegram Polling/getUpdates klientus ar vienu
  bot tokenu**. HA Polling drīkst ieslēgt tikai pēc atsevišķi
  autorizēta vecā pollera apturēšanas un pilna, pierādīta komandu
  cutover plāna. Neapturēt botu tikai tāpēc, ka paziņojumi strādā.
- Pēc pilnas paritātes pierādījumiem un atsevišķas owner LIVE
  atļaujas var izņemt vecā RPi5 bota runtime/servisa atkarību.
  Nekādas automātiskas servisu apturēšanas, restartēšanas, tokenu
  kopēšanas, konfigurācijas maiņas vai reversu komandu.

## Pārbaudes un pašreizējie secinājumi

`tests/test-balkons-ha-native-telegram.py` ir tikai Python stdlib offline
tests. Tie pārbauda deaktivizēto native konfigurāciju, pareizo
MQTT topic/saņēmēja placeholder/parse mode, papildus darbību neesamību,
nesankcionēta ieslēgšanas mēģinājuma bloķēšanu un esošā manuālās
laistīšanas drošības gate saglabāšanu **GitHub kodā**.

Šie testi nepierāda reālās HA instalācijas versiju vai Telegram integrācijas
esamību. RPi5 nav mainīts. **READY SOURCE** nozīmē vienīgi gatavu
pārskatāmu migrācijas avotu, nevis atļauju to lietot production.


## #1521 — MQTT paziņojumu pārsūtīšanas atdalīšana (tikai GitHub avots)

`ops/lib/balkons-bot.py` tagad paredz atsevišķu `BALKONS_MQTT_TELEGRAM_FORWARD`
slēdzi. Ja vide nav konfigurēta vai vērtība ir precīzi `1`, darbojas
pašreizējais pārsūtīšanas režīms. Tikai `0` ir paredzētā atspējošanas
vērtība; jebkura cita neparedzēta vērtība **nepārsūta** MQTT paziņojumus
(fail-closed pret dublikātiem). Kad pārsūtīšana nav atļauta, bots
**neabonē** `balkons/telegram_out` un arī neapstrādā negaidīti saņemtu
MQTT paziņojumu. Saņemtās Telegram komandas, `/stop`, manuālās
laistīšanas drošības pārbaude un `balkons/cmd` nav mainīti.

Šis ir **source-only** slēdzis. GitHub merge to neinstalē un nepārslēdz
esošu servisu. Pašreizējais HA `Balkona Laistīšana` Broadcast serviss
ir redzēts HA UI ar vienu entītiju, taču reālais Telegram saņēmējs un
piegāde nav neatkarīgi pierādīti. Neaktivizēt otro MQTT patērētāju
paralēli esošajai RPi5 pārsūtīšanai.

### Viena nākotnes, atsevišķi autorizējama LIVE pārslēgšana

1. **READONLY preflight:** identificēt precīzu HA `notify` entītiju,
   atļauto Telegram sarunu, HA MQTT savienojumu un esošo automatizāciju
   stāvokļus bez tokenu, chat ID vai privātās konfigurācijas kopēšanas.
   Pārbaudīt `balkons-bot.service` versiju, aktīvo abonementu,
   `/stop` komandas ceļu un iepriekš sagatavoto instalācijas
   mehānismu. Nepieņemt, ka avota merge ir runtime izmaiņa.
2. **Tikai ar atsevišķu precīzu COMPOSITE STRICT LIVE atļauju:**
   droši uzstādīt pārskatīto bota avotu un iestatīt
   `BALKONS_MQTT_TELEGRAM_FORWARD=0` tā servisa vidē. Tam var būt
   vajadzīgs servisa restarts, kas uz brīdi pārtrauc komandu saņemšanu:
   **neveikt**, ja pirms tam nav neatkarīgi nodrošināts drošs
   `/stop` ceļš un apstiprināts pieļaujamais pārtraukums.
   Pārbaudīt, ka botam vairs nav MQTT paziņojumu abonementa, bet
   Telegram komandu saņemšana un vadības drošības gate strādā.
3. Tikai pēc vecā pārsūtītāja izslēgšanas un komandu pārbaudes piesaistīt
   jau sagatavotajai *vienai* HA automatizācijai precīzu atļauto
   `notify` entītiju un aktivizēt to. Neizmantot otru `Polling`
   klientu. Ja ekskluzivitāte vai `/stop` nav pierādīta, **STOP**.
   Pārslēgšanas secība novērš divus vienlaicīgus sūtītājus, bet
   negarantē bezpārtraukuma paziņojumu piegādi pārejas logā.
4. Atsevišķi autorizēt ne vairāk kā vienu nekaitīgu paziņojumu
   `balkons/telegram_out` (`qos=0`, `retain=false`) un pārbaudīt
   cilvēka redzamo saņemšanu pareizajā Telegram sarunā. Bez
   automātiska retry, rollback vai cleanup. 11:00 Hermes kontrolieris,
   12 sensoru drošības loģika un sūknis nav šīs pārslēgšanas sastāvdaļa.

Nedz šis avots, nedz #1521 pilnais source darbs neautorizē HA/RPi5
runtime darbības, Telegram/MQTT sūtīšanu vai aktuatoru komandas.

## #1523 — Minimālais RPi5 paziņojumu pārslēgšanas drop-in (tikai avots)

Avotā sagatavots `ops/systemd/balkons-bot-telegram-forward-off.conf` — **tikai**
`Environment=BALKONS_MQTT_TELEGRAM_FORWARD=0` zem `[Service]`.
Mērķis pēc atsevišķas LIVE atļaujas:
`/etc/systemd/system/balkons-bot.service.d/96-balkons-telegram-forward-off.conf`.
Šis fails tiek apstrādāts pēc esošā `95-rpi5-source-credentials.conf`;
tas **nemaina** šifrēto credentials overlay, bot tokenu, polleri vai
`balkons/cmd`. GitHub merge neinstalē ne drop-in, ne Python kodu.

**Pirms jebkādas RPi5 pārstartēšanas obligāti:**

1. Sanitizēts, atsevišķi autorizēts READONLY pārbaudījums: faktiskais
   instalētais bota public source hash, servisa `active`/PID metadata,
   `systemd` drop-in nosaukumi/precedence, precīzais paredzētais
   `BALKONS_MQTT_TELEGRAM_FORWARD` statuss, HA MQTT connection,
   automatizācijas disabled stāvoklis. Bez raw systemd/HA konfigurācijas,
   env dump, credential satura vai tokeniem. Lokālais Git checkout
   nav automātiski `origin/main`; vajadzīgs atsevišķs, autorizēts
   clean `git fetch` + `merge --ff-only` un exact Git SHA preflight.
2. **Neatkarīgs ārkārtas `stop` ceļš** bez RPi5 Telegram pollera,
   piemēram, no īpašniekam pieejamā HA UI uz precīzo `balkons/cmd=stop`
   (`retain=false`). Šī publikācija ir **fiziskas vadības LIVE
   mutation**, nevis nekaitīgs smoke tests. Tikai pēc atsevišķas
   konkrētas owner LIVE atļaujas un ESP32 apturēšanas semantikas,
   aktuālas MQTT sasniedzamības un neatkarīgas ACK/ierīces drošības
   verifikācijas drīkst uzskatīt rezervi par pierādītu. GitHub avots
   nevar pierādīt ierīces reālo stāvokli. Ja pierādījuma nav, BLOCKED.
3. Pārbaudīt, vai vēsturiskais #1484 one-shot Python atjaunināšanas
   operators **patiesi** atbilst uzstādītā faila SHA, atļaujas receipt
   un recovery preconditions. Ja nē — to **neizmantot atkārtoti**;
   vajadzīgs atsevišķi pārskatīts, precīzi owner-autorizēts
   public-source + drop-in instalācijas ceļš. Nedrīkst uzskatīt,
   ka operatora esamība nozīmē, ka tas ir piemērots.

**Nākotnes atļautā secība (neizpildīt no šī avota):** pēc drošās
`stop` rezerves un dīkstāves pieļaujamības apliecināšanas, vienas
precīzas Composite STRICT LIVE atļaujas ietvaros pārbaudīt clean source
SHA un instalētos hash, uzstādīt pārskatīto bot Python avotu un **vienu**
drop-in ar tikai šo mainīgo; `systemctl daemon-reload` un **vienu**
`balkons-bot.service` restartu tikai tad, ja visi preconditions izpildīti.
Pēc tam pārbaudīt reālo environment vērtību sanitizēti, MQTT
notification SUBACK **neesamību** jaunajai paaudzei, saglabātu bot
komandu polling/`/stop` un aizliegto `/laist*` gate.
`No SUBACK` viens pats nav ekskluzivitātes pierādījums; jāpierāda
arī faktiska neabonēšana un ne-forwarding. Ja rodas neskaidrība
pēc pirmās mutation, STOP bez automātiska retry, rollback vai cleanup.

Tikai **pēc** pierādītas vecā paziņojumu pārsūtītāja atspējošanas drīkst
atsevišķi owner-autorizēti piesaistīt precīzo HA notify entītiju un
ieslēgt **vienu** HA MQTT→Telegram automatizāciju. HA Broadcast
neizveido otru `getUpdates` polleri. Pārejas logā iespējams
paziņojumu iztrūkums, bet nekad nedrīkst apzināti atstāt divus
aktīvus pārsūtītājus. Neviens šeit aprakstītais solis nav LIVE atļauja;
11:00 Hermes, sūkņa un sensoru drošības politika netiek mainīta.

Oficiālais `systemd` pamatojums: `systemd.unit(5)` drop-in faili
tiek apstrādāti leksikogrāfiskā secībā, `systemd.exec(5)`
vēlāks `Environment=` uzstādījums aizstāj agrāku; pirms LIVE tik
un tā ir vajadzīga konkrētās vienības precedence pārbaude.
