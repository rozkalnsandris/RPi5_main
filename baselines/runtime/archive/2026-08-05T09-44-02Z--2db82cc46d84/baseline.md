# Current runtime baseline

This is a verified, read-only runtime snapshot, not deployment configuration.

## Evidence binding

- Collection UTC: `2026-08-05T09:44:02Z`
- Source commit: `b1dd93d460ad71c1cf80502f7b2dc875fe384a1f`
- Evidence manifest SHA-256: `872adb99cf9fa9b5c18380b2f0d737f23acd593b4b718311410359042377fb73`
- Collection context: `host-approved`

## Docker

- Engine version: `29.7.1`
- Compose version: `v5.3.1`
- Containers: 20; Compose projects: 4; networks: 6.
- Container `adguard`: image `adguard/adguardhome:latest`, state `running`, health `healthy`.
- Container `autoheal`: image `willfarrell/autoheal:latest`, state `running`, health `healthy`.
- Container `chromadb`: image `chromadb/chroma:latest`, state `running`, health `none`.
- Container `cv`: image `nginx:alpine`, state `running`, health `none`.
- Container `cv-cloudflared`: image `cloudflare/cloudflared:latest`, state `running`, health `none`.
- Container `cvbot`: image `cv-cvbot`, state `running`, health `healthy`.
- Container `grafana`: image `grafana/grafana:latest`, state `running`, health `none`.
- Container `grafana-renderer`: image `grafana/grafana-image-renderer:latest`, state `running`, health `healthy`.
- Container `hermes-deals-api-1`: image `hermes-deals-api:release-0.3.27-netto-quality-2ded85a-20260804`, state `running`, health `healthy`.
- Container `hermes-deals-db-1`: image `postgres:18.4-bookworm`, state `running`, health `healthy`.
- Container `hermes-deals-ui-dev-9190-ui_dev_api-1`: image `hermes-deals-api:preview-netto-daily-nopdf-v7-3-684b148`, state `running`, health `healthy`.
- Container `hermes-deals-ui-dev-9190-ui_dev_web-1`: image `nginx:1.30.4-alpine`, state `running`, health `healthy`.
- Container `hermes-deals-web-1`: image `nginx:1.30.4-alpine`, state `running`, health `none`.
- Container `homeassistant`: image `ghcr.io/home-assistant/home-assistant:stable`, state `running`, health `none`.
- Container `matter-server`: image `ghcr.io/home-assistant-libs/python-matter-server:stable`, state `running`, health `none`.
- Container `mosquitto`: image `eclipse-mosquitto:2`, state `running`, health `none`.
- Container `node-exporter`: image `prom/node-exporter:latest`, state `running`, health `none`.
- Container `portainer`: image `portainer/portainer-ce:latest`, state `running`, health `none`.
- Container `prometheus`: image `prom/prometheus:latest`, state `running`, health `none`.
- Container `uptime-kuma`: image `louislam/uptime-kuma:2`, state `running`, health `healthy`.
- Compose project `cv`: status `running`.
- Compose project `docker`: status `running`.
- Compose project `hermes-deals`: status `running`.
- Compose project `hermes-deals-ui-dev-9190`: status `running`.
- Network `bridge`: driver `bridge`, scope `local`.
- Network `cv_default`: driver `bridge`, scope `local`.
- Network `docker_default`: driver `bridge`, scope `local`.
- Network `hermes-deals_internal`: driver `bridge`, scope `local`.
- Network `host`: driver `host`, scope `local`.
- Network `none`: driver `null`, scope `local`.

## systemd

- System state: `running`.
- Enabled units: 46; failed units: 0; timers: 11.
- Enabled `ModemManager.service`: `enabled`.
- Enabled `NetworkManager-dispatcher.service`: `enabled`.
- Enabled `NetworkManager-wait-online.service`: `enabled`.
- Enabled `NetworkManager.service`: `enabled`.
- Enabled `actions.runner.rozkalnsandris-hermes-deals.rpi5-hermes-deals-audit.service`: `enabled`.
- Enabled `apparmor.service`: `enabled`.
- Enabled `apt-daily-upgrade.timer`: `enabled`.
- Enabled `apt-daily.timer`: `enabled`.
- Enabled `avahi-daemon.service`: `enabled`.
- Enabled `balkons-bot.service`: `enabled`.
- Enabled `balkons-log.service`: `enabled`.
- Enabled `console-setup.service`: `enabled`.
- Enabled `containerd.service`: `enabled`.
- Enabled `cron.service`: `enabled`.
- Enabled `docker.service`: `enabled`.
- Enabled `dpkg-db-backup.timer`: `enabled`.
- Enabled `e2scrub_all.timer`: `enabled`.
- Enabled `e2scrub_reap.service`: `enabled`.
- Enabled `fail2ban.service`: `enabled`.
- Enabled `fake-hwclock.service`: `enabled`.
- Enabled `fstrim.timer`: `enabled`.
- Enabled `getty@.service`: `enabled`.
- Enabled `hciuart.service`: `enabled`.
- Enabled `hermes-dashboard.service`: `enabled`.
- Enabled `hermes-deals-aldi-collector.timer`: `enabled`.
- Enabled `hermes-deals-edeka-collector.timer`: `enabled`.
- Enabled `hermes-deals-netto-collector.timer`: `enabled`.
- Enabled `hermes-gateway.service`: `enabled`.
- Enabled `keyboard-setup.service`: `enabled`.
- Enabled `logrotate.timer`: `enabled`.
- Enabled `man-db.timer`: `enabled`.
- Enabled `nvmefc-boot-connections.service`: `enabled`.
- Enabled `rpi-display-backlight.service`: `enabled`.
- Enabled `rpi-eeprom-update.service`: `enabled`.
- Enabled `rpi5-docker-firewall.service`: `enabled`.
- Enabled `ssh.service`: `enabled`.
- Enabled `sshswitch.service`: `enabled`.
- Enabled `systemd-pstore.service`: `enabled`.
- Enabled `systemd-timesyncd.service`: `enabled`.
- Enabled `triggerhappy.service`: `enabled`.
- Enabled `udisks2.service`: `enabled`.
- Enabled `ufw.service`: `enabled`.
- Enabled `unattended-upgrades.service`: `enabled`.
- Enabled `watchdog.service`: `enabled`.
- Enabled `wpa_supplicant.service`: `enabled`.
- Enabled `zramswap.service`: `enabled`.
- Timer `apt-daily-upgrade.timer`: load `loaded`, active `active`, sub `waiting`, activates `apt-daily-upgrade.service`, next `Thu 2026-08-06 06:23:10 CEST`, last `Wed 2026-08-05 06:58:32 CEST`.
- Timer `apt-daily.timer`: load `loaded`, active `active`, sub `waiting`, activates `apt-daily.service`, next `Wed 2026-08-05 14:45:48 CEST`, last `Wed 2026-08-05 00:17:16 CEST`.
- Timer `dpkg-db-backup.timer`: load `loaded`, active `active`, sub `waiting`, activates `dpkg-db-backup.service`, next `Thu 2026-08-06 00:00:00 CEST`, last `Wed 2026-08-05 00:00:00 CEST`.
- Timer `e2scrub_all.timer`: load `loaded`, active `active`, sub `waiting`, activates `e2scrub_all.service`, next `Sun 2026-08-09 03:10:57 CEST`, last `Sun 2026-08-02 03:10:49 CEST`.
- Timer `fstrim.timer`: load `loaded`, active `active`, sub `waiting`, activates `fstrim.service`, next `Mon 2026-08-10 01:03:37 CEST`, last `Mon 2026-08-03 01:31:59 CEST`.
- Timer `hermes-deals-aldi-collector.timer`: load `loaded`, active `active`, sub `waiting`, activates `hermes-deals-aldi-collector.service`, next `Thu 2026-08-06 08:38:16 CEST`, last `Wed 2026-08-05 08:33:38 CEST`.
- Timer `hermes-deals-edeka-collector.timer`: load `loaded`, active `active`, sub `waiting`, activates `hermes-deals-edeka-collector.service`, next `Thu 2026-08-06 08:50:28 CEST`, last `Wed 2026-08-05 08:51:42 CEST`.
- Timer `hermes-deals-netto-collector.timer`: load `loaded`, active `active`, sub `waiting`, activates `hermes-deals-netto-collector.service`, next `Thu 2026-08-06 09:14:50 CEST`, last `Wed 2026-08-05 09:11:12 CEST`.
- Timer `logrotate.timer`: load `loaded`, active `active`, sub `waiting`, activates `logrotate.service`, next `Thu 2026-08-06 00:00:00 CEST`, last `Wed 2026-08-05 00:00:00 CEST`.
- Timer `man-db.timer`: load `loaded`, active `active`, sub `waiting`, activates `man-db.service`, next `Thu 2026-08-06 08:01:43 CEST`, last `Wed 2026-08-05 05:11:08 CEST`.
- Timer `systemd-tmpfiles-clean.timer`: load `loaded`, active `active`, sub `waiting`, activates `systemd-tmpfiles-clean.service`, next `unknown`, last `Wed 2026-08-05 01:39:19 CEST`.

## Listening ports

- `tcp` `loopback` port `8200`.
- `tcp` `loopback` port `18554`.
- `tcp` `loopback` port `36713`.
- `tcp` `private_or_local` port `1883`.
- `tcp` `private_or_local` port `3030`.
- `tcp` `private_or_local` port `8081`.
- `tcp` `private_or_local` port `9000`.
- `tcp` `private_or_local` port `9090`.
- `tcp` `private_or_local` port `9100`.
- `tcp` `private_or_local` port `9119`.
- `tcp` `private_or_local` port `9128`.
- `tcp` `private_or_local` port `9190`.
- `tcp` `private_or_local` port `9443`.
- `tcp` `wildcard` port `22`.
- `tcp` `wildcard` port `53`.
- `tcp` `wildcard` port `3001`.
- `tcp` `wildcard` port `3080`.
- `tcp` `wildcard` port `5580`.
- `tcp` `wildcard` port `8080`.
- `tcp` `wildcard` port `8088`.
- `tcp` `wildcard` port `8089`.
- `tcp` `wildcard` port `8123`.
- `tcp` `wildcard` port `18555`.
- `udp` `loopback` port `5353`.
- `udp` `private_or_local` port `546`.
- `udp` `private_or_local` port `5353`.
- `udp` `specific_other` port `5353`.
- `udp` `wildcard` port `53`.
- `udp` `wildcard` port `1900`.
- `udp` `wildcard` port `5353`.
- `udp` `wildcard` port `33165`.
- `udp` `wildcard` port `34196`.
- `udp` `wildcard` port `34379`.
- `udp` `wildcard` port `36675`.
- `udp` `wildcard` port `37092`.
- `udp` `wildcard` port `37175`.
- `udp` `wildcard` port `37695`.
- `udp` `wildcard` port `39293`.
- `udp` `wildcard` port `40297`.
- `udp` `wildcard` port `43551`.
- `udp` `wildcard` port `45889`.
- `udp` `wildcard` port `46161`.
- `udp` `wildcard` port `46321`.
- `udp` `wildcard` port `46665`.
- `udp` `wildcard` port `47059`.
- `udp` `wildcard` port `47622`.
- `udp` `wildcard` port `48300`.
- `udp` `wildcard` port `48956`.
- `udp` `wildcard` port `49150`.
- `udp` `wildcard` port `49413`.
- `udp` `wildcard` port `50186`.
- `udp` `wildcard` port `51338`.
- `udp` `wildcard` port `53837`.
- `udp` `wildcard` port `55212`.
- `udp` `wildcard` port `55842`.
- `udp` `wildcard` port `56347`.
- `udp` `wildcard` port `57079`.
- `udp` `wildcard` port `58272`.
- `udp` `wildcard` port `58705`.
- `udp` `wildcard` port `59207`.
- `udp` `wildcard` port `59377`.
- `udp` `wildcard` port `59656`.

## Interfaces

- `br-545decce23b3`: operstate `up`, link type `ether`, loopback `false`, IPv4=1, IPv6=1; scopes global=1, host=0, link=1, other=0.
- `br-5b43dced60dc`: operstate `up`, link type `ether`, loopback `false`, IPv4=1, IPv6=1; scopes global=1, host=0, link=1, other=0.
- `br-5b8b1c7e3a43`: operstate `up`, link type `ether`, loopback `false`, IPv4=1, IPv6=1; scopes global=1, host=0, link=1, other=0.
- `docker0`: operstate `up`, link type `ether`, loopback `false`, IPv4=1, IPv6=1; scopes global=1, host=0, link=1, other=0.
- `eth0`: operstate `up`, link type `ether`, loopback `false`, IPv4=1, IPv6=3; scopes global=3, host=0, link=1, other=0.
- `lo`: operstate `unknown`, link type `loopback`, loopback `true`, IPv4=1, IPv6=1; scopes global=0, host=2, link=0, other=0.
- `veth0270bf4`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth216534b`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth2a20b5f`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth2ee7403`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth3a3670b`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth691dc13`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth774f804`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth8f5c40d`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth920dae4`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth948762b`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vetha6caa90`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethb053077`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethb81aad0`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethe6748eb`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethedabf3b`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethf499f5c`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `wlan0`: operstate `down`, link type `ether`, loopback `false`, IPv4=0, IPv6=0; scopes global=0, host=0, link=0, other=0.

## Limitations and interpretation

The entries above are direct, sanitized observations. They do not establish causation or serve as deployment configuration.
- No command-capability limitations were recorded.
