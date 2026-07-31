import json
from typing import Dict, Any, Optional
from app.config import settings
from app.ai.llm_client import BaseLLM, MockLLM, get_llm_client
from app.database.repository import JobRepository
from app.logger import logger

class CareerStrategyAgent:
    """
    CareerStrategyAgent evaluates job opportunities strategically via Gemini / BaseLLM:
    - Analyzes long-term value, career growth, stability, interview probability, and time investment score.
    - Decides whether the opportunity is worth pursuing immediately, worth prioritizing, or ignored.
    - Generates dynamic reasoning, interview preparation suggestions, and learning effort recommendations.
    """
    def __init__(self, llm_client: Optional[BaseLLM] = None, repository: Optional[JobRepository] = None):
        self.llm_client = llm_client or get_llm_client()
        self.repository = repository or JobRepository()

    def evaluate_strategy(self, job_dict: Dict[str, Any], resume_content: str) -> Dict[str, Any]:
        """
        Runs the strategic career evaluation. Returns the structured JSON.
        Caches results to the database to prevent duplicate LLM calls.
        """
        job_id = job_dict.get("id")
        
        # 1. Check if cached decision already exists
        if job_id:
            cached = self.repository.get_career_decision(job_id)
            if cached:
                logger.info(f"CareerStrategyAgent: Loaded cached decision for Job ID {job_id}")
                return cached

        # 2. Compute evaluation (Mock vs Live LLM)
        if isinstance(self.llm_client, MockLLM) or getattr(self.llm_client, "mock_fallback", None) is not None or settings.MOCK_LLM:
            decision = self._generate_mock_decision(job_dict)
        else:
            decision = self._run_llm_strategy(job_dict, resume_content)

        # 3. Cache the decision in SQLite
        if job_id and decision:
            self.repository.save_career_decision(
                job_id=job_id,
                recommendation=decision.get("recommendation", "Consider"),
                confidence=decision.get("confidence", 0.7),
                priority=decision.get("priority", "Medium"),
                estimated_interview_probability=decision.get("estimated_interview_probability", "Medium"),
                career_growth=decision.get("career_growth", "Good"),
                salary_competitiveness=decision.get("salary_competitiveness", "Market Rate"),
                learning_effort=decision.get("learning_effort", "Medium"),
                resume_changes_required=decision.get("resume_changes_required", True),
                cover_letter_required=decision.get("cover_letter_required", True),
                estimated_application_time=decision.get("estimated_application_time", "20 minutes"),
                reasoning=decision.get("reasoning", []),
                missing_skills=decision.get("missing_skills", [])
            )

        return decision

    def _generate_mock_decision(self, job_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dynamically returns strategic outputs in mock mode based on matching scores.
        """
        score = job_dict.get("match_score") or 70
        title = job_dict.get("title", "")
        company = job_dict.get("company", "")
        
        # Deduce missing skills from the job description
        desc_lower = job_dict.get("description", "").lower()
        missing = []
        if "docker" not in desc_lower and "docker" in getattr(settings, "REQUIRED_SKILLS", []):
            missing.append("Docker")
        if "kubernetes" not in desc_lower and "kubernetes" in getattr(settings, "REQUIRED_SKILLS", []):
            missing.append("Kubernetes")
        if "aws" in desc_lower:
            missing.append("AWS Cloud Deployment")
            
        if not missing:
            missing = ["Advanced Prompt Engineering"]

        if score >= 85:
            return {
                "recommendation": "Apply Immediately",
                "confidence": 0.95,
                "priority": "High",
                "estimated_interview_probability": "High",
                "career_growth": "Excellent",
                "salary_competitiveness": "Above Market",
                "learning_effort": "Low",
                "resume_changes_required": True,
                "cover_letter_required": True,
                "estimated_application_time": "15 minutes",
                "reasoning": [
                    f"{score}% semantic resume match indicating high technological overlap.",
                    f"Role '{title}' matches your core candidate profile and experience range.",
                    f"Previous successful applications with similar technology configurations.",
                    f"Growth potential at '{company}' is projected as excellent."
                ],
                "missing_skills": missing
            }
        elif score >= 60:
            return {
                "recommendation": "Learn Skills First",
                "confidence": 0.78,
                "priority": "Medium",
                "estimated_interview_probability": "Medium",
                "career_growth": "Good",
                "salary_competitiveness": "Market Rate",
                "learning_effort": "Medium",
                "resume_changes_required": True,
                "cover_letter_required": False,
                "estimated_application_time": "25 minutes",
                "reasoning": [
                    f"{score}% match indicates acceptable technological alignment.",
                    f"Requires study of missing skills prior to high-priority application.",
                    "On-site work style requirement is a moderate mismatch."
                ],
                "missing_skills": missing
            }
        else:
            return {
                "recommendation": "Ignore Opportunity",
                "confidence": 0.65,
                "priority": "Low",
                "estimated_interview_probability": "Low",
                "career_growth": "Fair",
                "salary_competitiveness": "Below Market",
                "learning_effort": "High",
                "resume_changes_required": False,
                "cover_letter_required": False,
                "estimated_application_time": "10 minutes",
                "reasoning": [
                    f"Low match score ({score}%) fails minimum preference thresholds.",
                    "Substantial skill gaps require significant educational efforts."
                ],
                "missing_skills": missing
            }

    def _run_llm_strategy(self, job_dict: Dict[str, Any], resume_content: str) -> Dict[str, Any]:
        """
        Queries Gemini / BaseLLM for strategic advice returning structured JSON.
        """
        system_prompt = (
            "You are a Senior Career Strategy Advisor. You evaluate job opportunities and advise candidates "
            "on whether they should invest their limited time applying. Evaluate the job details against "
            "the candidate's resume and return a structured JSON object containing recommendation, "
            "confidence, priority, estimated_interview_probability, career_growth, salary_competitiveness, "
            "learning_effort, resume_changes_required, cover_letter_required, estimated_application_time, "
            "reasoning (list of strings), and missing_skills (list of strings).\n\n"
            "Format the response strictly as valid, clean JSON with no code blocks or extra text."
        )
        
        user_prompt = (
            f"Candidate Resume:\n{resume_content}\n\n"
            f"Job Listing details:\n"
            f"Title: {job_dict.get('title')}\n"
            f"Company: {job_dict.get('company')}\n"
            f"Location: {job_dict.get('location')}\n"
            f"Description: {job_dict.get('description')}\n"
            f"Current Match Score: {job_dict.get('match_score')}\n"
        )
        
        try:
            logger.info("CareerStrategyAgent: Initiating LLM career strategy analysis call.")
            response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_format={"type": "json_object"}
            )
            
            parsed_decision = json.loads(response)
            
            required_keys = ["recommendation", "confidence", "priority", "estimated_interview_probability", "career_growth", "learning_effort"]
            for key in required_keys:
                if key not in parsed_decision:
                    parsed_decision[key] = "Medium" if key in ["priority", "estimated_interview_probability", "learning_effort"] else "Good"

            return parsed_decision
        except Exception as e:
            logger.error(f"CareerStrategyAgent: LLM execution failed: {e}", exc_info=True)
            return self._generate_mock_decision(job_dict)
