from typing import Dict, Any, List, Optional
from app.database.repository import JobRepository
from app.agents.preference_agent import PreferenceAgent
from app.logger import logger

class RecommendationAgent:
    """
    RecommendationAgent houses the ScoringEngine:
    - Calculates multi-criteria recommendation scores.
    - Factors: LLM Match, Behavior, Company Pref, Location Pref, Technology Pref, Salary, Growth, and Risk.
    - Persists details in recommendation_history.
    """
    def __init__(self, repository: Optional[JobRepository] = None, preference_agent: Optional[PreferenceAgent] = None):
        self.repository = repository or JobRepository()
        self.preference_agent = preference_agent or PreferenceAgent(self.repository)

    def calculate_scores(self, job_dict: Dict[str, Any], match_result: Dict[str, Any], strategy_result: Dict[str, Any]) -> Dict[str, float]:
        """
        Computes individual category scores and combines them into the Final Recommendation Score.
        Returns a dictionary of all component scores.
        """
        job_id = job_dict.get("id")
        title = job_dict.get("title", "")
        company = job_dict.get("company", "")
        loc = job_dict.get("location", "")
        desc = job_dict.get("description", "").lower()

        # 1. LLM Match (0.0 to 1.0)
        llm_match = float(match_result.get("match_score", 50)) / 100.0

        # 2. Technology Preference Score (0.0 to 1.0)
        tech_score = 0.5
        from app.config import settings
        all_techs = settings.REQUIRED_SKILLS + settings.JOB_KEYWORDS
        matched_techs = [tech for tech in all_techs if tech.lower() in desc or tech.lower() in title.lower()]
        if matched_techs:
            scores = [self.preference_agent.get_score("technology", t) for t in matched_techs]
            tech_score = sum(scores) / len(scores)

        # 3. Location Preference Score (0.0 to 1.0)
        location_score = self.preference_agent.get_score("location", loc)

        # 4. Company Preference Score (0.0 to 1.0)
        company_score = 0.5
        with self.repository.session_provider() as session:
            from app.database.models import CompanyProfileModel
            from sqlalchemy import select
            query = select(CompanyProfileModel).where(CompanyProfileModel.name == company)
            profile = session.execute(query).scalars().first()
            if profile:
                if profile.status == "Favorite":
                    company_score = 1.0
                elif profile.status == "Blocked":
                    company_score = 0.0
                else:
                    # Scale based on success rate if applied
                    if profile.applied_count > 0:
                        company_score = 0.5 + (profile.success_rate / 200.0) # Scale between 0.5 and 1.0
                    else:
                        company_score = 0.5

        # 5. Behavior Score (0.0 to 1.0)
        # Evaluates how frequently candidate interacts with this role category
        behavior_score = 0.5
        with self.repository.session_provider() as session:
            from app.database.models import FeedbackEventModel
            from sqlalchemy import func, select
            query = select(func.count(FeedbackEventModel.id)).where(FeedbackEventModel.event_type == "Applied")
            total_applications = session.execute(query).scalar() or 0
            if total_applications > 0:
                # Count applications for similar roles
                title_words = [w for w in title.lower().split() if len(w) > 3]
                similar_count = 0
                if title_words:
                    # A rough count of feedback events for similarly named jobs
                    from app.database.models import JobModel
                    job_query = select(JobModel.id).where(JobModel.title.like(f"%{title_words[0]}%"))
                    job_ids = session.execute(job_query).scalars().all()
                    if job_ids:
                        app_event_query = select(func.count(FeedbackEventModel.id)).where(
                            FeedbackEventModel.job_id.in_(job_ids),
                            FeedbackEventModel.event_type == "Applied"
                        )
                        similar_count = session.execute(app_event_query).scalar() or 0
                
                behavior_score = 0.5 + min(0.5, (similar_count / total_applications) * 0.5)

        # 6. Salary Match (0.0 to 1.0)
        # Check if salary exceeds target or matches. If not mentioned, defaults to 0.7.
        salary_score = 0.7
        # Parse salary figures from description (e.g. LPA, $, k)
        if any(keyword in desc for keyword in ["salary", "compensation", "lpa", "usd", "$", "k"]):
            salary_score = 0.85 # Assume positive matching if details mentioned

        # 7. Growth Score (0.0 to 1.0)
        growth_est = strategy_result.get("career_growth", "Good")
        growth_map = {"Excellent": 1.0, "Good": 0.7, "Fair": 0.4, "Poor": 0.1}
        growth_score = growth_map.get(growth_est, 0.7)

        # 8. Risk Score (0.0 to 1.0)
        # Calculated as: 1.0 - Risk factor. High rejections = lower score.
        risk_score = 1.0
        if profile and profile.rejected_count > 0:
            rejection_ratio = profile.rejected_count / max(1, profile.applied_count)
            risk_score = max(0.2, 1.0 - rejection_ratio * 0.5)

        # 9. Final Weighted Score
        # Weights:
        # LLM Match: 30%
        # Technology Pref: 15%
        # Location Pref: 10%
        # Company Pref: 10%
        # Behavior Score: 10%
        # Salary Match: 10%
        # Growth Score: 10%
        # Risk Score: 5%
        final_score = (
            llm_match * 0.30 +
            tech_score * 0.15 +
            location_score * 0.10 +
            company_score * 0.10 +
            behavior_score * 0.10 +
            salary_score * 0.10 +
            growth_score * 0.10 +
            risk_score * 0.05
        ) * 100.0
        
        final_score = round(final_score, 2)

        scores_payload = {
            "llm_match": round(llm_match * 100, 1),
            "technology_pref": round(tech_score * 100, 1),
            "location_pref": round(location_score * 100, 1),
            "company_pref": round(company_score * 100, 1),
            "behavior": round(behavior_score * 100, 1),
            "salary_match": round(salary_score * 100, 1),
            "growth": round(growth_score * 100, 1),
            "risk": round(risk_score * 100, 1),
            "final_score": final_score
        }

        # 10. Log score audit details to database
        if job_id:
            reason = strategy_result.get("reasoning", [])
            self.repository.log_recommendation_history(
                job_id=job_id,
                scores=scores_payload,
                reason=reason
            )

        return scores_payload
