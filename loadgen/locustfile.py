"""Steady "normal shopper" traffic for the Demo Store, sent through the UI's nginx.

Each simulated user picks a customer from the "log in as" list, then browses the
catalog, checks order history and occasionally checks out, with 1-4 s of think
time between clicks. Requests mirror what the UI itself sends.

It deliberately never calls GET /api/products/{id}: that route has the
connection-leak bug (see leak_locustfile.py), and normal traffic must not touch it.

Run (see loadgen/README.md):
    locust -f loadgen/locustfile.py --host http://<ui-host> --headless -u 30 -r 5
    LOAD_WAVE=1 locust -f loadgen/locustfile.py --host http://<ui-host> --headless
"""

import math
import os
import random
import uuid

from locust import HttpUser, LoadTestShape, between, task

PAGE_SIZE = 12  # the UI's catalog page size (views/catalog.js)
CATALOG_PAGES = 17  # 200 products / 12 per page
CATEGORY_PAGES = 3  # 25 products per category / 12 per page


def request_id() -> str:
    # Accepted by nginx and the apiserver ([A-Za-z0-9._:-]{1,128}); the "lg-" prefix
    # marks load-generator traffic in both logs.
    return f"lg-{uuid.uuid4().hex}"


class Shopper(HttpUser):
    wait_time = between(1, 4)  # think time between clicks

    def on_start(self):
        self.customer_id = None
        self.categories = []
        self.product_ids = []
        self.get("/", name="/ (index)")
        self.load_session()

    def get(self, path, name, **kwargs):
        return self.client.get(path, name=name, headers={"X-Request-ID": request_id()}, **kwargs)

    def load_session(self) -> bool:
        """Pick a customer and load categories. Retried on later tasks if the API was down."""
        if self.customer_id is None:
            r = self.get("/api/customers", name="/api/customers", params={"limit": 50})
            customers = r.json().get("items", []) if r.ok else []
            if customers:
                self.customer_id = random.choice(customers)["customer_id"]
        if not self.categories:
            r = self.get("/api/categories", name="/api/categories")
            if r.ok:
                self.categories = [c["category"] for c in r.json().get("items", [])]
        return self.customer_id is not None

    @task(10)
    def browse_catalog(self):
        if self.categories and random.random() < 0.6:
            params = {
                "limit": PAGE_SIZE,
                "offset": random.randrange(CATEGORY_PAGES) * PAGE_SIZE,
                "category": random.choice(self.categories),
            }
        else:
            params = {"limit": PAGE_SIZE, "offset": random.randrange(CATALOG_PAGES) * PAGE_SIZE}
        r = self.get("/api/products", name="/api/products", params=params)
        if r.ok:
            self.product_ids = [p["product_id"] for p in r.json().get("items", [])] or self.product_ids

    @task(2)
    def order_history(self):
        if not self.load_session():
            return
        self.get("/api/orders", name="/api/orders [GET]", params={"customer_id": self.customer_id, "limit": 20})

    @task(1)
    def checkout(self):
        if not self.product_ids or not self.load_session():
            return
        picks = random.sample(self.product_ids, k=min(len(self.product_ids), random.randint(1, 3)))
        items = [{"product_id": pid, "quantity": random.randint(1, 2)} for pid in picks]
        with self.client.post(
            "/api/orders",
            json={"customer_id": self.customer_id, "items": items},
            headers={"X-Request-ID": request_id()},
            name="/api/orders [POST]",
            catch_response=True,
        ) as r:
            if r.status_code == 409:  # out of stock is normal business, not a failure
                r.success()


# Optional: a slow "daily-like" wave instead of flat traffic. Enable with LOAD_WAVE=1.
# Locust uses a LoadTestShape automatically when one is defined, ignoring -u/-r.
if os.getenv("LOAD_WAVE") == "1":

    class Wave(LoadTestShape):
        base = int(os.getenv("BASE_USERS", "30"))
        amplitude = int(os.getenv("WAVE_AMPLITUDE", "15"))
        period = int(os.getenv("WAVE_PERIOD_SEC", "3600"))
        spawn_rate = float(os.getenv("WAVE_SPAWN_RATE", "5"))

        def tick(self):
            t = self.get_run_time()
            users = self.base + int(self.amplitude * math.sin(2 * math.pi * t / self.period))
            return max(users, 1), self.spawn_rate
