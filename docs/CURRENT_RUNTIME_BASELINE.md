# Current runtime baseline

This is a verified, read-only runtime snapshot, not deployment configuration.

## Evidence binding

- Collection UTC: `2026-08-04T22:52:46Z`
- Source commit: `c1c176868db1baddbb92ab3dc05e09c8dece7015`
- Evidence manifest SHA-256: `2a4689aeeddf58bcbe7a4a380cb1dc10f237e5466a47b83bf90fd384c4c2bf54`
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

- System state: `degraded`.
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
- Timer `apt-daily-upgrade.timer`: load `loaded`, active `active`, sub `waiting`, activates `apt-daily-upgrade.service`, next `Wed 2026-08-05 06:19:39 CEST`, last `Tue 2026-08-04 06:26:39 CEST`.
- Timer `apt-daily.timer`: load `loaded`, active `active`, sub `waiting`, activates `apt-daily.service`, next `Wed 2026-08-05 15:03:15 CEST`, last `Wed 2026-08-05 00:17:16 CEST`.
- Timer `dpkg-db-backup.timer`: load `loaded`, active `active`, sub `waiting`, activates `dpkg-db-backup.service`, next `Thu 2026-08-06 00:00:00 CEST`, last `Wed 2026-08-05 00:00:00 CEST`.
- Timer `e2scrub_all.timer`: load `loaded`, active `active`, sub `waiting`, activates `e2scrub_all.service`, next `Sun 2026-08-09 03:10:11 CEST`, last `Sun 2026-08-02 03:10:49 CEST`.
- Timer `fstrim.timer`: load `loaded`, active `active`, sub `waiting`, activates `fstrim.service`, next `Mon 2026-08-10 00:05:58 CEST`, last `Mon 2026-08-03 01:31:59 CEST`.
- Timer `hermes-deals-aldi-collector.timer`: load `loaded`, active `active`, sub `waiting`, activates `hermes-deals-aldi-collector.service`, next `Wed 2026-08-05 08:30:01 CEST`, last `Tue 2026-08-04 08:39:00 CEST`.
- Timer `hermes-deals-edeka-collector.timer`: load `loaded`, active `active`, sub `waiting`, activates `hermes-deals-edeka-collector.service`, next `Wed 2026-08-05 08:56:28 CEST`, last `Tue 2026-08-04 08:52:59 CEST`.
- Timer `hermes-deals-netto-collector.timer`: load `loaded`, active `active`, sub `waiting`, activates `hermes-deals-netto-collector.service`, next `Wed 2026-08-05 09:16:00 CEST`, last `Tue 2026-08-04 09:17:19 CEST`.
- Timer `logrotate.timer`: load `loaded`, active `active`, sub `waiting`, activates `logrotate.service`, next `Thu 2026-08-06 00:00:00 CEST`, last `Wed 2026-08-05 00:00:00 CEST`.
- Timer `man-db.timer`: load `loaded`, active `active`, sub `waiting`, activates `man-db.service`, next `Wed 2026-08-05 05:58:28 CEST`, last `Tue 2026-08-04 09:45:59 CEST`.
- Timer `systemd-tmpfiles-clean.timer`: load `loaded`, active `active`, sub `waiting`, activates `systemd-tmpfiles-clean.service`, next `unknown`, last `Tue 2026-08-04 02:40:03 CEST`.

## Listening ports

- `tcp` `loopback` port `8200`.
- `tcp` `loopback` port `18554`.
- `tcp` `loopback` port `34811`.
- `tcp` `loopback` port `41197`.
- `tcp` `loopback` port `43413`.
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
- `udp` `wildcard` port `53`.
- `udp` `wildcard` port `1900`.
- `udp` `wildcard` port `5353`.
- `udp` `wildcard` port `33297`.
- `udp` `wildcard` port `33811`.
- `udp` `wildcard` port `33957`.
- `udp` `wildcard` port `33973`.
- `udp` `wildcard` port `34398`.
- `udp` `wildcard` port `34771`.
- `udp` `wildcard` port `36210`.
- `udp` `wildcard` port `36408`.
- `udp` `wildcard` port `36991`.
- `udp` `wildcard` port `37192`.
- `udp` `wildcard` port `39817`.
- `udp` `wildcard` port `40045`.
- `udp` `wildcard` port `40207`.
- `udp` `wildcard` port `40233`.
- `udp` `wildcard` port `41968`.
- `udp` `wildcard` port `42511`.
- `udp` `wildcard` port `43716`.
- `udp` `wildcard` port `44561`.
- `udp` `wildcard` port `44811`.
- `udp` `wildcard` port `45935`.
- `udp` `wildcard` port `46198`.
- `udp` `wildcard` port `46237`.
- `udp` `wildcard` port `46888`.
- `udp` `wildcard` port `47648`.
- `udp` `wildcard` port `47750`.
- `udp` `wildcard` port `49364`.
- `udp` `wildcard` port `49674`.
- `udp` `wildcard` port `51356`.
- `udp` `wildcard` port `51881`.
- `udp` `wildcard` port `52058`.
- `udp` `wildcard` port `54584`.
- `udp` `wildcard` port `56987`.

## Interfaces

- `br-545decce23b3`: operstate `up`, link type `ether`, loopback `false`, IPv4=1, IPv6=1; scopes global=1, host=0, link=1, other=0.
- `br-5b43dced60dc`: operstate `up`, link type `ether`, loopback `false`, IPv4=1, IPv6=1; scopes global=1, host=0, link=1, other=0.
- `br-5b8b1c7e3a43`: operstate `up`, link type `ether`, loopback `false`, IPv4=1, IPv6=1; scopes global=1, host=0, link=1, other=0.
- `docker0`: operstate `up`, link type `ether`, loopback `false`, IPv4=1, IPv6=1; scopes global=1, host=0, link=1, other=0.
- `eth0`: operstate `up`, link type `ether`, loopback `false`, IPv4=1, IPv6=3; scopes global=3, host=0, link=1, other=0.
- `lo`: operstate `unknown`, link type `loopback`, loopback `true`, IPv4=1, IPv6=1; scopes global=0, host=2, link=0, other=0.
- `veth023bd31`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth41a8457`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth44d1ef3`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth4fc6cdd`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth81b1b38`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth89d22fa`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `veth92da784`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vetha84c5b6`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vetha9ca034`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethb521f98`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethba19caa`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethbe18f3d`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethd325d84`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethdd9a73a`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethddffaf0`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `vethe12877b`: operstate `up`, link type `ether`, loopback `false`, IPv4=0, IPv6=1; scopes global=0, host=0, link=1, other=0.
- `wlan0`: operstate `down`, link type `ether`, loopback `false`, IPv4=0, IPv6=0; scopes global=0, host=0, link=0, other=0.

## Limitations and interpretation

The entries above are direct, sanitized observations. They do not establish causation or serve as deployment configuration.
Unavailable or informational sections:
- `systemd_system_state: success_degraded`.
