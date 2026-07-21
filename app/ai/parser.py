import re
import json
from typing import Type, TypeVar, Any
from pydantic import BaseModel
from app.logger import logger

T = TypeVar("T", bound=BaseModel)

def clean_json_string(raw_text: str) -> str:
    """
    Cleans markdown formatting codeblocks and leading/trailing whitespace
    from LLM responses to isolate the raw JSON payload.
    """
    if not raw_text:
        return ""
        
    cleaned = raw_text.strip()
    
    # 1. Match code blocks e.g. ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
        
    # 2. Basic cleanup for any weird characters before first '{' and after last '}'
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1:
        cleaned = cleaned[first_brace : last_brace + 1]
        
    return cleaned

def parse_and_validate_json(raw_text: str, model: Type[T]) -> T:
    """
    Extracts, parses, and validates a JSON string from LLM output.
    Raises ValueError or pydantic ValidationError if parsing fails.
    """
    cleaned_str = clean_json_string(raw_text)
    
    if not cleaned_str:
        raise ValueError("Could not extract any JSON block from LLM output text.")
        
    try:
        data = json.loads(cleaned_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON string: {cleaned_str}")
        raise ValueError(f"JSON formatting error in LLM output: {e}") from e
        
    try:
        # Validate and return Pydantic object
        return model.model_validate(data)
    except Exception as e:
        logger.error(f"Pydantic validation failed for model {model.__name__} against data: {data}")
        raise
