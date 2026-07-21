import json
from typing import Dict, Any, List, Optional
from app.database.repository import JobRepository
from app.agents.preference_agent import PreferenceAgent
from app.config import settings
from app.logger import logger

class LearningAgent:
    """
    LearningAgent is responsible for analyzing feedback logs and updating preference scores.
    Implements dynamic keyword extraction, location adjustments, and remote preference learning.
    """
    def __init__(self, repository: Optional[JobRepository] = None, preference_agent: Optional[PreferenceAgent] = None):
        self.repository = repository or JobRepository()
        self.preference_agent = preference_agent or PreferenceAgent(self.repository)

    def learn_from_feedback(self) -> Dict[str, Any]:
        """
        Scans feedback_events table and updates weights inside preferences.
        Returns a dictionary summary of adjustments made.
        """
        logger.info("LearningAgent: Commencing dynamic feedback learning analysis cycle.")
        
        # 1. Fetch recent feedback events
        with self.repository.session_provider() as session:
            from app.database.models import FeedbackEventModel
            from sqlalchemy import select
            query = select(FeedbackEventModel).order_by(FeedbackEventModel.created_at.desc()).limit(150)
            events = session.execute(query).scalars().all()
            
        if not events:
            logger.info("LearningAgent: No feedback events found in database. Learning skipped.")
            return {"status": "skipped", "reason": "No interaction events recorded."}

        # 2. Track count adjustments
        tech_rewards = {}
        location_rewards = {}
        remote_rewards = {"remote": 0, "hybrid": 0, "onsite": 0}
        
        # Define reward offsets for positive vs negative interactions
        reward_matrix = {
            "Applied": 0.05,
            "Bookmarked": 0.04,
            "Interview Scheduled": 0.10,
            "Offer Received": 0.15,
            "Offer Accepted": 0.20,
            "Viewed Job": 0.01,
            "Ignored Job": -0.06,
            "Rejected": -0.04,
            "Application Withdrawn": -0.02
        }

        # 3. Analyze each event
        for event in events:
            event_type = event.event_type
            weight = reward_matrix.get(event_type, 0.0)
            if weight == 0.0:
                continue

            # Fetch associated job details
            db_job = None
            if event.job_id:
                with self.repository.session_provider() as session:
                    from app.database.models import JobModel
                    db_job = session.get(JobModel, event.job_id)
            
            if not db_job:
                continue

            # Check Remote Mode
            desc = db_job.description.lower()
            loc = db_job.location.lower()
            if "remote" in desc or "remote" in loc:
                remote_rewards["remote"] += weight
            elif "hybrid" in desc or "hybrid" in loc:
                remote_rewards["hybrid"] += weight
            else:
                remote_rewards["onsite"] += weight

            # Extract location match
            job_loc = db_job.location.strip()
            if job_loc:
                location_rewards[job_loc] = location_rewards.get(job_loc, 0.0) + weight

            # Extract technology match from description
            all_techs = settings.REQUIRED_SKILLS + settings.JOB_KEYWORDS
            for tech in all_techs:
                if tech.lower() in desc or tech.lower() in db_job.title.lower():
                    tech_rewards[tech] = tech_rewards.get(tech, 0.0) + weight

        # 4. Apply decays first to keep system in equilibrium
        self.preference_agent.decay_preferences(factor=0.98)

        # 5. Save updated scores
        adjustments = {
            "technologies": [],
            "locations": [],
            "remote": []
        }

        for tech, score_delta in tech_rewards.items():
            current = self.preference_agent.get_score("technology", tech)
            new_score = current + score_delta
            self.preference_agent.update_score("technology", tech, new_score)
            adjustments["technologies"].append({"name": tech, "delta": round(score_delta, 4), "new_score": round(new_score, 4)})

        for loc, score_delta in location_rewards.items():
            current = self.preference_agent.get_score("location", loc)
            new_score = current + score_delta
            self.preference_agent.update_score("location", loc, new_score)
            adjustments["locations"].append({"name": loc, "delta": round(score_delta, 4), "new_score": round(new_score, 4)})

        for mode, score_delta in remote_rewards.items():
            current = self.preference_agent.get_score("remote_pref", mode)
            new_score = current + score_delta
            self.preference_agent.update_score("remote_pref", mode, new_score)
            adjustments["remote"].append({"name": mode, "delta": round(score_delta, 4), "new_score": round(new_score, 4)})

        logger.info(f"LearningAgent: Preference learning iteration complete. Adjusted {len(tech_rewards)} technologies.")
        return adjustments
