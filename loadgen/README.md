# Load generator

`locustfile.py` sends steady "normal shopper" traffic to the Demo Store **through the UI's
nginx** (the same path a browser takes). Each simulated user:

1. opens `/` (the SPA's index.html) and loads the "log in as" customer list and the categories,
2. then, with 1–4 s of think time between clicks, repeats this mix:

| Task | Weight | Request |
|---|---|---|
| browse catalog | 10 | `GET /api/products?limit=12&offset=…` (60% filtered by category) |
| view product | 6 | `GET /api/products/{id}` |
| order history | 2 | `GET /api/orders?customer_id=…&limit=20` |
| checkout | 1 | `POST /api/orders` with 1–3 products, quantity 1–2 |

A 409 `insufficient_stock` on checkout counts as success (normal business). Everything else
that is not 2xx (4xx, 500 `db_error`, 503 `db_pool_timeout`/`db_lock_timeout`, nginx 502/504) counts as a
Locust failure.

Every request carries an `X-Request-ID` of the form `lg-<32 hex>`, so load-generator traffic
can be told apart from real clicks, and one id links the nginx log and the apiserver log.

Roughly 30 users ≈ 13 requests/s and about 0.7 orders/s.

## Install

On the load generator host (Python 3.9+):

```sh
sudo mkdir -p /opt/loadgen && sudo chown $USER /opt/loadgen
cp loadgen/locustfile.py loadgen/requirements.txt /opt/loadgen/
cd /opt/loadgen
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

Replace `http://UI_HOST` with the UI's address (nginx, port 80), not the apiserver.

Flat traffic, no web UI:

```sh
.venv/bin/locust -f locustfile.py --host http://UI_HOST --headless -u 30 -r 5
```

`-u` is the number of users, `-r` how many users start per second. Add `-t 2h` to stop after a set
time; otherwise it runs until Ctrl+C.

Daily-like wave (users follow a sine wave around a base; `-u`/`-r` are ignored):

```sh
LOAD_WAVE=1 BASE_USERS=30 WAVE_AMPLITUDE=15 WAVE_PERIOD_SEC=3600 \
  .venv/bin/locust -f locustfile.py --host http://UI_HOST --headless
```

| Variable | Default | Meaning |
|---|---|---|
| `LOAD_WAVE` | unset | `1` enables the wave |
| `BASE_USERS` | 30 | middle of the wave |
| `WAVE_AMPLITUDE` | 15 | users above/below the base at the peak/trough |
| `WAVE_PERIOD_SEC` | 3600 | length of one full wave |
| `WAVE_SPAWN_RATE` | 5 | users started/stopped per second while adjusting |

With Locust's web UI instead (charts, start/stop, change user count live), drop `--headless` and
open `http://LOADGEN_HOST:8089`:

```sh
.venv/bin/locust -f locustfile.py --host http://UI_HOST
```

### As a service

To keep traffic running across logouts and reboots, `/etc/systemd/system/loadgen.service`:

```ini
[Unit]
Description=Demo Store load generator (Locust)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/loadgen
Environment=LOAD_WAVE=1 BASE_USERS=30 WAVE_AMPLITUDE=15 WAVE_PERIOD_SEC=3600
ExecStart=/opt/loadgen/.venv/bin/locust -f locustfile.py --host http://UI_HOST --headless --only-summary
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload && sudo systemctl enable --now loadgen
journalctl -u loadgen -f
```

## Keep stock from running out

Checkouts only ever decrease INVENTORY. At ~30 users the seeded stock (~50,000 units) lasts
roughly 7 hours; after that nearly every checkout gets a 409 and no orders are written, which
quietly changes the "normal" baseline. For long runs, top stock up periodically with
`restock.py`, from a checkout of this repo on a host that has the API server's venv and DB2_*
settings:

```sh
python loadgen/restock.py                       # +200 units where quantity < 20
python loadgen/restock.py --below 50 --add 500
```

Every 10 minutes from cron (`crontab -e`):

```
*/10 * * * * cd /path/to/ECommerce-Demo-APIServer && set -a && . ./.env && set +a && .venv/bin/python loadgen/restock.py >> /tmp/restock.log 2>&1
```

Or start fresh between demos with `python sql/seed.py --reset`.

## Things to know

- nginx's `proxy_read_timeout` is 10 s. Requests slower than that come back as nginx's 504
  `upstream_timeout`, not as an apiserver error. With Db2's default `LOCKTIMEOUT -1`, a stuck
  lock looks like 504s; set `LOCKTIMEOUT` below 10 (see the main README) to see 503
  `db_lock_timeout` instead.
- Only `index.html` is fetched for `/`, not the JS/CSS bundles, so nginx sees fewer `/assets/`
  requests than real browsers would produce.
- The customer list is the UI's (`limit=50`), so only the first 50 customers place orders, as
  in the real UI.
