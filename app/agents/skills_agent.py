import json
from typing import Dict, Any
from app.ai.llm_client import OpenAIClient
from app.logger import logger

class SkillsAgent:
    """
    Analyzes job requirements and candidate skills to construct learning paths.
    Categorizes skills into 'Already Have', 'Can Learn Quickly', and 'Long-Term Learning'.
    Suggests study roadmaps, estimated study durations, and relevant certifications.
    """
    def __init__(self, llm_client: OpenAIClient = None):
        self.llm_client = llm_client or OpenAIClient()

    def generate_learning_plan(self, resume_context: str, job_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates missing skills and structures a learning plan.
        Returns: Structured dictionary matching the Pydantic or frontend layout.
        """
        title = job_dict.get("title", "Target Role")
        company = job_dict.get("company", "Target Company")
        desc = job_dict.get("description", "")

        logger.info(f"SkillsAgent: Analyzing skill gaps and constructing learning path for '{title}'...")

        if self.llm_client.mock_mode:
            logger.info("SkillsAgent: Simulating learning path locally (Mock).")
            return self._get_mock_plan(title)

        system_prompt = (
            "You are a career development coach and technical recruiter. Analyze the candidate resume context against the job description and output a JSON learning plan.\n\n"
            "JSON SCHEMA:\n"
            "{\n"
            "  \"already_have\": [\"Python\", \"SQLAlchemy\"],\n"
            "  \"can_learn_quickly\": [\n"
            "    {\"skill\": \"Docker\", \"course\": \"Docker Beginners Course\", \"certification\": \"None\", \"estimated_hours\": 6}\n"
            "  ],\n"
            "  \"long_term_learning\": [\n"
            "    {\"skill\": \"Kubernetes\", \"course\": \"Certified Kubernetes Administrator (CKA)\", \"certification\": \"CKA\", \"estimated_hours\": 60}\n"
            "  ]\n"
            "}\n"
            "Ensure the output is valid raw JSON ONLY (no markdown fences, no formatting text)."
        )

        user_prompt = (
            f"Job Description:\n{desc}\n\n"
            f"Candidate Resume Details:\n{resume_context}"
        )

        try:
            raw_response = self.llm_client.generate(system_prompt, user_prompt)
            # Remove any possible markdown backticks
            cleaned = raw_response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
            # Verify keys exist
            for key in ["already_have", "can_learn_quickly", "long_term_learning"]:
                if key not in parsed:
                    parsed[key] = []
            return parsed
            
        except Exception as e:
            logger.error(f"SkillsAgent: Parsing or LLM generation failed: {e}", exc_info=True)
            return self._get_mock_plan(title)

    def _get_mock_plan(self, title: str) -> Dict[str, Any]:
        """
        Fallback mock learning plan data.
        """
        # Tailor quick learning based on title keywords
        quick_learn_skill = "Docker"
        long_term_skill = "Kubernetes & AWS Cloud Architectures"
        if "generative ai" in title.lower() or "ai engineer" in title.lower():
            quick_learn_skill = "RAG & Vector Embeddings"
            long_term_skill = "Fine-Tuning LLMs & HuggingFace Models"
            
        return {
            "already_have": ["Python", "FastAPI", "SQLAlchemy", "SQLite", "Git", "Machine Learning"],
            "can_learn_quickly": [
                {
                    "skill": quick_learn_skill,
                    "course": "Vector Spaces and Semantic Retrieval Crash Course",
                    "certification": "None",
                    "estimated_hours": 8
                }
            ],
            "long_term_learning": [
                {
                    "skill": long_term_skill,
                    "course": "Deep Learning Specialization - Coursera",
                    "certification": "AWS Certified Machine Learning - Specialty",
                    "estimated_hours": 80
                }
            ]
        }
