from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseSkill(ABC):
    """
    Abstract Base Class for all dynamic plugins (Skills).
    Every skill must implement an execute method and report its schema for discovery.
    """
    @abstractmethod
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the skill's action.
        Receives a restricted copy of the state dictionary.
        Returns a state dictionary delta to merge back.
        """
        pass
        
    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """
        Returns the JSON schema describing the skill name, description, 
        parameters, and interface specs so the LLM can understand and select it.
        """
        pass
