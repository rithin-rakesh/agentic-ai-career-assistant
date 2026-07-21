from abc import ABC, abstractmethod
from typing import List
from app.schemas.job import JobCreate

class BaseCollector(ABC):
    """
    Abstract Base Class for all job collectors.
    All source-specific collectors (e.g. Wellfound, LinkedIn) must inherit
    from this class and implement the collect method.
    """
    @abstractmethod
    def collect(self) -> List[JobCreate]:
        """
        Fetches jobs from the target source, parses them, validates them,
        and returns a list of JobCreate schema instances.
        
        The collector should NOT store the jobs in the database;
        database persistence is handled by the JobService layer.
        """
        pass
