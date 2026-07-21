from typing import List, Dict, Any
from app.ai.llm_client import BaseLLM
from app.ai.prompts import RAG_JOB_MATCH_SYSTEM_PROMPT, RAG_JOB_MATCH_USER_PROMPT
from app.ai.parser import parse_and_validate_json
from app.ai.job_matching_agent import JobMatchResult
from app.logger import logger

class MatchingAgent:
    """
    MatchingAgent executes semantic evaluations comparing job descriptions
    against retrieved context strings using the LLM recruiter logic.
    Supports node-level re-evaluations for jobs matching retry conditions.
    """
    def __init__(self, llm_client: BaseLLM):
        self.llm_client = llm_client

    def match_jobs(self, filtered_jobs: List[Dict[str, Any]], retrieved_contexts: Dict[str, str], current_results: Dict[str, Dict[str, Any]], attempts: Dict[str, int]) -> Dict[str, Dict[str, Any]]:
        """
        Evaluates jobs. Re-evaluates jobs with low confidence if they are marked for retries.
        """
        logger.info(f"MatchingAgent: Evaluating {len(filtered_jobs)} filtered jobs.")
        results = dict(current_results)
        
        for job_dict in filtered_jobs:
            url = job_dict.get("job_url", "")
            context = retrieved_contexts.get(url, "")
            
            if not url or not context:
                continue
                
            # Check if this job has already been evaluated successfully with high confidence
            existing_result = results.get(url)
            attempt_count = attempts.get(url, 0)
            
            if existing_result and existing_result.get("confidence", 1.0) >= 0.5:
                # High confidence evaluation already exists, skip
                continue
                
            # If we are executing a retry evaluation, log it
            if attempt_count > 0:
                logger.info(f"MatchingAgent: Executing retry evaluation (Attempt: {attempt_count}) for '{job_dict.get('title')}' at '{job_dict.get('company')}' due to low confidence.")
            
            try:
                # Construct prompting context
                user_prompt = RAG_JOB_MATCH_USER_PROMPT.format(
                    retrieved_context=context,
                    job_title=job_dict.get("title", ""),
                    job_company=job_dict.get("company", ""),
                    job_location=job_dict.get("location", ""),
                    job_source=job_dict.get("source", ""),
                    job_description=job_dict.get("description", "")
                )
                
                # If this is a retry attempt, we can slightly alter system instruction or log details
                system_prompt = RAG_JOB_MATCH_SYSTEM_PROMPT
                if attempt_count > 0:
                    system_prompt += "\nNOTE: This is a double-check evaluation. Please pay extra attention to details and be decisive on score and confidence."
                
                # Execute LLM completion
                response_text = self.llm_client.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_format={"type": "json_object"}
                )
                
                # Validate structures
                evaluation = parse_and_validate_json(response_text, JobMatchResult).model_dump()
                results[url] = evaluation
                
                logger.info(
                    f"MatchingAgent: Evaluated '{job_dict.get('title')}' at '{job_dict.get('company')}'. "
                    f"Match Score: {evaluation.get('match_score')}, Confidence: {evaluation.get('confidence')}"
                )
                
            except Exception as e:
                logger.error(f"MatchingAgent: Evaluation failed for job URL {url}: {e}", exc_info=True)
                # Fail-safe result payload
                results[url] = {
                    "match_score": 0,
                    "should_apply": False,
                    "priority": "Low",
                    "summary": f"Evaluation error: {e}",
                    "strengths": [],
                    "missing_skills": [],
                    "learning_effort": "High",
                    "confidence": 0.0
                }
                
        return results
