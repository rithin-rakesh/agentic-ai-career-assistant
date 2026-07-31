import os
import time
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple, Optional, Dict, Any
from app.config import settings
from app.logger import logger
from app.monitoring.metrics import EMAILS_SENT_TOTAL, EMAILS_FAILED_TOTAL, SMTP_LATENCY_SECONDS

class EmailService:
    """
    Sends HTML notifications. Supports live SMTP connections (TLS/SSL) with retries,
    timeout handling, Prometheus telemetry, structured logging, and a mock fallback
    mode when explicitly enabled or when credentials are not configured.
    """
    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.FROM_EMAIL
        self.to_email = settings.TO_EMAIL
        self.retries = settings.SMTP_RETRIES
        self.timeout = settings.SMTP_TIMEOUT

        # Determine delivery mode based on EMAIL_MODE config and credentials
        email_mode_cfg = getattr(settings, "EMAIL_MODE", "SMTP").upper()
        has_credentials = bool(self.username and self.password)

        if email_mode_cfg == "MOCK":
            self.mode = "MOCK"
            self.is_mock = True
            self.mock_reason = "Explicitly configured EMAIL_MODE=MOCK"
        elif not has_credentials:
            self.mode = "MOCK"
            self.is_mock = True
            missing_parts = []
            if not self.username: missing_parts.append("SMTP_USERNAME")
            if not self.password: missing_parts.append("SMTP_PASSWORD")
            self.mock_reason = f"Missing SMTP credentials ({', '.join(missing_parts)})"
        else:
            self.mode = "SMTP"
            self.is_mock = False
            self.mock_reason = None

        logger.info(
            f"EmailService initialized: DeliveryMode={self.mode}, "
            f"Host={self.host}:{self.port}, User={self.username or 'None'}, "
            f"Reason={self.mock_reason or 'Valid credentials configured'}"
        )

    def send_html_email(self, subject: str, html_content: str) -> Tuple[bool, int, Optional[str]]:
        """
        Sends an HTML email. If in mock mode, writes HTML to a local file.
        Returns: (success: bool, attempts_made: int, error_message: Optional[str])
        """
        if self.is_mock:
            return self._send_mock_email(subject, html_content)

        return self._send_smtp_email(subject, html_content)

    def _send_mock_email(self, subject: str, html_content: str) -> Tuple[bool, int, Optional[str]]:
        """
        Saves the rendered HTML to a local file inside data/sent_emails/ to mock delivery.
        """
        start_time = time.perf_counter()
        try:
            timestamp = int(time.time())
            safe_subject = "".join(c for c in subject if c.isalnum() or c in (" ", "_", "-")).rstrip()
            safe_subject = safe_subject.replace(" ", "_")
            
            output_dir = os.path.join(settings.BASE_DIR, "data", "sent_emails")
            os.makedirs(output_dir, exist_ok=True)
            
            file_name = f"email_{timestamp}_{safe_subject}.html"
            file_path = os.path.join(output_dir, file_name)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            duration = time.perf_counter() - start_time
            SMTP_LATENCY_SECONDS.labels(mode="MOCK").observe(duration)
            EMAILS_SENT_TOTAL.labels(mode="MOCK", status="success").inc()

            logger.info(f"EmailService [MOCK]: Successfully wrote email layout to {file_path} in {duration:.4f}s")
            return True, 1, None
        except Exception as e:
            duration = time.perf_counter() - start_time
            err_msg = f"EmailService [MOCK] failed to write local file: {e}"
            EMAILS_FAILED_TOTAL.labels(mode="MOCK", reason="file_write_error").inc()
            EMAILS_SENT_TOTAL.labels(mode="MOCK", status="failed").inc()
            logger.error(err_msg, exc_info=True)
            return False, 1, err_msg

    def _send_smtp_email(self, subject: str, html_content: str) -> Tuple[bool, int, Optional[str]]:
        """
        Sends email using active SMTP connections, handling authentication, TLS, and retries.
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = self.to_email
        msg.attach(MIMEText(html_content, "html"))

        last_error = None
        start_time = time.perf_counter()
        
        for attempt in range(1, self.retries + 1):
            logger.info(
                f"EmailService [SMTP]: Attempting delivery to {self.to_email} "
                f"via {self.host}:{self.port} (Attempt {attempt}/{self.retries})..."
            )
            try:
                # 1. Establish connection
                if self.port == 465:
                    smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
                else:
                    smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.ehlo()

                # 2. Login & Send
                if self.username and self.password:
                    smtp.login(self.username, self.password)
                    logger.debug(f"EmailService [SMTP]: Login successful for {self.username}")
                
                send_res = smtp.sendmail(self.from_email, [self.to_email], msg.as_string())
                smtp.quit()
                
                duration = time.perf_counter() - start_time
                SMTP_LATENCY_SECONDS.labels(mode="SMTP").observe(duration)
                EMAILS_SENT_TOTAL.labels(mode="SMTP", status="success").inc()

                logger.info(
                    f"EmailService [SMTP]: Email delivered successfully on attempt {attempt} "
                    f"in {duration:.4f}s. Server response: {send_res or 'Accepted'}"
                )
                return True, attempt, None

            except Exception as e:
                last_error = str(e)
                logger.warning(f"EmailService [SMTP]: Delivery attempt {attempt}/{self.retries} failed on {self.host}:{self.port}: {e}")
                if attempt < self.retries:
                    sleep_time = 2 ** attempt
                    logger.info(f"EmailService [SMTP]: Backoff sleep for {sleep_time}s before retry...")
                    time.sleep(sleep_time)
        
        duration = time.perf_counter() - start_time
        err_msg = f"EmailService [SMTP]: Delivery failed after {self.retries} attempts. Last error: {last_error}"
        EMAILS_FAILED_TOTAL.labels(mode="SMTP", reason="smtp_delivery_failure").inc()
        EMAILS_SENT_TOTAL.labels(mode="SMTP", status="failed").inc()
        logger.error(err_msg)
        return False, self.retries, err_msg

    def validate_connection(self, host: str = None, port: int = None, username: str = None, password: str = None) -> Tuple[bool, str]:
        """
        Tests the SMTP server connection, STARTTLS handshake, and login without sending an email.
        """
        target_host = host or self.host
        target_port = port or self.port
        target_user = username or self.username
        target_pass = password or self.password

        if not target_host or not target_user:
            msg = "SMTP Host and Username must be provided for connection validation."
            logger.warning(f"EmailService: Connection validation failed - {msg}")
            return False, msg

        logger.info(f"EmailService: Validating connection to {target_host}:{target_port} with user {target_user}...")
        try:
            if target_port == 465:
                smtp = smtplib.SMTP_SSL(target_host, target_port, timeout=self.timeout)
            else:
                smtp = smtplib.SMTP(target_host, target_port, timeout=self.timeout)
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()

            if target_user and target_pass:
                smtp.login(target_user, target_pass)
                logger.info(f"EmailService: Authentication handshake successful for {target_user}")

            smtp.quit()
            return True, "SMTP connection and authentication successful."
        except Exception as e:
            logger.error(f"EmailService: Connection validation failed for {target_host}:{target_port}: {e}")
            return False, f"SMTP Connection failed: {e}"

    def send_test_email(
        self,
        to_email: str,
        host: str = None,
        port: int = None,
        username: str = None,
        password: str = None,
        subject: str = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Sends a test email to verify delivery mode (SMTP vs MOCK).
        Returns: (success: bool, message: str, details_dict: dict)
        """
        target_host = host or self.host
        target_port = port or self.port
        target_user = username if username is not None else self.username
        target_pass = password if password is not None else self.password
        sender = target_user or self.from_email or "assistant@agenticjobsearch.com"
        email_subject = subject or "Test Email — Agentic AI Career Assistant"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check if test email should run in MOCK mode
        email_mode_cfg = getattr(settings, "EMAIL_MODE", "SMTP").upper()
        use_mock = email_mode_cfg == "MOCK" or not (target_user and target_pass)

        if use_mock:
            fallback_reason = "Explicitly configured EMAIL_MODE=MOCK" if email_mode_cfg == "MOCK" else "Missing target SMTP credentials"
            logger.info(f"EmailService: Dispatching test email in MOCK mode. Reason: {fallback_reason}")
            
            html = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #0f172a; color: #f8fafc; border-radius: 8px;">
                <h2 style="color: #6366f1;">[MOCK] Test Email from Agentic AI Career Assistant</h2>
                <p>Mock email delivery executed. Emails logged locally in data/sent_emails/.</p>
                <p><strong>Recipient:</strong> {to_email}</p>
                <p><strong>Reason:</strong> {fallback_reason}</p>
            </div>
            """
            ok, attempts, err = self._send_mock_email(email_subject, html)
            msg = "Mock test email generated successfully in data/sent_emails/." if ok else f"Mock email failed: {err}"
            
            details = {
                "status": "success" if ok else "error",
                "message": msg,
                "recipient": to_email,
                "subject": email_subject,
                "timestamp": now_iso,
                "delivery_mode": "MOCK",
                "acceptance_status": "Mocked" if ok else "Failed",
                "mock_reason": fallback_reason
            }
            return ok, msg, details

        # Real SMTP Delivery
        logger.info(f"EmailService: Dispatching live test email to {to_email} via {target_host}:{target_port}...")
        html = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #0f172a; color: #f8fafc; border-radius: 8px;">
            <h2 style="color: #6366f1;">Test Email from Agentic AI Career Assistant</h2>
            <p>Your Gmail / SMTP configuration has been validated and live delivery is operating successfully!</p>
            <p><strong>SMTP Host:</strong> {target_host}</p>
            <p><strong>Port:</strong> {target_port}</p>
            <p><strong>Sender:</strong> {sender}</p>
            <p><strong>Recipient:</strong> {to_email}</p>
            <hr style="border: 1px solid #334155;">
            <p style="font-size: 12px; color: #94a3b8;">This is an automated test message sent from your AI Career Assistant dashboard.</p>
        </div>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = email_subject
        msg["From"] = sender
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))

        start_time = time.perf_counter()
        try:
            if target_port == 465:
                smtp = smtplib.SMTP_SSL(target_host, target_port, timeout=self.timeout)
            else:
                smtp = smtplib.SMTP(target_host, target_port, timeout=self.timeout)
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()

            smtp.login(target_user, target_pass)
            send_response = smtp.sendmail(sender, [to_email], msg.as_string())
            smtp.quit()

            duration = time.perf_counter() - start_time
            SMTP_LATENCY_SECONDS.labels(mode="SMTP").observe(duration)
            EMAILS_SENT_TOTAL.labels(mode="SMTP", status="success").inc()

            succ_msg = "Live SMTP test email sent successfully."
            logger.info(f"EmailService [SMTP]: Test email delivered to {to_email} in {duration:.4f}s. Server response: {send_response or 'Accepted'}")
            
            details = {
                "status": "success",
                "message": succ_msg,
                "recipient": to_email,
                "subject": email_subject,
                "timestamp": now_iso,
                "delivery_mode": "SMTP",
                "acceptance_status": "Accepted",
                "smtp_response": str(send_response) if send_response else "250 OK"
            }
            return True, succ_msg, details

        except Exception as e:
            duration = time.perf_counter() - start_time
            err_msg = f"Failed to send SMTP test email: {e}"
            EMAILS_FAILED_TOTAL.labels(mode="SMTP", reason="test_email_failed").inc()
            EMAILS_SENT_TOTAL.labels(mode="SMTP", status="failed").inc()
            logger.error(f"EmailService [SMTP]: Test email failed to {to_email} on {target_host}:{target_port}: {e}")

            details = {
                "status": "error",
                "message": err_msg,
                "recipient": to_email,
                "subject": email_subject,
                "timestamp": now_iso,
                "delivery_mode": "SMTP",
                "acceptance_status": "Failed",
                "error": str(e)
            }
            return False, err_msg, details
