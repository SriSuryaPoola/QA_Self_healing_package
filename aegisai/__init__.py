"""AegisAI public package surface."""

from .sdk import AegisAI
from .security import RiskLevel, SecurityDecision, SecurityOfficer, SecurityPolicy
from .state import is_state_poisoned, on_state_poisoned, set_state_poisoned

__version__ = "0.3.4"

__all__ = [
    "AegisAI",
    "RiskLevel",
    "SecurityDecision",
    "SecurityOfficer",
    "SecurityPolicy",
    "__version__",
    "is_state_poisoned",
    "on_state_poisoned",
    "set_state_poisoned",
]
