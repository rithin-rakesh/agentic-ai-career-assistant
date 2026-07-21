import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any

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
            "message": record.getMessage(),
        }
        
        # Include exception details if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        # Include extra fields if added to the log record
        # Avoid overriding default log record attributes
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message"
            }:
                log_data[key] = value
                
        return json.dumps(log_data)

def setup_logging(level: str = "INFO", use_json: bool = False) -> logging.Logger:
    """
    Sets up the structured logging configuration.
    Redirects stdout logs to avoid standard error streaming if preferred.
    """
    root_logger = logging.getLogger()
    
    # Remove existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    root_logger.setLevel(level.upper())
    
    # Choose formatter
    if use_json:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
    # Setup console handler redirecting to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Return configured logger for the application
    return logging.getLogger("job_agent")

# Initialize a default logger instance
logger = setup_logging()
