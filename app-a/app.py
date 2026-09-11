from flask import Flask, request, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
import threading
import time
import requests

app = Flask(__name__)

TARGET_URL = "http://app-b:8000/work"

request_rate = 1
rate_lock = threading.Lock()

requests_total = Counter(
    "app_a_requests_total",
    "Total requests sent by app-a",
    ["status"]
)

request_duration = Histogram(
    "app_a_request_duration_seconds",
    "Time taken for requests sent to app-b"
)

active_requests = Gauge(
    "app_a_active_requests",
    "Number of active requests from app-a"
)


def send_request():
    start = time.time()
    active_requests.inc()

    try:
        response = requests.get(TARGET_URL, timeout=10)

        if response.status_code == 200:
            requests_total.labels(status="success").inc()
        else:
            requests_total.labels(status="failed").inc()

    except Exception:
        requests_total.labels(status="failed").inc()

    finally:
        active_requests.dec()
        request_duration.observe(time.time() - start)


def load_generator():
    global request_rate

    while True:
        with rate_lock:
            current_rate = request_rate

        if current_rate > 0:
            for _ in range(current_rate):
                threading.Thread(
                    target=send_request,
                    daemon=True
                ).start()

        time.sleep(1)


@app.route("/rate", methods=["GET", "POST"])
def rate():
    global request_rate

    if request.method == "POST":
        data = request.get_json()
        new_rate = int(data["rate"])

        with rate_lock:
            request_rate = new_rate

    with rate_lock:
        current_rate = request_rate

    return {
        "requests_per_second": current_rate
    }


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/metrics")
def metrics():
    return Response(
        generate_latest(),
        mimetype=CONTENT_TYPE_LATEST
    )


if __name__ == "__main__":
    thread = threading.Thread(
        target=load_generator,
        daemon=True
    )
    thread.start()

    app.run(
        host="0.0.0.0",
        port=8000,
        threaded=True
    )
