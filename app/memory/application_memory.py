import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.config import settings
from app.logger import logger

class ApplicationMemoryManager:
    """
    Manages long-term career assistant memory persisted in data/career_memory.json.
    Tracks applications status, favorite/ignored companies, target tech stack, and locations.
    """
    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or os.path.join(settings.BASE_DIR, "data", "career_memory.json")
        self.memory = self._load_memory()

    def _load_memory(self) -> Dict[str, Any]:
        """
        Loads memory from file, or initializes defaults if not found.
        """
        if not os.path.exists(self.file_path):
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            default_structure = {
                "applied_jobs": [],
                "rejected_jobs": [],
                "interview_invitations": [],
                "favorite_companies": ["Google", "DeepMind", "OpenAI", "Anthropic"],
                "ignored_companies": ["SpamCorp", "OutsourceFactory"],
                "preferred_locations": ["Remote", "Bangalore", "San Francisco", "London"],
                "preferred_technologies": ["Python", "PyTorch", "LangGraph", "Docker", "SQLAlchemy", "FastAPI"],
                "previously_generated_resumes": {} # map of job_url to paths
            }
            try:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(default_structure, f, indent=4)
                logger.info(f"Memory: Initialized new memory cache at {self.file_path}")
                return default_structure
            except Exception as e:
                logger.error(f"Memory: Failed to create memory file: {e}")
                return default_structure

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Ensure required keys exist
            required_keys = ["applied_jobs", "rejected_jobs", "interview_invitations", "favorite_companies", "ignored_companies", "preferred_locations", "preferred_technologies", "previously_generated_resumes"]
            for key in required_keys:
                if key not in data:
                    data[key] = [] if key != "previously_generated_resumes" else {}
                    
            return data
        except Exception as e:
            logger.error(f"Memory: Error reading memory cache file: {e}", exc_info=True)
            return {}

    def save_memory(self) -> None:
        """
        Saves local memory state back to JSON file.
        """
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=4)
            logger.info("Memory: Saved career memory file successfully.")
        except Exception as e:
            logger.error(f"Memory: Failed to save memory: {e}", exc_info=True)

    def add_applied_job(self, job_url: str, company: str, position: str, status: str = "Draft", resume_path: str = None, cover_letter_path: str = None) -> None:
        """
        Logs a prepared application package record in memory.
        """
        # Avoid duplicate memory logs
        for job in self.memory["applied_jobs"]:
            if job.get("job_url") == job_url:
                job["status"] = status
                job["last_updated"] = datetime.now(timezone.utc).isoformat()
                if resume_path:
                    job["resume_path"] = resume_path
                if cover_letter_path:
                    job["cover_letter_path"] = cover_letter_path
                self.save_memory()
                return

        new_record = {
            "job_url": job_url,
            "company": company,
            "position": position,
            "status": status,
            "resume_path": resume_path,
            "cover_letter_path": cover_letter_path,
            "applied_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        self.memory["applied_jobs"].append(new_record)
        
        # Save package references
        if resume_path or cover_letter_path:
            self.memory["previously_generated_resumes"][job_url] = {
                "resume_path": resume_path,
                "cover_letter_path": cover_letter_path,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        self.save_memory()
        logger.info(f"Memory: Appended applied job listing for '{position}' at '{company}'.")

    def update_status(self, job_url: str, new_status: str) -> None:
        """
        Updates the status of an active application in memory cache.
        Handles list shifting for stats tracking (e.g. tracking interview invites).
        """
        found = False
        for job in self.memory["applied_jobs"]:
            if job.get("job_url") == job_url:
                job["status"] = new_status
                job["last_updated"] = datetime.now(timezone.utc).isoformat()
                if new_status == "Applied":
                    job["applied_at"] = datetime.now(timezone.utc).isoformat()
                found = True
                break

        if not found:
            logger.warning(f"Memory: Status change requested for unregistered job URL {job_url}")
            return

        # Shift lists dynamically based on status triggers
        if new_status == "Interview" and job_url not in self.memory["interview_invitations"]:
            self.memory["interview_invitations"].append(job_url)
        elif new_status == "Rejected" and job_url not in self.memory["rejected_jobs"]:
            self.memory["rejected_jobs"].append(job_url)
            
        self.save_memory()
        logger.info(f"Memory: Updated job status for URL {job_url} to '{new_status}'")

    def has_generated_package(self, job_url: str) -> bool:
        """
        Checks if an application package has already been built for this URL.
        """
        return job_url in self.memory.get("previously_generated_resumes", {})

    def get_memory_context(self) -> str:
        """
        Formats memory parameters as a structured text block for LLM prompt context injection.
        """
        context = []
        context.append("## CANDIDATE CAREER PREFERENCES (LONG-TERM MEMORY)")
        context.append(f"- Preferred Technologies: {', '.join(self.memory.get('preferred_technologies', []))}")
        context.append(f"- Preferred Locations: {', '.join(self.memory.get('preferred_locations', []))}")
        context.append(f"- Favorite Target Companies: {', '.join(self.memory.get('favorite_companies', []))}")
        context.append(f"- Ignored / Blocked Companies: {', '.join(self.memory.get('ignored_companies', []))}")
        
        applied_count = len(self.memory.get("applied_jobs", []))
        interview_count = len(self.memory.get("interview_invitations", []))
        context.append(f"\n## HISTORICAL STATS")
        context.append(f"- Total Applications Prepared: {applied_count}")
        context.append(f"- Interview Invitations Received: {interview_count}")
        
        return "\n".join(context)
