import os
import json
import hashlib
from typing import List, Dict, Any
from app.config import settings
from app.agents.resume_agent import ResumeAgent
from app.agents.cover_letter_agent import CoverLetterAgent
from app.agents.skills_agent import SkillsAgent
from app.memory.application_memory import ApplicationMemoryManager
from app.resume.resume_generator import ResumeDocumentGenerator
from app.cover_letters.generator import CoverLetterGenerator
from app.logger import logger

class ApplicationAgent:
    """
    Main coordinator for the Application Preparation Layer.
    For every High Priority match, tailored resumes, cover letters,
    and missing skills learning roadmaps are autonomously compiled and saved.
    Logs package results into career memory cache to avoid regeneration loops.
    """
    def __init__(self, resume_agent: ResumeAgent = None, cl_agent: CoverLetterAgent = None, skills_agent: SkillsAgent = None, memory_manager: ApplicationMemoryManager = None):
        self.resume_agent = resume_agent or ResumeAgent()
        self.cl_agent = cl_agent or CoverLetterAgent()
        self.skills_agent = skills_agent or SkillsAgent()
        self.memory = memory_manager or ApplicationMemoryManager()
        self.resume_doc_gen = ResumeDocumentGenerator()
        self.cl_doc_gen = CoverLetterGenerator()

    def prepare_applications(self, ranked_jobs: List[Dict[str, Any]], retrieved_context: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Processes ranked jobs list, executing compilation sequences for High Priority matches.
        Returns: List of package tracking dictionaries.
        """
        packages = []

        # Read the raw original resume to pass to the tailoring agent
        original_resume = ""
        try:
            if os.path.exists(settings.RESUME_TEMPLATE):
                with open(settings.RESUME_TEMPLATE, "r", encoding="utf-8") as f:
                    original_resume = f.read()
            else:
                # Default fallback original resume structure
                original_resume = "# Candidate Profile\n\n- Experience: Junior ML Engineer (1.5 years)\n- Skills: Python, SQL"
        except Exception as e:
            logger.error(f"ApplicationAgent: Failed to read original resume template: {e}")
            original_resume = "# Candidate Profile\n\n- Experience: Junior ML Engineer\n- Skills: Python, SQL"

        for job_dict in ranked_jobs:
            priority = job_dict.get("priority", "Low")
            score = job_dict.get("match_score", 0)
            
            # Application packages are prepared ONLY for High Priority matches
            is_high_priority = (priority == "High") or (score >= settings.INSTANT_THRESHOLD)
            if not is_high_priority:
                continue

            job_url = job_dict.get("job_url", "")
            company = job_dict.get("company", "Unknown Company")
            title = job_dict.get("title", "Unknown Title")

            # 1. Prevent duplicate application document generation
            if self.memory.has_generated_package(job_url):
                logger.info(f"ApplicationAgent: Package already exists for '{title}' at '{company}'. Loading cached metadata.")
                cached = self.memory.memory["previously_generated_resumes"][job_url]
                packages.append({
                    "job_url": job_url,
                    "company": company,
                    "position": title,
                    "status": "Draft",
                    "resume_path": cached.get("resume_path"),
                    "cover_letter_path": cached.get("cover_letter_path"),
                    "learning_plan_path": os.path.dirname(cached.get("resume_path", "")) if cached.get("resume_path") else None
                })
                continue

            # 2. Run compilation pipeline
            logger.info(f"ApplicationAgent: Commencing package generation for '{title}' at '{company}'...")
            
            # Fetch retrieved context snippets
            context = retrieved_context.get(job_url, "Skills: Python, FastAPI, SQL")
            
            # Tailor Resume Markdown
            tailored_resume_md = self.resume_agent.tailor_resume(original_resume, job_dict)
            
            # Draft Cover Letter Markdown
            cover_letter_md = self.cl_agent.generate_cover_letter(context, job_dict)
            
            # Generate Skills gap roadmap
            learning_plan = self.skills_agent.generate_learning_plan(context, job_dict)

            # 3. Save files to custom directory
            url_hash = hashlib.md5(job_url.encode("utf-8")).hexdigest()[:8]
            clean_company = "".join(c for c in company.replace(" ", "_") if c.isalnum() or c == "_")
            clean_title = "".join(c for c in title.replace(" ", "_") if c.isalnum() or c == "_")
            folder_name = f"{clean_company}_{clean_title}_{url_hash}"
            
            out_dir = os.path.join(settings.OUTPUT_DIRECTORY, folder_name)
            os.makedirs(out_dir, exist_ok=True)

            # Compile resume formats (.md, .docx, .pdf)
            resume_base_path = os.path.join(out_dir, "resume_tailored")
            resume_files = self.resume_doc_gen.generate(tailored_resume_md, resume_base_path)
            
            # Compile cover letter formats
            cl_base_path = os.path.join(out_dir, "cover_letter")
            cl_files = self.cl_doc_gen.generate(cover_letter_md, cl_base_path)

            # Save learning plan JSON roadmap
            lp_path = os.path.join(out_dir, "learning_plan.json")
            try:
                with open(lp_path, "w", encoding="utf-8") as f:
                    json.dump(learning_plan, f, indent=4)
                logger.info(f"ApplicationAgent: Saved learning plan to {lp_path}")
            except Exception as e:
                logger.error(f"ApplicationAgent: Failed to save learning plan JSON: {e}")

            # 4. Resolve default paths for SQLite and Memory storage (favoring PDF, falling back to docx/md)
            res_path = resume_files.get("pdf") or resume_files.get("docx") or resume_files.get("markdown")
            cov_path = cl_files.get("pdf") or cl_files.get("docx") or cl_files.get("markdown")

            # Update Memory cache
            self.memory.add_applied_job(job_url, company, title, "Draft", res_path, cov_path)

            packages.append({
                "job_url": job_url,
                "company": company,
                "position": title,
                "status": "Draft",
                "resume_path": res_path,
                "cover_letter_path": cov_path,
                "learning_plan_path": lp_path
            })

            logger.info(f"ApplicationAgent: Successfully completed application package for Job ID '{title}' at '{company}'.")

        return packages
