from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "apiserver_http_requests_total",
    "HTTP requests by method, route template and status code",
    ["method", "route", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "apiserver_http_request_duration_seconds",
    "HTTP request duration by method and route template",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
