from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING
from pydantic import BaseModel, Field
from app.ai.llm_client import BaseLLM
from app.ai.prompts import JOB_MATCH_SYSTEM_PROMPT, JOB_MATCH_USER_PROMPT
from app.ai.parser import parse_and_validate_json
from app.logger import logger

if TYPE_CHECKING:
    from app.resume.resume_parser import Resume

class JobMatchResult(BaseModel):
    """
    Validation schema enforcing structural requirements of the matching LLM agent.
    """
    match_score: int = Field(..., ge=0, le=100, description="Suitability score out of 100")
    should_apply: bool = Field(..., description="True if recommended to apply, False otherwise")
    priority: str = Field(..., description="Application priority level: High, Medium, or Low")
    summary: str = Field(..., description="Brief reasoning summarizing the recommendation")
    strengths: List[str] = Field(default_factory=list, description="Skills/experiences matching the job")
    missing_skills: List[str] = Field(default_factory=list, description="Skills/experiences missing from candidate's profile")
    learning_effort: str = Field(..., description="Estimated effort to close gaps: Low, Medium, or High")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence of the agent in this matching result")
    
    # Phase 2.4 Extended Structured Evaluation Fields
    resume_strength: int = Field(80, ge=0, le=100, description="Evaluated strength of candidate resume for this role")
    career_growth_score: int = Field(75, ge=0, le=100, description="Career growth potential score out of 100")
    estimated_interview_probability: int = Field(70, ge=0, le=100, description="Estimated interview probability percentage")
    learning_recommendation: str = Field("Focus on core missing skills", description="Actionable learning advice")

class JobMatchingAgent:
    """
    AI Reasoning Agent that evaluates job suitability against candidate's profile.
    Replaces rule-based keyword filters with LLM-based semantic reasoning.
    """
    def __init__(self, llm_client: BaseLLM):
        self.llm_client = llm_client

    def evaluate_job(self, resume: Resume, job_title: str, job_company: str, job_location: str, job_source: str, job_description: str) -> dict:
        """
        Runs semantic suitability evaluation.
        Formats structured resume data and job details, calls LLM, and validates structured output.
        """
        logger.info(f"AI matching agent started evaluating: '{job_title}' at '{job_company}'")
        
        # Serialize structured Resume pydantic model to string format for prompting
        resume_json_str = resume.model_dump_json(indent=2)
        
        # Populate prompt variables
        user_prompt = JOB_MATCH_USER_PROMPT.format(
            resume_json=resume_json_str,
            job_title=job_title,
            job_company=job_company,
            job_location=job_location,
            job_source=job_source,
            job_description=job_description
        )
        
        try:
            # Generate chat completion in JSON format
            response_text = self.llm_client.generate(
                system_prompt=JOB_MATCH_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_format={"type": "json_object"}
            )
            
            # Extract JSON and validate against schema
            match_result = parse_and_validate_json(response_text, JobMatchResult)
            
            logger.info(f"Job evaluation complete. Match score: {match_result.match_score}, should_apply: {match_result.should_apply}")
            return match_result.model_dump()
            
        except Exception as e:
            logger.error(f"AI job evaluation encountered an error: {e}", exc_info=True)
            # Fail-safe default dictionary to prevent crashing the collection pipeline
            return {
                "match_score": 0,
                "should_apply": False,
                "priority": "Low",
                "summary": f"Failed to perform AI analysis: {e}",
                "strengths": [],
                "missing_skills": [],
                "learning_effort": "High",
                "confidence": 0.0
            }
class_dict = {
    "JobMatchResult": JobMatchResult,
    "JobMatchingAgent": JobMatchingAgent
}
