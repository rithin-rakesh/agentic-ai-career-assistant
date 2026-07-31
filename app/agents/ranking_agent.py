from typing import List, Dict, Any, Optional
from app.ai.llm_client import BaseLLM, get_llm_client
from app.logger import logger
from app.monitoring.metrics import JOBS_RANKED_TOTAL

class RankingAgent:
    """
    RankingAgent consolidates job details and evaluation scores.
    Executes multi-factor weighted job scoring (Resume Match, Career Growth, Salary, Remote Preference, Skill Gap Inverse)
    and sorts jobs deterministically while generating priority levels (High, Medium, Low).
    """
    def __init__(self, llm_client: Optional[BaseLLM] = None):
        self.llm_client = llm_client or get_llm_client()

    def rank_jobs(self, filtered_jobs: List[Dict[str, Any]], match_results: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        logger.info("RankingAgent: Commencing multi-factor weighted scoring and ranking consolidation.")
        ranked_list = []
        
        for job_dict in filtered_jobs:
            url = job_dict.get("job_url", "")
            evaluation = match_results.get(url, {})
            
            # Combine job details and AI matching scores
            combined_payload = dict(job_dict)
            combined_payload.update(evaluation)

            # Multi-factor weighted composite scoring
            match_score = float(combined_payload.get("match_score", 0))
            career_growth = float(combined_payload.get("career_growth_score", 75))
            salary_rating = 85.0 if combined_payload.get("salary_range") else 50.0
            
            loc_str = str(combined_payload.get("location", "")).lower()
            rem_str = str(combined_payload.get("remote_type", "")).lower()
            remote_rating = 100.0 if "remote" in loc_str or "remote" in rem_str else 60.0
            
            missing_count = len(combined_payload.get("missing_skills", []))
            skill_gap_inverse = max(0.0, 100.0 - (missing_count * 15.0))

            composite = (
                0.35 * match_score +
                0.20 * career_growth +
                0.15 * salary_rating +
                0.15 * remote_rating +
                0.15 * skill_gap_inverse
            )
            combined_payload["composite_score"] = round(composite, 1)

            # Priority assignment: High if composite >= 75 or match_score >= 85
            if composite >= 75.0 or match_score >= 85.0:
                priority = "High"
            elif composite >= 60.0 or match_score >= 70.0:
                priority = "Medium"
            else:
                priority = "Low"

            combined_payload["priority"] = priority
            JOBS_RANKED_TOTAL.labels(priority=priority).inc()
            ranked_list.append(combined_payload)
            
        # Execute deterministic multi-key sorting:
        # 1. Recommendation (should_apply=True first)
        # 2. Multi-factor composite score
        # 3. Raw match score
        # 4. Agent confidence
        ranked_list.sort(
            key=lambda x: (
                int(x.get("should_apply", False)),
                x.get("composite_score", 0.0),
                x.get("match_score", 0),
                x.get("confidence", 0.0)
            ),
            reverse=True
        )
        
        logger.info(f"RankingAgent: Sorted {len(ranked_list)} jobs.")
        for idx, job in enumerate(ranked_list[:5], 1):
            logger.info(
                f"Rank #{idx}: '{job.get('title')}' at '{job.get('company')}' | "
                f"Composite Score: {job.get('composite_score')} | Match Score: {job.get('match_score')} | "
                f"Recommend: {job.get('should_apply')} | Priority: {job.get('priority')}"
            )
            
        return ranked_list
