# Balkona Telegram: vienkāršāka Home Assistant integrācija (source only, #1490)

**Pašreizējais vienkāršotais aizstāšanas lēmums:** skatīt apakšā sadaļu
**AKTUĀLAIS LĒMUMS — #1523**. Agrākā #1490/#1521 komandu
migrācija un #1521 opt-out apraksta vēsturiskos variantus.

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
  `notify.andris` saņēmēju (tikai pēc atkārtotas LIVE pārbaudes). Neviena
  tērzētava netiek automātiski minēta; īpašniekam jāpiesaista **precīza
  atļautā Telegram notify entītija** pēc HA evidence. Kamēr saņēmējs nav revalidēts,
  šo paraugu nedrīkst aktivizēt.
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

## AKTUĀLAIS LĒMUMS — #1523: vienkārša aizstāšana (2026-11-18)

Iepriekš aprakstītie #1490/#1521 divposmu migrācijas un paziņojumu
`BALKONS_MQTT_TELEGRAM_FORWARD=0` drop-in varianti ir **vēsturiski**.
Īpašnieks izvēlējās vienu vienkāršu ceļu:

**RPi5 `balkons-bot.service` pilnībā izslēgt, pēc tam ieslēgt vienu
Home Assistant MQTT→Telegram Broadcast automatizāciju.** Nekāds
Python bota atjauninājums, otrs polleris, pakalpojuma pārrakstīšana,
drošības slēdža drop-in vai paralēla darbība nav nepieciešama.

Šis ir tikai **paziņojumu** ceļš. Pēc bota izslēgšanas Telegram
`/stop`, `/laist`, `/laist_2`, `/mitrums`, `/statuss`,
`/raw` un `/start` **vairs nav pieejamas**. HA Broadcast
komandas nesaņem un neaizstāj aktuatoru vadību. Pirms LIVE izslēgšanas
īpašniekam jābūt neatkarīgam veidam, kā apturēt laistīšanu — bez vecā
Telegram bota (piemēram, fiziska piekļuve vai atsevišķi verificēts
HA MQTT `stop` ceļš). Ja nav iespējams apturēt sūkni, **neizslēgt**
vadības botu. Nedrīkst pieņemt sūkņa stāvokli no GitHub koda.

### Viena nākotnes LIVE pārslēgšana — nav šeit autorizēta

1. **Sanitizēts read-only preflight.** Pārbaudīt HA MQTT savienojumu,
   Broadcast saņēmēju `notify.andris` (tā vienreizējais Telegram tests
   jau bija veiksmīgs, bet konfigurācija pirms LIVE jāpārbauda no jauna),
   un ka otrā HA MQTT→Telegram automatizācija nav ieslēgta.
   Pārbaudīt `balkons-bot.service` lifecycle metadata, neatklājot
   tokenus/privātu konfigurāciju. Pārbaudīt neatkarīgo sūkņa
   apturēšanas iespēju; bez tās **BLOCKED**.
2. **Sagatavot HA automatizāciju izslēgtu** ar precīzo
   `ops/homeassistant/balkons-telegram-native-notify.yaml` paraugu.
   Tā joprojām ir GitHub atsauce, nevis live HA instalācija.
   HA UI instalācijā nodrošināt, ka automātika ir OFF līdz 3. solim;
   noņemt parauga `initial_state: false` pirms saglabāšanas, lai
   pēc atkārtotas HA palaišanas ieslēgts statuss tiktu atjaunots.
3. **Tikai ar jaunu precīzu Composite STRICT LIVE atļauju** RPi5
   izpildīt vienu `systemctl disable --now balkons-bot.service`,
   pēc tam read-only pārbaudīt `inactive` un `disabled`.
   **Neatinstalēt** šifrētos credentials, servisa failus vai Python kodu.
   Vecais Telegram komandu polleris pēc izslēgšanas vairs nav pieejams.
   Ja rezultāts ir neskaidrs: STOP, bez automātiska retry/rollback.
4. **Tikai pēc vecā servisa izslēgšanas** ar atsevišķi precīzi
   autorizētu HA UI darbību ieslēgt **vienu** MQTT→
   `telegram_bot.send_message` automatizāciju ar tēmu
   `balkons/telegram_out`, adresātu `notify.andris`, 
   `parse_mode: plain_text`. Pārbaudīt tās `on` stāvokli.
   Pārejā iespējams īss paziņojumu iztrūkums; **nav paralēlu sūtītāju**.
   Jebkurš tests, kas publicē MQTT, pat nekaitīgu paziņojumu, prasa
   atsevišķu LIVE autorizāciju. Cilvēka redzētais Telegram paziņojums
   ir gala piegādes pierādījums.

Nedz `#1523` avota PR merge, nedz šī dokumentācija **nedod**
LIVE tiesības uz RPi5/HA, sūkni, MQTT komandu vai Hermes kontrolieri.
Esošie 11:00 laistīšanas noteikumi paliek neskarti.

Dokumentācijas pamatojums: https://www.home-assistant.io/integrations/telegram_bot/ ,
https://www.home-assistant.io/triggers/mqtt/ ,
https://www.home-assistant.io/actions/telegram_bot.send_message/ ,
https://www.home-assistant.io/docs/automation/yaml/ .
