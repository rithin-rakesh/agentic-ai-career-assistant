import os
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple, Optional
from app.config import settings
from app.logger import logger

class EmailService:
    """
    Sends HTML notifications. Supports live SMTP connections (TLS/SSL) with retries,
    timeout handling, and a mock fallback mode when credentials are not configured.
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

        # Enable mock state if credentials are empty or MOCK_LLM is enabled
        self.is_mock = settings.MOCK_LLM or not self.username
        if self.is_mock:
            logger.info("EmailService: Operating in MOCK mode. Emails will be logged locally in data/sent_emails/.")

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
                
            logger.info(f"EmailService [MOCK]: Successfully wrote email mock layout to {file_path}")
            return True, 1, None
        except Exception as e:
            err_msg = f"EmailService [MOCK] failed to write local file: {e}"
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
        
        for attempt in range(1, self.retries + 1):
            logger.info(f"EmailService: Attempting SMTP delivery (Attempt {attempt}/{self.retries})...")
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
                
                smtp.sendmail(self.from_email, [self.to_email], msg.as_string())
                smtp.quit()
                
                logger.info(f"EmailService: SMTP email delivered successfully on attempt {attempt}")
                return True, attempt, None

            except Exception as e:
                last_error = str(e)
                logger.warning(f"EmailService: SMTP attempt {attempt} failed: {e}")
                if attempt < self.retries:
                    sleep_time = 2 ** attempt
                    logger.info(f"EmailService: Sleeping for {sleep_time} seconds before retrying...")
                    time.sleep(sleep_time)
        
        err_msg = f"EmailService: SMTP delivery failed after {self.retries} attempts. Last error: {last_error}"
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
            return False, "SMTP Host and Username must be provided."

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

            smtp.quit()
            return True, "SMTP connection and authentication successful."
        except Exception as e:
            logger.error(f"SMTP Connection validation failed for {target_host}:{target_port}: {e}")
            return False, f"SMTP Connection failed: {e}"

    def send_test_email(self, to_email: str, host: str = None, port: int = None, username: str = None, password: str = None) -> Tuple[bool, str]:
        """
        Sends a test email to verify SMTP delivery.
        """
        target_host = host or self.host
        target_port = port or self.port
        target_user = username if username is not None else self.username
        target_pass = password if password is not None else self.password
        sender = target_user or self.from_email or "assistant@agenticjobsearch.com"

        # If operating in mock mode or credentials missing, use mock file generator
        if self.is_mock or not target_user or not target_pass:
            html = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #0f172a; color: #f8fafc; border-radius: 8px;">
                <h2 style="color: #6366f1;">[MOCK] Test Email from Agentic AI Career Assistant</h2>
                <p>Mock email delivery executed. Emails logged locally in data/sent_emails/.</p>
                <p><strong>Recipient:</strong> {to_email}</p>
            </div>
            """
            ok, attempts, err = self._send_mock_email("Test Email — Agentic AI Career Assistant", html)
            return ok, "Mock test email generated successfully in data/sent_emails/." if ok else f"Mock email failed: {err}"

        html = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #0f172a; color: #f8fafc; border-radius: 8px;">
            <h2 style="color: #6366f1;">Test Email from Agentic AI Career Assistant</h2>
            <p>Your Gmail / SMTP configuration has been validated successfully!</p>
            <p><strong>SMTP Host:</strong> {target_host}</p>
            <p><strong>Port:</strong> {target_port}</p>
            <p><strong>Sender:</strong> {sender}</p>
            <hr style="border: 1px solid #334155;">
            <p style="font-size: 12px; color: #94a3b8;">This is an automated test message sent from your AI Career Assistant dashboard.</p>
        </div>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Test Email — Agentic AI Career Assistant"
        msg["From"] = sender
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))

        try:
            if target_port == 465:
                smtp = smtplib.SMTP_SSL(target_host, target_port, timeout=self.timeout)
            else:
                smtp = smtplib.SMTP(target_host, target_port, timeout=self.timeout)
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()

            smtp.login(target_user, target_pass)
            smtp.sendmail(sender, [to_email], msg.as_string())
            smtp.quit()
            return True, "Test email sent successfully."
        except Exception as e:
            logger.error(f"Failed to send test email: {e}")
            return False, f"Failed to send test email: {e}"

