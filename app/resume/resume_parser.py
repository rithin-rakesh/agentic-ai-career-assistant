from typing import List, Optional, Any
from pydantic import BaseModel, Field
from app.ai.llm_client import BaseLLM
from app.ai.prompts import RESUME_PARSE_SYSTEM_PROMPT, RESUME_PARSE_USER_PROMPT
from app.ai.parser import parse_and_validate_json
from app.logger import logger

class EducationItem(BaseModel):
    institution: str = Field(..., description="Name of the university or school")
    degree: str = Field(..., description="Degree or certification title")
    year: Optional[int] = Field(None, description="Year of graduation")

class ExperienceItem(BaseModel):
    company: str = Field(..., description="Company name")
    role: str = Field(..., description="Role title")
    years: float = Field(..., description="Number of years in this role")
    description: str = Field("", description="Responsibilities or achievements")

class ProjectItem(BaseModel):
    title: str = Field(..., description="Project title")
    description: str = Field("", description="Brief details about the project work")
    technologies: List[str] = Field(default_factory=list, description="Technologies used in this project")

class Resume(BaseModel):
    """
    Structured candidate profile representation parsed from raw text.
    """
    skills: List[str] = Field(default_factory=list)
    programming_languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    experience: List[ExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)

class ResumeParser:
    """
    Service responsible for converting raw resume text strings
    into a structured Resume Pydantic domain model using LLM capabilities.
    """
    def __init__(self, llm_client: BaseLLM):
        self.llm_client = llm_client

    def parse_resume_text(self, raw_text: str) -> Resume:
        """
        Submits the raw text to the LLM client, processes the JSON response,
        and validates it against the Resume model schema.
        """
        logger.info("Parsing raw resume text utilizing the LLM agent.")
        
        user_prompt = RESUME_PARSE_USER_PROMPT.format(resume_text=raw_text)
        
        try:
            # Generate structured response from LLM
            # Tell client to output in JSON format if supported
            response_text = self.llm_client.generate(
                system_prompt=RESUME_PARSE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_format={"type": "json_object"}
            )
            
            # Parse response and validate against Resume schema
            resume_data = parse_and_validate_json(response_text, Resume)
            logger.info("Resume text parsed and validated successfully.")
            return resume_data
            
        except Exception as e:
            logger.error(f"Error parsing resume: {e}", exc_info=True)
            # Return empty/minimal schema rather than crashing
            return Resume()
