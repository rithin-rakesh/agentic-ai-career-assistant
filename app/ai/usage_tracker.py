import time
import threading
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional
from app.logger import logger

class AIUsageTracker:
    """
    Thread-safe tracker for Gemini AI Gateway usage metrics, latency, token consumption,
    and connection health.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AIUsageTracker, cls).__new__(cls)
                cls._instance._init_tracker()
            return cls._instance

    def _init_tracker(self):
        self.active_model: str = "gemini-2.5-flash"
        self.connection_status: str = "Offline / Mock Mode"
        self.last_reset_date: date = datetime.now(timezone.utc).date()
        self.prompts_today: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self.total_latency_ms: float = 0.0
        self.last_latency_ms: float = 0.0
        self.successful_requests: int = 0
        self.failed_requests: int = 0
        self.retry_count: int = 0
        self.last_successful_request: Optional[str] = None
        self.last_failed_request: Optional[str] = None
        self.last_error_message: Optional[str] = None
        self.quota_info: str = "Standard Free Tier / Pay-As-You-Go"

    def _check_day_rollover(self):
        today = datetime.now(timezone.utc).date()
        if today != self.last_reset_date:
            self.last_reset_date = today
            self.prompts_today = 0

    def record_request_start(self):
        with self._lock:
            self._check_day_rollover()
            self.prompts_today += 1

    def record_success(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        retries: int = 0
    ):
        with self._lock:
            self._check_day_rollover()
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            self.active_model = model
            self.connection_status = "Connected"
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self.total_tokens += (prompt_tokens + completion_tokens)
            self.last_latency_ms = round(latency_ms, 2)
            self.total_latency_ms += latency_ms
            self.successful_requests += 1
            self.retry_count += retries
            self.last_successful_request = now_iso
            self.last_error_message = None

    def record_failure(
        self,
        model: str,
        status_label: str,
        error_msg: str,
        retries: int = 0
    ):
        with self._lock:
            self._check_day_rollover()
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            self.active_model = model
            self.connection_status = status_label
            self.failed_requests += 1
            self.retry_count += retries
            self.last_failed_request = now_iso
            self.last_error_message = error_msg

    def get_summary(self) -> Dict[str, Any]:
        return self.get_usage_summary()

    def get_usage_summary(self) -> Dict[str, Any]:
        with self._lock:
            self._check_day_rollover()
            total_reqs = self.successful_requests + self.failed_requests
            avg_latency = (
                round(self.total_latency_ms / self.successful_requests, 2)
                if self.successful_requests > 0 else 0.0
            )
            return {
                "active_model": self.active_model,
                "connection_status": self.connection_status,
                "prompts_today": self.prompts_today,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
                "average_latency_ms": avg_latency,
                "last_latency_ms": self.last_latency_ms,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "last_successful_request": self.last_successful_request or "N/A",
                "last_failed_request": self.last_failed_request or "N/A",
                "retry_count": self.retry_count,
                "last_error_message": self.last_error_message or "None",
                "quota_info": self.quota_info
            }

ai_usage_tracker = AIUsageTracker()
