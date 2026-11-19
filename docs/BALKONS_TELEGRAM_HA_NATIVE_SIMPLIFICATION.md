# Balkona Telegram: vienkāršāka Home Assistant integrācija (source only, #1490)

**AKTUĀLAIS 2026-11-18:** šo dokumentu lasa kopā ar pēdējo
nodaļu “AKTUĀLĀ PĀRSLĒGŠANA — #1523 + #1525”. Vēsturiskie
Broadcast-only un #1490/#1521 2 posmu plāni nav izpildāmas
instrukcijas. Šobrīd mērķis ir saglabāt Telegram komandas caur
vienu HA Polling integrāciju; `/laist*` paliek bloķēta.

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

## AKTUĀLĀ PĀRSLĒGŠANA — #1523 + #1525: HA Polling ar komandām (2026-11-18)

**Šī nodaļa aizstāj iepriekšējās Broadcast-only bota izslēgšanas
instrukcijas un vēsturiskās #1490/#1521 alternatīvas.** Atsevišķi
paziņojumu un komandu avota faili ir VIENA paredzētā HA Telegram
migrācija, nevis divas konkurējošas Telegram integrācijas.

### Gala funkcionalitāte un atļaujas

- Ienākošās komandas jau sagatavotas `RPi5_main/main` pēc
  [PR #1526](https://github.com/rozkalnsandris/RPi5_main/pull/1526):
  `ops/homeassistant/balkons-telegram-polling-commands.yaml`.
  Tā ir **atspējota**, ar privāti aizstājamām `event`, `chat_id` un
  `user_id` vērtībām. `/stop` -> `balkons/cmd=stop`;
  `/mitrums`, `/statuss` un `/raw` sūta fiksētus diagnostikas
  pieprasījumus; `/start` izsūta palīdzību.
- Izejošajiem paziņojumiem izmanto `ops/homeassistant/balkons-telegram-native-notify.yaml`:
  precīza MQTT tēma `balkons/telegram_out`, viena
  `telegram_bot.send_message` darbība, `notify.andris`,
  `initial_state: false`, bez MQTT komandu publicēšanas.
- `/laist` un visas `/laist_*` komandas ir **DENY**, nevis
  iepriekšējā bota manuālās laistīšanas funkcijas atjaunošana.
  HA vēl nav verificēta līdzvērtīga RPi5 `manual-safety-v1.json`
  sensoru/sala/svaiguma/dienas limita pārbaude.
- Paredzēts **viens atļautais Polling saņēmējs konkrētam bot tokenam**
  pēc vecā RPi5 `getUpdates` pollera izslēgšanas. Vienas HA Telegram
  Polling integrācijas notify entītijas var nosūtīt izejošās ziņas;
  Broadcast-only režīms komandas nesaņem. **Nepievienot** otru
  Polling klientu ar to pašu tokenu. <https://www.home-assistant.io/integrations/telegram_bot/>
- HA UI 2026-11-18 tika novēroti **divi Broadcast ieraksti**:
  `Balkona Laistīšana` un `Andris`. Tas **nepierāda**, ka tie
  pieder vienam bot tokenam vai ka `notify.andris` ir paredzētā
  Polling bota notify entītija. Pirms jebkuras LIVE darbības privāti
  noteikt precīzu bot config entry/event entity, saņēmēja čatu,
  atļauto sūtītāju un `notify.andris` saistību; publiskā repo
  neatklāt čata ID, lietotāja ID, tokenu vai HA raw konfigurāciju.
  Nepārkonfigurēt nejaušu vai nepareizu Broadcast ierakstu.
  <https://www.home-assistant.io/actions/telegram_bot.send_message/>

### Neatkarīgais STOP ceļš (source pierādījums, NE LIVE garantija)

ESP32 firmware MQTT discovery paredz `Sūknis` slēdzi ar
`cmd_t=balkons/sukna/komanda`, `pl_off=OFF`,
`stat_t=balkons/sukna/stends` un `avty_t=balkons/status`.
Firmware `OFF` apstrādā kā steidzamu releja izslēgšanu.
HA UI 2026-11-18 tika novērota MQTT entītija `Sūknis` ar
stāvokli `Off`. **Tas neapliecina fiziskā sūkņa stāvokli,
komandas piegādi vai neatkarīgās vadības pieejamību nākotnē.**
Konkrētais `switch.*` entity ID un pieejamības/stāvokļa svaigums
jānosaka privāti; testējot `switch.turn_off` vai `mqtt.publish`,
tiek veikta aktuatora LIVE mutation, kam vajag atsevišķu īpašnieka atļauju.
Pirms bota izslēgšanas jābūt neatkarīgi pārbaudītam un īpašniekam
pieejamam reālam STOP ceļam. MQTT publish rezultāts nav fiziska ACK.
<https://www.home-assistant.io/integrations/switch.mqtt/>

### Secīgais cutover (tikai NĀKOTNES, atsevišķi autorizējamas LIVE darbības)

1. **READONLY preflight:** verificēt tieši iesaistīto Telegram botu
   un `Broadcast`/iespējamo `Polling` režīmu, `notify.andris`
   piederību, `event` ID, privātu chat/user allowlist, HA MQTT
   savienojumu, aktīvās HA automatizācijas, RPi5 `balkons-bot.service`
   lifecycle un veco `getUpdates` klientu. Pārbaudīt neatkarīgā
   STOP ceļa fizisku pieejamību un drošuma nosacījumus.
   Ja šos pierādījumus nevar iegūt: **BLOCKED**, servisu neaiztikt.
2. **Staging OFF ar atsevišķu HA LIVE atļauju:** sagatavot divas
   HA automatizācijas atspējotas. Neieslēgt ne komandas, ne MQTT
   paziņojumu patērētāju, kamēr vecais bots saņem Telegram
   komandas un pārsūta `balkons/telegram_out`.
   `event`/chat/user placeholder vērtības aizstāt tikai privāti
   pēc īstā HA Polling event entity iegūšanas.
3. **Atsevišķa īpašnieka Composite STRICT LIVE atļauja:**
   tikai pēc neatkarīgā STOP apstiprinājuma izslēgt vecā bota
   servisu ar vienu precīzi autorizētu
   `systemctl disable --now balkons-bot.service`; pārbaudīt
   `inactive/disabled` un to, ka vecais polleris/forwarder
   tiešām apturēts. Ja stāvoklis neskaidrs: **STOP**, bez retry,
   rollback vai cleanup.
4. **Pēc vecā pollera apturēšanas**, ar atsevišķi autorizētu HA UI
   izmaiņu ieslēgt **vienu** pareizā Telegram bota Polling režīmu,
   pārbaudīt `telegram_command` event entity un privātos
   `chat_id`/`user_id`. Piesaistīt komandu automātiku, saglabājot
   `/laist*` DENY; ieslēgt tikai tad, kad ir neatkarīgs STOP,
   pareiza sūtītāja saistība un pārbaudīts komandu ceļš.
5. Pēc vecā MQTT paziņojumu patērētāja apturēšanas un saņēmēja
   revalidācijas atsevišķi aktivizēt **vienu** HA MQTT→Telegram
   automatizāciju. Pārbaudīt dublikātu neesamību. Tikai ar
   atsevišķu autorizāciju veikt vienu nekaitīgu Telegram paziņojuma
   testu un pārliecināties par cilvēka redzētu piegādi.

**Pārejas logs nav bezpārtraukuma garantija.** Starp vecā pollera
apturēšanu un HA Polling ieslēgšanu Telegram komandas nav pieejamas;
neatkarīgais HA/fiziskais STOP ceļš ir obligāts. Jebkurš negaidīts
stāvoklis pēc pirmās LIVE mutation: **STOP**, bez automātiska
atkārtota mēģinājuma vai pretējas aktuatora komandas.

`main` firmware, HA UI vai GitHub avots viens pats nepierāda
reāla releja/sūkņa/Telegram stāvokli. Šis PR **neautorizē**
merge, HA konfigurāciju, MQTT publicēšanu, Telegram ziņu sūtīšanu,
RPi5/ESP32 ierīces/hosta mutation vai Hermes 11:00 kontroliera izmaiņas.

Oficiāli avoti:
https://www.home-assistant.io/integrations/telegram_bot/ ;
https://www.home-assistant.io/actions/telegram_bot.send_message/ ;
https://www.home-assistant.io/integrations/switch.mqtt/ ;
https://www.home-assistant.io/blog/2026/11/04/release-202611/ .


### HA UI INERT staging — precīzs ID un pirmais Save (2026-11-18)

**source-only, NAV HA instalācija.** Iepriekšējā
`CREATE_DISABLED_ONCE ... NO_ENABLE` LIVE atļauja nebija izpildīta:
HA `Save` netika veikts. Tā nepiešķir pilnvaras šim jaunajam procesam.

`initial_state: false` nosaka HA automatizācijas stāvokli
**startēšanas** laikā, nevis garantē, ka GUI first-save uzreiz izveido
entity `OFF`. Tāpēc source ir trīs neatkarīgi drošības slāņi:
`initial_state: false`, vienīgais MQTT trigger
`enabled: false`, un vienīgais `telegram_bot.send_message`
action `enabled: false`. Ne MQTT trigeris, ne atspējotā
sūtīšanas darbība nevar nosūtīt Telegram ziņu.
Avots arī neietver `mqtt.publish` vai sūkņa komandu.
Oficiālie avoti:
https://www.home-assistant.io/docs/automation/yaml/ ;
https://www.home-assistant.io/docs/automation/trigger/ ;
https://www.home-assistant.io/docs/automation/building-blocks/ .

**Precīzs entītijas ID.** `id: balkons_telegram_native_notification_staged`
ir unikālais HA konfigurācijas ID; tas NAV HA `entity_id`.
`alias: "balkons_telegram_native_notification_staged"`
atbilst mērķa slugam
`automation.balkons_telegram_native_notification_staged`,
bet sadursmes vai reģistra vēsture var dot citu ID.
Tāpēc pirms Save jāpārbauda, ka ID/alias nav jau aizņemts,
un pēc Save jāverificē reālais `entity_id` bez automātiskas
pārdēvēšanas.

**Tikai ar JAUNU Composite STRICT LIVE atļauju:**

1. HA UI YAML editorā izveidot **vienu mapping** no GitHub
   viena elementa YAML saraksta. No `- id:` noņemt saraksta
   `- ` un visām augšējā līmeņa rindām noņemt divas
   atstarpes; nedrīkst ielīmēt visu YAML sarakstu kā vienu map.
2. PIRMS Save pārbaudīt `id`, `alias`, `initial_state: false`,
   precīzo `balkons/telegram_out` MQTT trigeri, `notify.andris`,
   vienu Telegram send action, abus `enabled: false`, payload
   ierobežojumu, plain text un nekādu citu darbību.
3. **GUI first-save var īslaicīgi izveidot automatizācijas entity ON.**
   Vecā `NO_ENABLE` atļauja šādu Save neatļauj. Vajadzīga
   jauna īpašnieka atļauja inert CREATE + iespējamu vienreizēju
   Disable. Ja atļaujas nav — **BLOCKED**, Save neveikt.
4. Pēc viena Save tikai read-only pārbaudīt precīzu HA entity
   un abu atsevišķo slēdžu statusu. Ja redzams paredzētais
   sākotnējais `ON`, vienreiz Disable drīkst veikt tikai šīs
   iepriekš autorizētās kompozītās darbības ietvaros.
   Pēc tam verificēt `OFF`. Ja entity ID atšķiras,
   ir kļūda, timeout vai cita neskaidrība: **STOP**,
   bez retry, rollback, rename vai cleanup.
5. Sūtīšanas action un MQTT trigeris ar `enabled: false`
   jāatstāj inertā stāvoklī arī tad, kad pati automation
   ir `OFF`. To vēlāk maina tikai atsevišķi autorizētā
   cutover, pārbaudot vecā bota MQTT patērētāja apturēšanu.

Šis staging ir **bez Telegram sūtīšanas**, MQTT publikācijām,
sūkņa komandām, RPi5 servisa apturēšanas un pārējām LIVE izmaiņām.
