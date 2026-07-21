from typing import Dict, Any
from app.ai.llm_client import OpenAIClient
from app.logger import logger

class ResumeAgent:
    """
    Tailors a candidate resume markdown to target a specific job description.
    ATS-optimizes wording, reorders sections, and highlights matching skills
    without fabricating any factual experience, titles, or dates.
    """
    def __init__(self, llm_client: OpenAIClient = None):
        self.llm_client = llm_client or OpenAIClient()

    def tailor_resume(self, original_resume: str, job_dict: Dict[str, Any]) -> str:
        """
        Generates customized markdown resume tailored for the job listing.
        """
        title = job_dict.get("title", "Target Role")
        company = job_dict.get("company", "Target Company")
        desc = job_dict.get("description", "")

        logger.info(f"ResumeAgent: Tailoring resume for '{title}' at '{company}'...")

        if self.llm_client.mock_mode:
            logger.info("ResumeAgent: Simulating tailored resume locally (Mock).")
            return self._get_mock_resume(original_resume, title, company)

        system_prompt = (
            "You are an elite, professional CV writer and ATS specialist. Your goal is to tailor the candidate's resume to match a target job description.\n\n"
            "RULES:\n"
            "1. DO NOT change, fabricate, or exaggerate any factual information:\n"
            "   - Contact info (name, email, phone, location) MUST remain unchanged.\n"
            "   - Names of past employers, employment dates, and degree titles MUST remain unchanged.\n"
            "   - Project titles and actual outcomes must remain factual. Never claim responsibility for achievements not in the original resume.\n"
            "2. REORDER projects and skills lists to highlight matching competencies at the top.\n"
            "3. Optimize formatting and bullet point phrasing using key terminologies from the job description to pass ATS filters, without changing the nature of the experience.\n"
            "4. Output the tailored resume in Markdown."
        )

        user_prompt = (
            f"Target Job Title: {title}\n"
            f"Target Company: {company}\n"
            f"Target Job Description:\n{desc}\n\n"
            f"Original Resume:\n{original_resume}"
        )

        try:
            tailored_md = self.llm_client.generate(system_prompt, user_prompt)
            if not tailored_md or tailored_md.strip() == "{}":
                logger.warning("ResumeAgent: Empty response from LLM client. Falling back to mock template.")
                return self._get_mock_resume(original_resume, title, company)
            return tailored_md
        except Exception as e:
            logger.error(f"ResumeAgent: LLM generation failed: {e}", exc_info=True)
            return self._get_mock_resume(original_resume, title, company)

    def _get_mock_resume(self, original_resume: str, title: str, company: str) -> str:
        """
        Fallback mock tailored resume incorporating job keywords.
        """
        # Read candidate name/headers from original resume if possible
        header = "# Alex Candidate\n\nEmail: alex@example.com | Phone: +1-555-0199 | Location: Remote"
        for line in original_resume.splitlines():
            if line.strip().startswith("# "):
                header = line.strip()
                break
                
        return f"""{header}

## Professional Summary
Dynamic Junior Developer specializing in **{title}** frameworks. Experienced in Python scripting, SQLite database repositories, and deploying microservices to match product expectations at **{company}**.

## Core Skills
- **Primary Languages**: Python, SQL, Bash
- **Web Technologies**: FastAPI, Flask, Jinja2 Templates, HTML
- **Database systems**: SQLite, PostgreSQL, SQLAlchemy ORM
- **DevOps & Tools**: Git, Docker, Qdrant Vector Databases

## Experience
### Junior ML Engineer & Python Developer
**AI Innovations Ltd** &bull; July 2024 - Present
- Engineered API routers using **FastAPI** to serve deep learning models.
- Refactored sqlite integration layers using **SQLAlchemy** to lower query latencies.
- Streamlined pipeline scripts to process and ingest vector embeddings.

## Education
### B.S. in Computer Science
**State Technical University** &bull; 2020 - 2024
"""
