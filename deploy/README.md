# OneTouch HTTPS route

The current Hostinger Rodem MES Caddy instance owns `srv1934103.hstgr.cloud` and its TLS certificate. Keep the existing MES route at `/`; mount `rodem-mes-Caddyfile` as `/etc/caddy/Caddyfile` and run Caddy with `caddy run --config /etc/caddy/Caddyfile --adapter caddyfile`. The MES upstream uses its container name so it remains unambiguous when Caddy also joins the OneTouch network.

Attach only the Caddy service to the external `onetouch-cockpit-v2_default` network in addition to its existing `mesnet` network:

```yaml
services:
  caddy:
    networks:
      mesnet:
        ipv4_address: 10.213.71.10
      onetouch_v2: {}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro

networks:
  onetouch_v2:
    external: true
    name: onetouch-cockpit-v2_default
```

The OneTouch frontend is built with `/onetouch/` as its base path, and its API requests use the same prefix. Caddy strips that prefix before forwarding to the app. Keep the Caddy upstream name `onetouch-cockpit-v2-app-1:8501`; do not attach the OneTouch app to `mesnet`, where both Compose projects use the service alias `app`.
