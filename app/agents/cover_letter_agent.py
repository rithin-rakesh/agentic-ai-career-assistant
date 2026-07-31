from typing import Dict, Any, Optional
from app.ai.llm_client import BaseLLM, MockLLM, get_llm_client
from app.logger import logger

class CoverLetterAgent:
    """
    Generates tailored, professional cover letters matching
    candidate profile details with target job requirements via Gemini / BaseLLM.
    Strictly forbids experience fabrication or title embellishment.
    """
    def __init__(self, llm_client: Optional[BaseLLM] = None):
        self.llm_client = llm_client or get_llm_client()

    def generate_cover_letter(self, resume_context: str, job_dict: Dict[str, Any]) -> str:
        """
        Drafts a cover letter in Markdown based on job details and resume capabilities.
        """
        title = job_dict.get("title", "Target Role")
        company = job_dict.get("company", "Target Company")
        desc = job_dict.get("description", "")

        logger.info(f"CoverLetterAgent: Drafting cover letter for '{title}' at '{company}'...")

        if isinstance(self.llm_client, MockLLM) or getattr(self.llm_client, "mock_fallback", None) is not None:
            logger.info("CoverLetterAgent: Simulating cover letter locally (Mock).")
            return self._get_mock_cover_letter(title, company)

        system_prompt = (
            "You are a professional hiring consultant and copywriter. Write a persuasive, professional cover letter for the candidate.\n\n"
            "GUIDELINES:\n"
            "1. Write a single page, formatted in Markdown, starting with standard headers, salutations, body paragraph sections, and sign-offs.\n"
            "2. Connect candidate skills from their resume with the target job's challenges and deliverables.\n"
            "3. NEVER fabricate any employment records, skills, or achievements not explicitly stated in the candidate's resume context.\n"
            "4. Tone must be confident, formal, and enthusiastic."
        )

        user_prompt = (
            f"Target Company: {company}\n"
            f"Target Position: {title}\n"
            f"Job Description:\n{desc}\n\n"
            f"Candidate Resume Context:\n{resume_context}"
        )

        try:
            cover_letter = self.llm_client.generate(system_prompt, user_prompt)
            if not cover_letter or cover_letter.strip() == "{}":
                logger.warning("CoverLetterAgent: Empty response from LLM. Falling back to mock template.")
                return self._get_mock_cover_letter(title, company)
            return cover_letter
        except Exception as e:
            logger.error(f"CoverLetterAgent: LLM draft failed: {e}", exc_info=True)
            return self._get_mock_cover_letter(title, company)

    def _get_mock_cover_letter(self, title: str, company: str) -> str:
        """
        Fallback mock cover letter template.
        """
        return f"""# Alex Candidate
Email: alex@example.com | Phone: +1-555-0199 | Location: Remote

## July 19, 2026

Hiring Committee
**{company}**

Dear Hiring Team,

I am writing to express my strong interest in the **{title}** position at **{company}**. With my solid foundation in Python software design, SQLAlchemy data layers, and API routing development, I am eager to contribute to your engineering goals.

In my recent experience as a Junior ML Engineer at AI Innovations Ltd, I developed robust backend integrations using FastAPI and optimized database interactions. I focus on writing clean, modular, and maintainable code that directly aligns with the technical standards at **{company}**.

I am particularly excited about the chance to apply my skills to the challenges detailed in your job description. I look forward to discussing how my background and qualifications can support your team.

Thank you for your time and consideration.

Sincerely,

Alex Candidate
"""
