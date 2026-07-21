from pydantic import BaseModel, Field
from typing import List

class UserPreferences(BaseModel):
    """
    Pydantic schema representing candidate career preferences.
    Used for filtering and highlighting relevant opportunities.
    """
    preferred_locations: List[str] = Field(default_factory=list)
    preferred_technologies: List[str] = Field(default_factory=list)
    favorite_companies: List[str] = Field(default_factory=list)
    ignored_companies: List[str] = Field(default_factory=list)
