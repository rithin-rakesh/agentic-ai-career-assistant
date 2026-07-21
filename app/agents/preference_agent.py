from typing import Dict, Any, List, Optional
from app.database.repository import JobRepository
from app.logger import logger

class PreferenceAgent:
    """
    PreferenceAgent operates the PreferenceEngine.
    Maintains, decay, and updates dynamic candidate preference weights across categories.
    """
    def __init__(self, repository: Optional[JobRepository] = None):
        self.repository = repository or JobRepository()

    def get_score(self, category: str, name: str) -> float:
        """
        Retrieves preference score weight for a specific item.
        Defaults to 0.5 if not found, or 0.8 if name matches base target config.
        """
        # Read from database
        with self.repository.session_provider() as session:
            from app.database.models import PreferenceModel
            from sqlalchemy import select
            query = select(PreferenceModel).where(
                PreferenceModel.category == category,
                PreferenceModel.name == name
            )
            pref = session.execute(query).scalars().first()
            if pref:
                return pref.score
                
        # Base Target defaults
        from app.config import settings
        if category == "technology" and name in settings.JOB_KEYWORDS:
            return 0.8
        if category == "location" and name in settings.PREFERRED_LOCATIONS:
            return 0.8
        if category == "remote_pref" and name.lower() == "remote" and settings.ENABLE_REMOTE:
            return 0.8
            
        return 0.5

    def update_score(self, category: str, name: str, score: float) -> Any:
        """
        Saves the updated score, clamped between 0.0 and 1.0.
        """
        clamped_score = max(0.0, min(1.0, round(score, 4)))
        logger.info(f"PreferenceAgent: Updating weight '{name}' in category '{category}' to {clamped_score}")
        return self.repository.update_preference_score(category, name, clamped_score)

    def get_category_preferences(self, category: str) -> Dict[str, float]:
        """
        Retrieves all keys and scores inside a specific category.
        """
        prefs = {}
        # Fetch from DB
        with self.repository.session_provider() as session:
            from app.database.models import PreferenceModel
            from sqlalchemy import select
            query = select(PreferenceModel).where(PreferenceModel.category == category)
            db_prefs = session.execute(query).scalars().all()
            for p in db_prefs:
                prefs[p.name] = p.score
                
        # Fill defaults from config if empty
        from app.config import settings
        if category == "technology":
            for kw in settings.JOB_KEYWORDS:
                if kw not in prefs:
                    prefs[kw] = 0.8
        elif category == "location":
            for loc in settings.PREFERRED_LOCATIONS:
                if loc not in prefs:
                    prefs[loc] = 0.8
        elif category == "remote_pref":
            if "Remote" not in prefs:
                prefs["Remote"] = 0.8 if settings.ENABLE_REMOTE else 0.5
                
        return prefs

    def decay_preferences(self, factor: float = 0.98) -> None:
        """
        Multiplies all dynamic weights by a decay factor (towards the baseline 0.5)
        to represent waning interests over time if no active feedback reinforces them.
        """
        logger.info(f"PreferenceAgent: Applying decay factor of {factor} to all preference weights.")
        with self.repository.session_provider() as session:
            from app.database.models import PreferenceModel
            from sqlalchemy import select
            
            # Fetch all preferences
            query = select(PreferenceModel)
            db_prefs = session.execute(query).scalars().all()
            for pref in db_prefs:
                # Decay towards the baseline of 0.5
                current = pref.score
                decayed = 0.5 + (current - 0.5) * factor
                pref.score = max(0.0, min(1.0, round(decayed, 4)))
            session.commit()
