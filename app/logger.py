import logging
import json
import sys
import os
import re
from datetime import datetime, timezone
from typing import Any

# Force Python environment IO encoding to UTF-8
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|password|pwd|pass|jwt[_-]?secret|secret[_-]?key|smtp[_-]?password|authorization|bearer|token)=["\']?([^"\'\s&]+)["\']?'),
    re.compile(r'Bearer\s+[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*'),
    re.compile(r'AIzaSy[A-Za-z0-9-_]{33}'),
    re.compile(r'eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*'),
]

def sanitize_secret_text(text: str) -> str:
    """
    Masks sensitive information in text string.
    Replaces matched credentials, bearer tokens, or API keys with masked placeholders.
    """
    if not isinstance(text, str):
        return text

    sanitized = text

    # Pattern 1: key=val or key: val
    for pattern in SECRET_PATTERNS:
        if "Bearer" in pattern.pattern:
            sanitized = pattern.sub("Bearer ••••••••", sanitized)
        elif "AIzaSy" in pattern.pattern or "eyJ" in pattern.pattern:
            sanitized = pattern.sub("••••••••", sanitized)
        else:
            def replacer(match):
                prefix = match.group(1)
                return f"{prefix}=••••••••"
            sanitized = pattern.sub(replacer, sanitized)

    return sanitized

class SecretMaskingFilter(logging.Filter):
    """
    Logging filter that automatically redacts sensitive data (API keys, passwords, JWT tokens)
    from all log records before emission.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_secret_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: sanitize_secret_text(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(sanitize_secret_text(str(a)) if isinstance(a, str) else a for a in record.args)
        return True

class JsonFormatter(logging.Formatter):
    """
    Custom logging formatter that outputs log messages in JSON format.
    Useful for production environments, log aggregation tools, and parsing.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_secret_text(record.getMessage()),
        }
        
        # Include exception details if present
        if record.exc_info:
            log_data["exception"] = sanitize_secret_text(self.formatException(record.exc_info))
            
        # Include extra fields if added to the log record
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message"
            }:
                if isinstance(value, str):
                    log_data[key] = sanitize_secret_text(value)
                else:
                    log_data[key] = value
                
        return json.dumps(log_data, ensure_ascii=False)

def setup_logging(level: str = "INFO", use_json: bool = False) -> logging.Logger:
    """
    Sets up the structured logging configuration with SecretMaskingFilter enabled.
    Redirects stdout logs with UTF-8 safety.
    """
    root_logger = logging.getLogger()
    
    # Remove existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    root_logger.setLevel(level.upper())
    
    # Choose formatter
    if use_json or os.getenv("LOG_FORMAT", "").lower() == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
    # Setup console handler redirecting to stdout with UTF-8 safety
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(SecretMaskingFilter())
    root_logger.addHandler(handler)
    
    return logging.getLogger("job_agent")

# Initialize a default logger instance
logger = setup_logging()
