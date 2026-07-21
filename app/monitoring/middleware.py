import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.monitoring.metrics import HTTP_REQUEST_COUNT, HTTP_REQUEST_LATENCY
from app.logger import logger

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that ensures every request carries a unique Correlation ID (X-Correlation-ID).
    If missing in incoming headers, generates a new UUID4.
    Also records request latency and status codes for Prometheus monitoring.
    """
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id

        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
            duration = time.perf_counter() - start_time
            
            status_code = str(response.status_code)
            endpoint = request.url.path
            method = request.method

            # Record Prometheus metrics
            HTTP_REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            HTTP_REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

            response.headers["X-Correlation-ID"] = correlation_id
            return response
        except Exception as exc:
            duration = time.perf_counter() - start_time
            HTTP_REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status_code="500").inc()
            HTTP_REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path).observe(duration)
            logger.error(f"Unhandled exception in request [{correlation_id}]: {exc}", exc_info=True)
            raise exc
