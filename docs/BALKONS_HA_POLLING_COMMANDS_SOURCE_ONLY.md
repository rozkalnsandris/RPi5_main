# HA Telegram Polling komandas — SOURCE ONLY (#1525)

**Mērķis:** nākotnē saglabāt `/stop`, `/mitrums`, `/statuss`, `/raw` un `/start` bez RPi5 Python bota. Atsevišķs outcome no paziņojumu Draft PR #1524. Tikai GitHub avots, nav HA vai ESP32 LIVE izmaiņu.

## Home Assistant 2026.11 dokumentācija

- https://www.home-assistant.io/integrations/telegram_bot/ — `Broadcast` ir outbound-only; `Polling` saņem komandas. Telegram integrācijas `event entity` izmanto `state` trigger un `trigger.to_state.attributes` (`event_type`, `command`, `args`, `chat_id`, `user_id`). Vienam bot tokenam nav atļauti divi vienlaicīgi `getUpdates` klienti.
- https://www.home-assistant.io/actions/mqtt.publish/ — `mqtt.publish` ar fiksētu tēmu, datiem, `qos: 0` un `retain: false`.
- https://www.home-assistant.io/actions/telegram_bot.send_message/ — sūtīšana uz precīzu `notify` entītiju.
- https://www.home-assistant.io/blog/2026/11/04/release-202611/ — vecā Telegram YAML `notify` platforma ir novecojusi un noņemta.

## Sagatavotais risinājums

`ops/homeassistant/balkons-telegram-polling-commands.yaml` ir **viena inertā** HA automatizācijas atsauce (`initial_state: false`,
viens `state` trigeris ar `enabled: false` un galvenā `choose` darbība
ar `enabled: false`), nevis uzinstalēta Polling integrācija.

Reālās HA event entītijas identifikators ir `event.balkona_laistisana_update_event`; tas jau ir fiksēts source. Pirms owner-autorizētas LIVE izmaiņas HA UI **privāti** jāaizstāj `REPLACE_WITH_VERIFIED_BALKONS_POLLING_CONFIG_ENTRY_ID`, `REPLACE_WITH_APPROVED_CHAT_ID` un `REPLACE_WITH_APPROVED_USER_ID` ar neatkarīgi pārbaudītām atbilstošā bota, čata un sūtītāja vērtībām. Neievietot identifikatorus publiskā GitHub. `notify.andris` ir iepriekš izmēģināta entītija, bet pēc Polling pārkonfigurācijas jāpārbauda atkārtoti.

Tikai pareizs `telegram_command` notikums, konkrētais chat + user, un tukši `args` ļauj izvērtēt komandu. Citas komandas pēc noklusējuma nedara neko.

| Telegram | Paredzētā HA darbība | Noteikums |
|---|---|---|
| `/stop` | `balkons/cmd=stop` | neatkarīgi no laistīšanas atļaujas |
| `/mitrums` | `balkons/cmd=mitrums` | diagnostika |
| `/statuss` | `balkons/cmd=statuss` | diagnostika |
| `/raw` | `balkons/cmd=raw` | diagnostika |
| `/start` | statisks Telegram palīdzības teksts | nav MQTT |
| `/laist`, `/laist_*` | Telegram **DENY** atbilde | nav MQTT laistīšanas komandas |
| nezināma | nav darbību | fail-closed |

ESP32 atbildes jau tiek nosūtītas uz `balkons/telegram_out`; tās paredzēts piegādāt ar atsevišķo HA notification-only automatizāciju #1524. `mqtt.publish` darbības pieņemšana nepierāda ESP32 ACK vai sūkņa faktisku apturēšanu. `mode: parallel` nepieļauj STOP parastu Telegram atbilžu seriālu rindu, bet negarantē tīkla/MQTT piegādes termiņu.

## Kāpēc `/laist*` ir bloķēta

Pašreizējā RPi5 `manual-safety-v1.json` admission prasa aktuālu (ne vecāku par 6 h) un precīzu schema, 10 sensorus, `sensor_coverage_ok`, nepastāvošu sala risku, `already_watered_today=false` un `decision=manual_permit`. HA nav pierādīta līdzvērtīga datu autoritāte. Kamēr nav patstāvīgi izstrādāta un pārbaudīta HA policy, **nekāda** `/laist` vai `/laist_*` MQTT publicēšana nav pieļaujama. ESP32 failsafe nav šo vārtu aizstājējs.

## Nākamais LIVE gate (nav autorizēts)

1. Sanitizēti READONLY pārbaudīt HA platformu, saņēmēju `notify.andris`, event entity, autorizēto chat/user bez ID izvadīšanas, MQTT savienojumu, RPi5 bota Polling statusu un neatkarīgu ārkārtas apturēšanas ceļu. Nedrīkst pieņemt ESP32/sūkņa stāvokli no GitHub.
2. Sagatavot HA automātiku **OFF**. Pārbaudīt, kas noticis ar #1524 paziņojumu PR/HA statusu. Pēc atsevišķas precīzas Composite STRICT LIVE atļaujas deaktivizēt veco RPi5 polleri, pārbaudīt `inactive/disabled` un **tikai tad** pārslēgt esošo HA Telegram botu uz `Polling`. Nedrīkst veidot otru `getUpdates` konkurentu.
3. Tikai pēc owner atļaujas un privāto datu/avārijas STOP ceļa pārbaudes ieslēgt vienu komandautomatizāciju, nepārkāpjot MQTT/aktuatora drošības robežu. `/laist*` paliek bloķēta. Pēc neskaidras pirmās mutation — STOP bez retry/rollback/cleanup.

**Merge nav LIVE.** Šis source darba posms neietver HA konfigurācijas maiņu, Telegram sūtīšanu, MQTT publish, RPi5 servisu apturēšanu, credentials, Hermes, ESP32 firmware vai sūkņa komandas.


## HA UI inertā sagatavošana (source only, 2026-11-19)

Šis ir tikai GitHub source, nevis HA instalācija vai LIVE atļauja.
READONLY preflight redzēja Telegram Broadcast servisus, bet
neverificēja Polling event entītiju. Vecais `balkons-bot.service`
bija `active/running/enabled`; neveidot otru `getUpdates` klientu.

Trīs neatkarīgi aizsargi: `initial_state: false`, vienīgais
`state` trigeris `enabled: false`, galvenā `choose` darbība
`enabled: false`. Pēdējā neļauj izpildīt MQTT vai Telegram
darbības arī ar HA `Run actions` (kas apiet trigeri).

Jaunai HA UI automation veido vienu YAML mapping **bez `id:`**:
pilnībā izlaist GitHub `- id:` rindu, atlikušajām rindām
noņemt divas atkāpes atstarpes; HA piešķir ģenerētu ID.
**Šis source nav gatavs LIVE instalācijai ar placeholder datiem.**
Source jau nosaka novēroto Telegram Polling `event` entītiju.
Privāti jāpārbauda attiecīgā bota `config_entry_id`, atļautā
`chat_id` un `user_id`, kā arī `notify.andris` piesaiste.
Reālās vērtības aizstāj tikai precīzi autorizētā HA UI darbībā,
nekad publiskā GitHub. Neieslēgt otro `getUpdates` klientu.

Tikai ar jaunu **Composite STRICT LIVE** owner atļauju drīkst
vienu inertā stāvoklī izveidotu automation saglabāt HA UI.
Pirms Save verificēt bez-ID mapu, trīs aizsargus, privātos
identitātes filtrus, nemainīgus `/laist*` DENY un fiksētus
MQTT maršrutus. Pēc Save read-only pārbaudīt HA ģenerēto ID,
faktisko entity ID, Automation OFF un abus `enabled: false`.
Ja sākumā ON, drīkst vienreiz Disable tikai šīs atļaujas ietvaros.

Pie kļūdas, ID konflikta vai timeout: **STOP, bez retry**,
rollback, cleanup vai alternatīvas LIVE mutation.
**NO MQTT publish**, Telegram sūtīšana, bota apturēšana,
Polling pārslēgšana un sūkņa/ESP32 izmaiņas nav autorizētas.

Home Assistant: https://www.home-assistant.io/docs/automation/trigger/ ;
https://www.home-assistant.io/docs/automation/building-blocks/ ;
https://www.home-assistant.io/docs/automation/yaml/ .

## Native Polling bota identitātes filtrs (source only, 2026-11-22)

Vienkāršākais HA-native variants: esošajai **atspējotajai** YAML
komandu automatizācijai pievienots noteikums, ka `trigger.to_state`
ir precīzā `event.balkona_laistisana_update_event` entītija, `bot`
atribūts ir `mapping` un `bot.config_entry_id` precīzi sakrīt ar
**atsevišķi un privāti apstiprinātu** `Polling` bota config entry ID.
Pārbaude turpina prasīt `telegram_command`, atļauto `chat_id`,
`user_id` un tukšus `args`. Ja `bot` trūkst, tas nav mapping vai
`config_entry_id` trūkst/neatbilst, nosacījums neizpildās.
Reālie ID nav source; placeholder
`REPLACE_WITH_VERIFIED_BALKONS_POLLING_CONFIG_ENTRY_ID` jāaizstāj
**tikai privāti**, atsevišķi apstiprinātā HA UI darbībā.
Tas nav lietotāja identitātes/provenance pierādījums pats par sevi.

Šis ir tikai **GitHub source**, nevis instalētās HA automation izmaiņa.
HA UI iepriekš bija izveidota
`automation.balkons_telegram_polling_commands_staged`
(ID `1795378925536`), un READONLY pārbaudē tā bija `OFF`, ar
atspējotu trigeri un `choose` darbību. Pirms jebkura HA Save jāverificē
faktiskais instalētais YAML un privāti identifikatori; šis source
nedod Save, enable, Telegram vai MQTT autorizāciju. Vienā botā nedrīkst
darbināt otru `getUpdates` saņēmēju. `/laist*` paliek DENY,
`/stop` ārkārtas piekļuve jāverificē patstāvīgi, un
`notify.andris` piesaiste vēl nav neatkarīgi apliecināta.

Avota pamatojums: Home Assistant Core `2026.11.2`
`homeassistant/components/telegram_bot/bot.py` pievieno
`event_data["bot"]["config_entry_id"]`; `event.py` šo payload
pievieno event entītijai. Python collector instalēšana šim
native filtram **nav vajadzīga**.
