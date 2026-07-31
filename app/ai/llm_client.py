import os
import re
import time
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.config import settings
from app.logger import logger
from app.ai.usage_tracker import ai_usage_tracker
from app.monitoring.metrics import (
    GEMINI_REQUESTS_TOTAL,
    GEMINI_REQUEST_LATENCY,
    GEMINI_RETRIES_TOTAL
)

def _clean_json_response(raw_text: str) -> str:
    """
    Sanitizes LLM outputs by removing markdown code block tags and extra whitespace.
    """
    if not raw_text:
        return ""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def resolve_gemini_api_key(passed_key: Optional[str] = None) -> str:
    """
    Resolves the Gemini API Key adhering to strict fallback precedence:
    1. Passed API key (if valid/unmasked)
    2. Database settings / Application Memory (ai_settings.gemini_api_key)
    3. Environment variable (GEMINI_API_KEY) / settings
    4. Empty string (triggers MockLLM fallback)
    """
    # 1. Direct explicit parameter
    if passed_key and not passed_key.startswith("••••") and passed_key != "********" and len(passed_key.strip()) > 5:
        return passed_key.strip()

    # 2. Database Settings / Memory Manager
    try:
        from app.memory.application_memory import ApplicationMemoryManager
        mem_key = ApplicationMemoryManager().memory.get("ai_settings", {}).get("gemini_api_key", "")
        if mem_key and not mem_key.startswith("••••") and mem_key != "********" and len(mem_key.strip()) > 5:
            return mem_key.strip()
    except Exception:
        pass

    # 3. Environment Variable / Settings
    env_key = os.getenv("GEMINI_API_KEY", getattr(settings, "GEMINI_API_KEY", ""))
    if env_key and not env_key.startswith("••••") and env_key != "********" and len(env_key.strip()) > 5:
        return env_key.strip()

    return ""

class BaseLLM(ABC):
    """
    Abstract contract defining the core LLM execution interface.
    """
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, response_format: Optional[Dict[str, Any]] = None) -> str:
        """
        Submits system and user prompts to the LLM and returns sanitized string response.
        """
        pass

class MockLLM(BaseLLM):
    """
    Offline local simulation fallback when Gemini API key is missing or invalid.
    """
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or getattr(settings, "MODEL_NAME", "gemini-2.5-flash")
        logger.info(f"MockLLM initialized in OFFLINE mode for model '{self.model_name}'.")

    def generate(self, system_prompt: str, user_prompt: str, response_format: Optional[Dict[str, Any]] = None) -> str:
        logger.info("Executing local MockLLM generation.")
        time.sleep(0.1)
        ai_usage_tracker.record_request_start()
        
        user_lower = user_prompt.lower()

        # Parse Resume request
        if "resume text" in user_lower or "resume_text" in user_lower:
            res = json.dumps({
                "skills": ["Python", "SQL", "Machine Learning", "PyTorch", "FastAPI", "Docker", "Qdrant"],
                "programming_languages": ["Python", "SQL", "Bash"],
                "frameworks": ["FastAPI", "Flask", "PyTorch", "LangGraph"],
                "experience": [{
                    "company": "AI Tech Solutions",
                    "role": "AI Engineer",
                    "years": 2.5,
                    "description": "Developed LLM and RAG agents with Qdrant and FastAPI."
                }],
                "education": [{
                    "institution": "University of Technology",
                    "degree": "B.S. Computer Science",
                    "year": 2023
                }],
                "projects": [{
                    "title": "Agentic Career Assistant",
                    "description": "Autonomous job application system using LangGraph and Gemini.",
                    "technologies": ["Python", "Gemini API", "FastAPI", "Qdrant"]
                }],
                "certifications": ["Google Cloud Certified Cloud Engineer"]
            })
            ai_usage_tracker.record_success(self.model_name, prompt_tokens=150, completion_tokens=120, latency_ms=100.0)
            return res

        # Evaluate Job request
        if "evaluate this job" in user_lower or "job details" in user_lower:
            if "senior" in user_lower or "lead" in user_lower or "8+ years" in user_lower:
                res = json.dumps({
                    "match_score": 62,
                    "should_apply": False,
                    "priority": "Medium",
                    "summary": "Candidate meets core ML skills but has fewer years of senior staff leadership than required.",
                    "strengths": ["Python", "PyTorch", "FastAPI"],
                    "missing_skills": ["Staff Leadership", "Large Scale Distributed Systems"],
                    "learning_effort": "High",
                    "confidence": 0.85
                })
            else:
                res = json.dumps({
                    "match_score": 92,
                    "should_apply": True,
                    "priority": "High",
                    "summary": "Strong alignment with candidate's Python, FastAPI, and GenAI skill set.",
                    "strengths": ["Python", "FastAPI", "Qdrant", "RAG", "LangGraph"],
                    "missing_skills": ["Kubernetes"],
                    "learning_effort": "Low",
                    "confidence": 0.95
                })
            ai_usage_tracker.record_success(self.model_name, prompt_tokens=200, completion_tokens=150, latency_ms=120.0)
            return res

        # Default JSON mock response
        res = json.dumps({"status": "simulated", "message": "MockLLM execution completed."})
        ai_usage_tracker.record_success(self.model_name, prompt_tokens=50, completion_tokens=20, latency_ms=50.0)
        return res

class GeminiClient(BaseLLM):
    """
    Production-grade Google Gemini LLM API client supporting gemini-2.5-flash and gemini-2.5-pro.
    Implements connection pooling, exponential backoff retries, timeout handling, and Prometheus metrics.
    """
    _shared_client = None
    _shared_key = None
    _llm_cache: Dict[str, str] = {}
    provider_label = "Google Gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None
    ):
        self.api_key = resolve_gemini_api_key(api_key)
        self.model_name = model_name or getattr(settings, "MODEL_NAME", "gemini-2.5-flash")
        if self.model_name not in ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro"):
            self.model_name = "gemini-2.5-flash"
        self.temperature = temperature if temperature is not None else getattr(settings, "TEMPERATURE", 0.2)
        self.max_tokens = max_tokens or getattr(settings, "MAX_TOKENS", 2048)
        self.timeout = timeout or getattr(settings, "REQUEST_TIMEOUT", 30)
        self.max_retries = getattr(settings, "MAX_RETRIES", 3)

        if not self.api_key:
            self.mock_fallback = MockLLM(model_name=self.model_name)
        else:
            self.mock_fallback = None
            self._init_google_client()

    def _init_google_client(self):
        try:
            from google import genai
            if GeminiClient._shared_client is None or GeminiClient._shared_key != self.api_key:
                GeminiClient._shared_client = genai.Client(api_key=self.api_key)
                GeminiClient._shared_key = self.api_key
            self.client = GeminiClient._shared_client
        except Exception as e:
            logger.error(f"Failed to initialize google.genai Client: {e}", exc_info=True)
            self.mock_fallback = MockLLM(model_name=self.model_name)

    def generate(self, system_prompt: str, user_prompt: str, response_format: Optional[Dict[str, Any]] = None) -> str:
        if self.mock_fallback:
            return self.mock_fallback.generate(system_prompt, user_prompt, response_format)

        import hashlib
        cache_key = hashlib.sha256(f"{self.model_name}:{system_prompt}:{user_prompt}".encode('utf-8')).hexdigest()
        if cache_key in GeminiClient._llm_cache:
            logger.info(f"GeminiClient: Cache hit for key {cache_key[:8]}... Returning cached result.")
            return GeminiClient._llm_cache[cache_key]

        ai_usage_tracker.record_request_start()
        start_time = time.perf_counter()
        backoff = 2.0
        last_error = None
        retries_occurred = 0

        for attempt in range(1, self.max_retries + 1):
            try:
                from google.genai import types

                combined_contents = f"{system_prompt}\n\nUser Input:\n{user_prompt}"
                config_kwargs = {
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                }
                
                if response_format or "json" in system_prompt.lower():
                    config_kwargs["response_mime_type"] = "application/json"

                config = types.GenerateContentConfig(**config_kwargs)

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=combined_contents,
                    config=config
                )

                latency_ms = (time.perf_counter() - start_time) * 1000.0
                raw_text = response.text if response and hasattr(response, "text") else ""
                clean_text = _clean_json_response(raw_text)

                if clean_text:
                    GeminiClient._llm_cache[cache_key] = clean_text

                usage = getattr(response, "usage_metadata", None)
                p_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
                c_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

                # Usage tracker record
                ai_usage_tracker.record_success(
                    model=self.model_name,
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    latency_ms=latency_ms,
                    retries=retries_occurred
                )

                # Prometheus metrics (without token accounting for Step 1)
                GEMINI_REQUESTS_TOTAL.labels(provider=self.provider_label, model=self.model_name, status="success").inc()
                GEMINI_REQUEST_LATENCY.labels(provider=self.provider_label, model=self.model_name).observe(latency_ms / 1000.0)

                logger.info(f"Gemini API request succeeded ({self.model_name}) in {latency_ms:.2f}ms.")
                return clean_text

            except Exception as e:
                last_error = str(e).encode("utf-8", errors="replace").decode("utf-8")
                retries_occurred += 1
                GEMINI_RETRIES_TOTAL.labels(provider=self.provider_label, model=self.model_name).inc()
                
                err_lower = last_error.lower()
                status_label = "Rate Limited" if "429" in err_lower or "resource_exhausted" in err_lower else (
                    "Quota Exceeded" if "quota" in err_lower else (
                    "Timeout" if "timeout" in err_lower or "deadline" in err_lower else (
                    "Invalid API Key" if "api_key" in err_lower or "unauthenticated" in err_lower else "API Error"
                )))

                logger.warning(f"Gemini API attempt {attempt}/{self.max_retries} failed ({status_label}): {e}")

                if attempt == self.max_retries:
                    ai_usage_tracker.record_failure(
                        model=self.model_name,
                        status_label=status_label,
                        error_msg=last_error,
                        retries=retries_occurred
                    )
                    GEMINI_REQUESTS_TOTAL.labels(provider=self.provider_label, model=self.model_name, status="failure").inc()
                    logger.error(f"Gemini API failed after {self.max_retries} attempts: {last_error}. Falling back to MockLLM.")
                    mock_fallback = MockLLM(model_name=self.model_name)
                    return mock_fallback.generate(system_prompt, user_prompt, response_format)

                sleep_time = backoff ** attempt
                time.sleep(sleep_time)

        return json.dumps({"error": "Gemini API request failed", "details": last_error})

# Alias for backwards compatibility with any existing imports expecting OpenAIClient
class OpenAIClient(GeminiClient):
    pass

def get_llm_client(api_key: Optional[str] = None, model_name: Optional[str] = None) -> BaseLLM:
    """
    Factory function returning a GeminiClient if an API key is available via resolution order,
    or MockLLM if unconfigured or offline.
    """
    key = resolve_gemini_api_key(api_key)
    if not key:
        return MockLLM(model_name=model_name)
    return GeminiClient(api_key=key, model_name=model_name)
