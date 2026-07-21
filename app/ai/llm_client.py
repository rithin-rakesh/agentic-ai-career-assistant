import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.config import settings
from app.logger import logger

class BaseLLM(ABC):
    """
    Abstract interface defining the LLM connection contract.
    Ensures swaps to Anthropic or Google Gemini are possible without rewriting business logic.
    """
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, response_format: Optional[Dict[str, Any]] = None) -> str:
        """
        Submits prompts to the LLM and returns the raw response string.
        """
        pass

class OpenAIClient(BaseLLM):
    """
    OpenAI API client adapter implementing BaseLLM.
    Equipped with a simulated mock fallback state to bypass API key requirements for developers.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model_name = settings.MODEL_NAME
        self.temperature = settings.TEMPERATURE
        self.max_tokens = settings.MAX_TOKENS
        self.timeout = settings.REQUEST_TIMEOUT
        self.mock_mode = settings.MOCK_LLM or not self.api_key

        if self.mock_mode:
            logger.info("OpenAIClient initialized in MOCK mode. API requests will be simulated locally.")
        else:
            logger.info(f"OpenAIClient initialized. Target model: {self.model_name}")

    def generate(self, system_prompt: str, user_prompt: str, response_format: Optional[Dict[str, Any]] = None) -> str:
        """
        Executes a prompt completion. Implements resilient exponential backoff retry cycles on rate limits or timeouts.
        """
        if self.mock_mode:
            return self._simulate_generation(system_prompt, user_prompt)

        # Import openai inside method to allow execution if the package hasn't loaded immediately elsewhere
        from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError
        
        client = OpenAI(api_key=self.api_key)
        
        max_retries = 3
        backoff = 2  # Exponential backoff factor
        
        logger.info(f"Submitting prompt to OpenAI API (model: {self.model_name}).")
        start_time = time.perf_counter()
        
        for attempt in range(1, max_retries + 1):
            try:
                # Use correct model format arguments
                response = client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    response_format=response_format,
                    timeout=self.timeout
                )
                
                duration = time.perf_counter() - start_time
                tokens_used = response.usage.total_tokens if response.usage else 0
                
                logger.info(
                    f"LLM request completed in {duration:.2f} seconds. "
                    f"Token usage: Prompt={response.usage.prompt_tokens if response.usage else 0}, "
                    f"Completion={response.usage.completion_tokens if response.usage else 0}, "
                    f"Total={tokens_used}"
                )
                
                return response.choices[0].message.content or ""
                
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                if attempt == max_retries:
                    logger.error(f"LLM failed after {max_retries} attempts: {e}")
                    raise
                sleep_seconds = backoff ** attempt
                logger.warning(f"LLM request failed (Attempt {attempt}/{max_retries}): {e}. Retrying in {sleep_seconds}s...")
                time.sleep(sleep_seconds)
            except Exception as e:
                logger.error(f"Fatal error during LLM generation: {e}", exc_info=True)
                raise

        raise RuntimeError("LLM request completed with unhandled rate limit or timeout errors.")

    def _simulate_generation(self, system_prompt: str, user_prompt: str) -> str:
        """
        Simulates LLM JSON returns locally based on prompts.
        Useful for running verification tests without credit usage or credentials.
        """
        logger.info("Simulating LLM execution locally.")
        time.sleep(0.5)  # Simulate small network latency
        
        user_prompt_lower = user_prompt.lower()
        
        # 1. Parse Resume request
        if "resume text" in user_prompt_lower or "resume_text" in user_prompt_lower:
            return """
            {
              "skills": ["Python", "SQL", "Machine Learning", "PyTorch", "Git", "REST APIs"],
              "programming_languages": ["Python", "SQL", "Bash"],
              "frameworks": ["Flask", "FastAPI", "SQLAlchemy", "PyTorch"],
              "experience": [
                {
                  "company": "AI Innovations Ltd",
                  "role": "Junior ML Engineer",
                  "years": 1.5,
                  "description": "Built pipeline code in Python using SQLAlchemy and PyTorch. Implemented FastAPI routers."
                }
              ],
              "education": [
                {
                  "institution": "State Technical University",
                  "degree": "B.S. in Computer Science",
                  "year": 2024
                }
              ],
              "projects": [
                {
                  "title": "Job Aggregator Dashboard",
                  "description": "Developed web crawling pipelines and sqlite repo services.",
                  "technologies": ["Python", "SQLAlchemy", "SQLite"]
                }
              ],
              "certifications": ["AWS Certified Cloud Practitioner"]
            }
            """
            
        # 2. Evaluate Job request
        elif "evaluate this job" in user_prompt_lower or "job details" in user_prompt_lower:
            # Dynamically tailor the mock response based on job titles in the prompt
            if "staff ai engineer" in user_prompt_lower or "5+ years" in user_prompt_lower:
                # Poor match: Experience requirement too high
                return """
                {
                  "match_score": 42,
                  "should_apply": false,
                  "priority": "Low",
                  "summary": "The candidate has only 1.5 years of experience as a Junior ML Engineer, whereas this role requires a Staff level engineer with at least 5 years of experience. The gap in senior engineering experience is too large.",
                  "strengths": ["Python", "PyTorch", "Machine Learning"],
                  "missing_skills": ["Staff Leadership", "Production scaling of LLMs at scale", "System Design"],
                  "learning_effort": "High",
                  "confidence": 0.95
                }
                """
            elif "python developer" in user_prompt_lower or "generative ai engineer" in user_prompt_lower or "ai engineer" in user_prompt_lower:
                # Excellent match: matches junior experience and skill profile
                return """
                {
                  "match_score": 92,
                  "should_apply": true,
                  "priority": "High",
                  "summary": "Excellent semantic match. The candidate has Junior ML engineering experience and solid Python/SQL capabilities, which align closely with the requirements of this role. Missing skills like PyTorch/TensorFlow mentioned in the job description are already partially in their project portfolio.",
                  "strengths": ["Python", "FastAPI", "SQLAlchemy", "SQL", "Git"],
                  "missing_skills": ["Docker", "Deploying models to AWS"],
                  "learning_effort": "Low",
                  "confidence": 0.90
                }
                """
            else:
                # Neutral match
                return """
                {
                  "match_score": 75,
                  "should_apply": true,
                  "priority": "Medium",
                  "summary": "Reasonable match. The candidate meets the base Python development requirements. Some learning is needed to bridge the gap in framework specializations required by the team.",
                  "strengths": ["Python", "SQL", "Git"],
                  "missing_skills": ["Docker", "Kubernetes"],
                  "learning_effort": "Medium",
                  "confidence": 0.85
                }
                """
                
        return "{}"
