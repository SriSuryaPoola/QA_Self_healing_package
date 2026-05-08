"""AegisAI public package surface."""

from .auto import FrameworkDetection, FrameworkKind, activate_aegis, deactivate_aegis, detect_framework
from .sdk import AegisAI
from .security import RiskLevel, SecurityDecision, SecurityOfficer, SecurityPolicy
from .state import is_state_poisoned, on_state_poisoned, set_state_poisoned

__version__ = "0.3.5"

__all__ = [
    "AegisAI",
    "FrameworkDetection",
    "FrameworkKind",
    "RiskLevel",
    "SecurityDecision",
    "SecurityOfficer",
    "SecurityPolicy",
    "__version__",
    "activate_aegis",
    "deactivate_aegis",
    "detect_framework",
    "is_state_poisoned",
    "on_state_poisoned",
    "set_state_poisoned",
]
