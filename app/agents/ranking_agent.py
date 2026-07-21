from typing import List, Dict, Any
from app.logger import logger

class RankingAgent:
    """
    RankingAgent consolidates job details and evaluation scores.
    Sorts listings based on:
    1. should_apply (recommendations first)
    2. match_score (highest score first)
    3. confidence (highest confidence first)
    """
    def rank_jobs(self, filtered_jobs: List[Dict[str, Any]], match_results: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        logger.info("RankingAgent: Commencing final scoring list consolidation.")
        ranked_list = []
        
        for job_dict in filtered_jobs:
            url = job_dict.get("job_url", "")
            evaluation = match_results.get(url, {})
            
            # Combine job details and AI matching scores
            combined_payload = dict(job_dict)
            combined_payload.update(evaluation)
            ranked_list.append(combined_payload)
            
        # Execute sorting:
        # Pushes should_apply=True to top, then highest match_score, then highest confidence
        ranked_list.sort(
            key=lambda x: (
                int(x.get("should_apply", False)),
                x.get("match_score", 0),
                x.get("confidence", 0.0)
            ),
            reverse=True
        )
        
        logger.info(f"RankingAgent: Sorted {len(ranked_list)} jobs.")
        for idx, job in enumerate(ranked_list[:5], 1):
            logger.info(
                f"Rank #{idx}: '{job.get('title')}' at '{job.get('company')}' | "
                f"Score: {job.get('match_score')} | Recommend: {job.get('should_apply')} | Priority: {job.get('priority')}"
            )
            
        return ranked_list
