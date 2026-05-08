"""AegisAI public package surface."""

from .auto import FrameworkDetection, FrameworkKind, activate_aegis, deactivate_aegis, detect_framework
from .artifacts import capture_debug_artifacts
from .dry_run import DryRunResult, audit_locator
from .drift import DomDrift, detect_dom_drift
from .reporting import HealingEvent, HealingReport, get_session_report, reset_session_report
from .sdk import AegisAI
from .security import RiskLevel, SecurityDecision, SecurityOfficer, SecurityPolicy, load_security_policy
from .state import is_state_poisoned, on_state_poisoned, set_state_poisoned

__version__ = "0.3.6"

__all__ = [
    "AegisAI",
    "DryRunResult",
    "DomDrift",
    "FrameworkDetection",
    "FrameworkKind",
    "HealingEvent",
    "HealingReport",
    "RiskLevel",
    "SecurityDecision",
    "SecurityOfficer",
    "SecurityPolicy",
    "__version__",
    "activate_aegis",
    "audit_locator",
    "capture_debug_artifacts",
    "deactivate_aegis",
    "detect_framework",
    "detect_dom_drift",
    "get_session_report",
    "is_state_poisoned",
    "load_security_policy",
    "on_state_poisoned",
    "reset_session_report",
    "set_state_poisoned",
]
