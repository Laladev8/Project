# Docker Compose Load Testing & Grafana Monitoring

This project demonstrates load testing between two containerized applications using Docker Compose and monitoring the system with Prometheus, Grafana, and cAdvisor.

The main goal is to observe how increasing request load affects application performance and container resources, and to demonstrate an Out-Of-Memory (OOM) restart scenario.

---

## Architecture

```text
                    HTTP Requests
                  ┌───────────────┐
                  │               ▼
              ┌───────┐       ┌───────┐
              │ app-a │ ─────>│ app-b │
              └───────┘       └───────┘
                  │                │
                  │ metrics        │ metrics
                  │                │
                  └───────┬────────┘
                          │
                          ▼
                    ┌───────────┐
                    │Prometheus │
                    └─────┬─────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
          ┌────────┐             ┌──────────┐
          │Grafana │             │ cAdvisor │
          └────────┘             └──────────┘
```

All services communicate through the Docker Compose `monitor-net` network.

---

## Components

### app-a

`app-a` is the load generator.

It sends HTTP requests to:

```text
http://app-b:8000/work
```

The request rate can be changed without restarting the container.

Example:

```bash
curl http://localhost:8001/rate
```

Set the request rate to 3 requests per second:

```bash
curl -X POST http://localhost:8001/rate \
  -H "Content-Type: application/json" \
  -d '{"rate":3}'
```

Set it back to 1 request per second:

```bash
curl -X POST http://localhost:8001/rate \
  -H "Content-Type: application/json" \
  -d '{"rate":1}'
```

`app-a` exposes Prometheus metrics through:

```text
/metrics
```

It tracks:

* Total successful requests
* Total failed requests
* Request latency
* Active requests

---

## app-b

`app-b` is the application receiving requests from `app-a`.

The main endpoint is:

```text
/work
```

Each request performs CPU work and temporarily allocates approximately 10 MB of memory for around 2 seconds.

This behavior allows concurrent requests to increase memory usage and makes it possible to demonstrate an OOM condition.

Additional endpoints:

```text
/health
/metrics
```

Example:

```bash
curl http://localhost:8001/health
```

The application exposes metrics including:

* Total requests
* Successful requests
* Failed requests
* Request duration
* Active requests

---

## Resource Limits

The containers have resource limits configured in `docker-compose.yml`.

### app-a

```yaml
limits:
  cpus: "0.5"
  memory: 256M
```

### app-b

```yaml
limits:
  cpus: "0.25"
  memory: 128M
```

`app-b` has a deliberately small memory limit so that increasing concurrent requests can trigger an OOM condition.

The limits can be verified with:

```bash
docker inspect app-b --format 'Memory={{.HostConfig.Memory}} bytes | NanoCPUs={{.HostConfig.NanoCpus}}'
```

---

## Docker Network

All monitoring and application services use the same Docker network:

```yaml
networks:
  monitor-net:
    driver: bridge
```

Services are connected to this network using:

```yaml
networks:
  - monitor-net
```

Because they are on the same Docker network, services can communicate using their Compose service names.

Examples:

```text
app-a → app-b:8000
Prometheus → app-b:8000
Prometheus → cadvisor:8080
Grafana → prometheus:9090
```

No container IP addresses need to be configured manually.

---

## Prometheus

Prometheus collects and stores metrics from the applications and cAdvisor.

Configured targets include:

* app-a
* app-b
* cAdvisor
* nodeexporter
* Prometheus
* Pushgateway

The application scrape interval is 5 seconds.

Example Prometheus target:

```yaml
- job_name: 'app-b'
  scrape_interval: 5s
  static_configs:
    - targets: ['app-b:8000']
```

Prometheus is available on:

```text
http://localhost:9090
```

when port 9090 is published or forwarded through an SSH tunnel.

---

## cAdvisor

cAdvisor (Container Advisor) collects container-level resource metrics.

It provides information such as:

* Container CPU usage
* Container memory usage
* Container resource limits
* Network statistics
* Other container-level metrics

The monitoring flow is:

```text
Docker Containers
       ↓
    cAdvisor
       ↓
   Prometheus
       ↓
    Grafana
```

cAdvisor is exposed internally on:

```text
cadvisor:8080
```

It is intentionally not published directly to the host.

Prometheus can access it through the Docker network.

Example check:

```bash
docker exec prometheus wget -qO- http://cadvisor:8080/metrics
```

---

## Grafana

Grafana is used to visualize the metrics collected by Prometheus.

The Prometheus datasource is configured as:

```text
http://prometheus:9090
```

Grafana is available on:

```text
http://localhost:3000
```

when the port is forwarded to the local machine.

Example SSH tunnel:

```bash
ssh -L 3000:localhost:3000 devops@<VM-IP>
```

Then open:

```text
http://localhost:3000
```

---

## Important Prometheus Queries

### Request rate

```promql
sum(rate(app_a_requests_total[1m]))
```

Shows the approximate number of requests sent by `app-a` per second.

### Successful requests

```promql
sum(rate(app_a_requests_total{status="success"}[1m]))
```

### Failed requests

```promql
sum(rate(app_a_requests_total{status="failed"}[1m]))
```

### Error percentage

```promql
100 * sum(rate(app_a_requests_total{status="failed"}[1m]))
/
sum(rate(app_a_requests_total[1m]))
```

### Active requests on app-b

```promql
app_b_active_requests
```

### app-b process start time

```promql
process_start_time_seconds{job="app-b"}
```

This value changes when the application process is restarted.

### Target availability

```promql
up{job=~"app-a|app-b"}
```

A value of `1` means Prometheus can successfully scrape the target.

A value of `0` means the target could not be scraped.

---

## Running the Project

Build and start all services:

```bash
docker compose up -d --build
```

Check running containers:

```bash
docker compose ps
```

Check logs:

```bash
docker compose logs -f
```

Check a specific service:

```bash
docker compose logs -f app-b
```

---

## Load Test

Start with a low request rate:

```bash
curl -X POST http://localhost:8001/rate \
  -H "Content-Type: application/json" \
  -d '{"rate":1}'
```

Increase the load:

```bash
curl -X POST http://localhost:8001/rate \
  -H "Content-Type: application/json" \
  -d '{"rate":3}'
```

For a stronger load test, increase the rate gradually and observe:

* Request rate
* Active requests
* CPU usage
* Memory usage
* Failed requests
* Container restarts

The exact rate required to trigger OOM can vary depending on the environment.

---

## OOM and Restart Verification

The project can demonstrate an OOM condition in `app-b`.

Check the container state:

```bash
docker inspect app-b \
  --format '{{.State.ExitCode}} | OOMKilled={{.State.OOMKilled}} | RestartCount={{.RestartCount}}'
```

Example result:

```text
137 | OOMKilled=true | RestartCount=20
```

This means:

* `137` indicates the process was killed with `SIGKILL`
* `OOMKilled=true` confirms that the container was killed because of an Out-Of-Memory condition
* `RestartCount=20` shows that Docker restarted the container multiple times

The restart can also be observed through:

```promql
process_start_time_seconds{job="app-b"}
```

---

## Recovery

After demonstrating the OOM condition, reduce the request rate:

```bash
curl -X POST http://localhost:8001/rate \
  -H "Content-Type: application/json" \
  -d '{"rate":1}'
```

Check the container:

```bash
docker ps --filter name=app-b
```

The expected state is:

```text
Up
```

At a lower request rate, the application should recover and remain stable.

---

## Monitoring Flow

The complete monitoring architecture is:

```text
                 Request Load
                      │
                      ▼
                   app-a
                      │
                      │ HTTP
                      ▼
                   app-b
                      │
              ┌───────┴────────┐
              │                │
       Application         Container
         Metrics            Metrics
              │                │
              ▼                ▼
          Prometheus <───── cAdvisor
              │
              ▼
           Grafana
```

Application metrics come directly from `/metrics` endpoints.

Container resource metrics come from cAdvisor.

Prometheus collects both types of metrics.

Grafana visualizes the collected data.

---

## Expected Test Scenario

The main test scenario is:

```text
1 request/sec
      ↓
Normal operation
      ↓
Increase load
      ↓
Active requests increase
      ↓
Memory usage increases
      ↓
Reach app-b 128 MB memory limit
      ↓
OOMKilled
      ↓
app-b restarts
      ↓
app-a failures increase
      ↓
Reduce load to 1 request/sec
      ↓
app-b recovers
```

This demonstrates the relationship between application load, container resource usage, OOM behavior, failures, and recovery.

---

## Useful Docker Commands

List running containers:

```bash
docker ps
```

View all containers:

```bash
docker ps -a
```

View resource usage:

```bash
docker stats
```

View app-b logs:

```bash
docker logs app-b
```

Inspect app-b:

```bash
docker inspect app-b
```

Check Docker networks:

```bash
docker network ls
```

Inspect the project network:

```bash
docker network inspect docker-compose-prometheus-and-grafana_monitor-net
```

Stop the project:

```bash
docker compose down
```

Start it again:

```bash
docker compose up -d
```

---

## Project Structure

```text
.
├── app-a/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── app-b/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── prometheus/
│   ├── prometheus.yml
│   └── alert.rules
│
├── grafana/
│   └── provisioning/
│       ├── dashboards/
│       └── datasources/
│
├── alertmanager/
├── docker-compose.yml
└── README.md
```

---

## Summary

This project demonstrates a complete container monitoring workflow:

* Docker Compose for service orchestration
* Flask applications for generating and receiving load
* Configurable request rate
* Application-level Prometheus metrics
* cAdvisor for container resource monitoring
* Prometheus for metric collection and storage
* Grafana for visualization
* Docker CPU and memory limits
* OOM behavior and automatic container restart
* Monitoring of failures and recovery
