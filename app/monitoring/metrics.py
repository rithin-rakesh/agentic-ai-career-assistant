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

# Gemini LLM Metrics
GEMINI_REQUESTS_TOTAL = Counter(
    "job_agent_gemini_requests_total",
    "Total Gemini LLM API calls",
    ["provider", "model", "status"]
)

GEMINI_REQUEST_LATENCY = Histogram(
    "job_agent_gemini_request_duration_seconds",
    "Gemini API call latency in seconds",
    ["provider", "model"]
)

GEMINI_RETRIES_TOTAL = Counter(
    "job_agent_gemini_retries_total",
    "Total Gemini API retries triggered",
    ["provider", "model"]
)

PREFERENCE_LEARNING_CYCLES = Counter(
    "job_agent_preference_learning_cycles_total",
    "Total self-improvement preference learning iterations executed"
)

# Email Infrastructure Metrics (Phase 2.3)
EMAILS_SENT_TOTAL = Counter(
    "emails_sent_total",
    "Total emails sent across delivery modes",
    ["mode", "status"]
)

EMAILS_FAILED_TOTAL = Counter(
    "emails_failed_total",
    "Total email delivery failures",
    ["mode", "reason"]
)

SMTP_LATENCY_SECONDS = Histogram(
    "smtp_latency_seconds",
    "SMTP delivery latency in seconds",
    ["mode"]
)

SYSTEM_HEALTH_GAUGE = Gauge(
    "job_agent_system_health_status",
    "Overall system health status (1 = Healthy, 0 = Unhealthy)"
)

# Live Job Intelligence Metrics (Phase 2.4)
COLLECTOR_REQUESTS_TOTAL = Counter(
    "collector_requests_total",
    "Total requests executed by job collectors across sources",
    ["collector", "status"]
)

COLLECTOR_LATENCY_SECONDS = Histogram(
    "collector_latency_seconds",
    "Latency of job collector requests in seconds",
    ["collector"]
)

JOBS_FILTERED_TOTAL = Counter(
    "jobs_filtered_total",
    "Total jobs filtered out by smart screening rules",
    ["reason"]
)

JOBS_RANKED_TOTAL = Counter(
    "jobs_ranked_total",
    "Total jobs assigned ranking priority levels",
    ["priority"]
)

DUPLICATE_JOBS_TOTAL = Counter(
    "duplicate_jobs_total",
    "Total duplicate job listings detected and excluded",
    ["reason"]
)

# End-to-End Pipeline Reliability Metrics (Phase 2.5)
PIPELINE_RUNS_TOTAL = Counter(
    "pipeline_runs_total",
    "Total autonomous pipeline execution runs",
    ["status"]
)

PIPELINE_FAILURES_TOTAL = Counter(
    "pipeline_failures_total",
    "Total pipeline node/stage failures",
    ["stage"]
)

PIPELINE_DURATION_SECONDS = Histogram(
    "pipeline_duration_seconds",
    "Autonomous pipeline total execution duration in seconds"
)

PIPELINE_CURRENT_STAGE = Gauge(
    "pipeline_current_stage",
    "Numeric index of active pipeline stage"
)

SCHEDULER_LAST_SUCCESS = Gauge(
    "scheduler_last_success",
    "Timestamp of last successful scheduler execution"
)

SCHEDULER_LAST_FAILURE = Gauge(
    "scheduler_last_failure",
    "Timestamp of last failed scheduler execution"
)

if PROMETHEUS_AVAILABLE:
    MATCH_SCORE_DISTRIBUTION = Histogram(
        "match_score_distribution",
        "Distribution of AI match scores for job opportunities",
        buckets=[0, 20, 40, 60, 80, 100]
    )
else:
    MATCH_SCORE_DISTRIBUTION = DummyMetric()

def metrics_response() -> Response:
    """
    Returns current Prometheus metrics formatted for scraping.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
