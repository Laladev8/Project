
from flask import Flask, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time
import os

app = Flask(__name__)


# Prometheus metrics
requests_total = Counter(
    "app_b_requests_total",
    "Total requests received by app-b",
    ["endpoint", "status"]
)

request_duration = Histogram(
    "app_b_request_duration_seconds",
    "Time taken to handle requests",
    ["endpoint"]
)

active_requests = Gauge(
    "app_b_active_requests",
    "Number of active requests"
)


# Health check
@app.route("/health")
def health():
    return {"status": "ok"}, 200


# Main workload endpoint
@app.route("/work")
def work():
    start = time.time()
    active_requests.inc()

    try:
        # Each request uses about 10 MB of RAM
        memory = bytearray(10 * 1024 * 1024)

        # Make sure the allocated memory is actually used
        for i in range(0, len(memory), 4096):
            memory[i] = 1

        # Some CPU-intensive work
        result = 0
        for i in range(1_000_000):
            result += i * i

        # Keep the memory allocated for about 2 seconds
        time.sleep(2)

        requests_total.labels(
            endpoint="/work",
            status="success"
        ).inc()

        return {
            "status": "ok",
            "pid": os.getpid()
        }

    except Exception:
        requests_total.labels(
            endpoint="/work",
            status="error"
        ).inc()
        raise

    finally:
        active_requests.dec()

        request_duration.labels(
            endpoint="/work"
        ).observe(time.time() - start)


# Prometheus collects metrics from this endpoint
@app.route("/metrics")
def metrics():
    return Response(
        generate_latest(),
        mimetype=CONTENT_TYPE_LATEST
    )


if __name__ == "__main__":
    # 0.0.0.0 allows other Docker containers to access app-b
    app.run(
        host="0.0.0.0",
        port=8000,
        threaded=True
    )


