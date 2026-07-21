import time
from fastapi import Response
from app.logger import logger

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client package not installed. Prometheus metrics will be simulated.")

    class DummyMetric:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def inc(self, amount=1): pass
        def observe(self, amount): pass
        def set(self, value): pass

    Counter = Histogram = Gauge = DummyMetric
    CONTENT_TYPE_LATEST = "text/plain"
    def generate_latest(): return b"# Prometheus client not installed\n"

# HTTP Request Metrics
HTTP_REQUEST_COUNT = Counter(
    "job_agent_http_requests_total",
    "Total HTTP requests received by API",
    ["method", "endpoint", "status_code"]
)

HTTP_REQUEST_LATENCY = Histogram(
    "job_agent_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"]
)

# Agent Execution Metrics
AGENT_EXECUTION_COUNT = Counter(
    "job_agent_agent_executions_total",
    "Total LangGraph agent executions",
    ["agent_name", "status"]
)

AGENT_EXECUTION_LATENCY = Histogram(
    "job_agent_agent_execution_duration_seconds",
    "LangGraph agent execution duration in seconds",
    ["agent_name"]
)

# Business Metrics
JOBS_COLLECTED_TOTAL = Counter(
    "job_agent_jobs_collected_total",
    "Total raw jobs collected across web sources",
    ["source"]
)

JOBS_MATCHED_HIGH_PRIORITY = Counter(
    "job_agent_jobs_matched_high_priority_total",
    "Total high priority job recommendations generated"
)

PREFERENCE_LEARNING_CYCLES = Counter(
    "job_agent_preference_learning_cycles_total",
    "Total self-improvement preference learning iterations executed"
)

SYSTEM_HEALTH_GAUGE = Gauge(
    "job_agent_system_health_status",
    "Overall system health status (1 = Healthy, 0 = Unhealthy)"
)

def metrics_response() -> Response:
    """
    Returns current Prometheus metrics formatted for scraping.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
