from app.config import settings
from app.logger import logger

def init_sentry():
    """
    Initializes Sentry error tracking if SENTRY_DSN is configured.
    """
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.logging import LoggingIntegration

            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                integrations=[
                    FastApiIntegration(),
                    LoggingIntegration(level=None, event_level=None)
                ],
                traces_sample_rate=0.2,
                environment="production"
            )
            logger.info("Sentry SDK error monitoring successfully initialized.")
        except Exception as e:
            logger.warning(f"Failed to initialize Sentry SDK: {e}")
    else:
        logger.info("SENTRY_DSN not provided. Sentry monitoring is disabled.")
