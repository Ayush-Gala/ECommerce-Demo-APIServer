"""Connection-leak trigger for the Demo Store (Case 1).

This load profile drives the connection leak in GET /api/products/{id}: every
request for a product id that does not exist leaks one pool connection (the
route acquires a connection and never releases it on the 404 path). After
POOL_MAX_SIZE (default 20) misses, the pool is exhausted and *every* DB-backed
request starts returning 503 db_pool_timeout after POOL_ACQUIRE_TIMEOUT seconds.

Unlike the normal locustfile, point this one straight at the apiserver, not the
UI's nginx, so the apiserver's own 503s are visible rather than nginx 504s:

    locust -f loadgen/leak_locustfile.py --host http://APISERVER:8000 \
        --headless -u 1 -r 1

Knobs (environment variables):
    MISS_ID_BASE   first product id to request; must be above the real catalog
                   so the lookup always misses (default 10000000)
    LEAK_INTERVAL  seconds between leak requests; wider spacing makes
                   apiserver_db_pool_in_use climb slowly for a nicer demo
                   (default 2.0)

Watch while it runs:
    curl -s http://APISERVER:8000/metrics | grep apiserver_db_pool
    tail -f /var/log/apiserver/apiserver.log | grep -E 'pool|503'

Recover: restart the apiserver (systemctl restart apiserver); leaked
connections are only reclaimed on restart.
"""

import itertools
import os

from locust import HttpUser, constant, task

MISS_ID_BASE = int(os.getenv("MISS_ID_BASE", "10000000"))
LEAK_INTERVAL = float(os.getenv("LEAK_INTERVAL", "2.0"))


class Leaker(HttpUser):
    # One steady request every LEAK_INTERVAL seconds; keep -u low (1-2) so the
    # pool fills in a controlled, observable way rather than all at once.
    wait_time = constant(LEAK_INTERVAL)

    def on_start(self):
        self._ids = itertools.count(MISS_ID_BASE)

    @task
    def leak_one_connection(self):
        pid = next(self._ids)
        with self.client.get(
            f"/api/products/{pid}",
            name="/api/products/{id} (miss -> leak)",
            headers={"X-Request-ID": f"leak-{pid}"},
            catch_response=True,
        ) as r:
            # While the pool still has capacity the miss returns 404 (expected,
            # and the leak we want). Once the pool is exhausted the same request
            # returns 503 db_pool_timeout, which is the symptom we are
            # demonstrating, so neither should count as a Locust failure.
            if r.status_code in (404, 503):
                r.success()
