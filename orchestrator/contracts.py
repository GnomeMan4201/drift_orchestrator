"""
drift_orchestrator — orchestrator/contracts.py
Shared contracts, enums, and data models for the router/audit/policy pipeline.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMPLEXITY_HIGH: float = 0.85
PRECISION_HIGH: float  = 0.85
MAX_RETRY_ATTEMPTS: int = 3


def make_request_id() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskType(str, Enum):
    TOOL_CLONE            = "tool_clone"
    STRUCTURED_EXTRACTION = "structured_extraction"
    CODE_GENERATION       = "code_generation"
    ANALYSIS              = "analysis"


class RouteDecision(str, Enum):
    PLANNER      = "planner"
    DIRECT_CODER = "direct_coder"


class ModelRole(str, Enum):
    PLANNER = "planner"
    CODER   = "coder"


class RiskPosture(str, Enum):
    CAUTIOUS  = "cautious"
    STANDARD  = "standard"
    PERMISSIVE = "permissive"


class AuditStatus(str, Enum):
    PASS                  = "pass"
    FAIL_CLOSED           = "fail_closed"
    RETRY_ALTERNATE_MODEL = "retry_alternate_model"
    RETRY_SAME_ROLE_STRICT = "retry_same_role_strict"
    REPLAN_AND_RECODE     = "replan_and_recode"


class FailureClass(str, Enum):
    GENERIC_FALLBACK  = "generic_fallback"
    PLANNER_VIOLATION = "planner_violation"
    COMPILE_FAILURE   = "compile_failure"
    RISK_INJECTION    = "risk_injection"
    SCHEMA_FAILURE    = "schema_failure"
    EMPTY_OUTPUT      = "empty_output"


class RetryAction(str, Enum):
    PASS                   = "pass"
    FAIL_CLOSED            = "fail_closed"
    RETRY_ALTERNATE_MODEL  = "retry_alternate_model"
    RETRY_SAME_ROLE_STRICT = "retry_same_role_strict"
    REPLAN_AND_RECODE      = "replan_and_recode"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RouterTicket:
    request_id:           str
    original_prompt:      str
    normalized_prompt:    str
    route_decision:       RouteDecision
    task_type:            TaskType
    complexity:           float               = 0.5
    precision:            float               = 0.5
    risk_posture:         RiskPosture         = RiskPosture.STANDARD
    needs_decomposition:  bool                = False
    needs_verification:   bool                = False
    needs_code_validation: bool               = False
    preferred_model_role:  ModelRole | None   = None
    secondary_model_role:  ModelRole | None   = None
    routing_reason:        str                = ""
    routing_confidence:    float              = 1.0
    forbidden_patterns:    list[str]          = field(default_factory=list)
    required_outputs:      list[str]          = field(default_factory=list)


@dataclass
class PlannerSpec:
    request_id:                str
    planner_status:            str
    task_type:                 TaskType
    mechanism_summary:         str
    subsystems:                list[str]       = field(default_factory=list)
    implementation_requirements: list[str]    = field(default_factory=list)
    validation_targets:        list[str]       = field(default_factory=list)
    forbidden_patterns:        list[str]       = field(default_factory=list)
    coder_instructions:        str             = ""


@dataclass
class CoderOutput:
    request_id:    str
    model_name:    str
    model_role:    ModelRole
    raw_output:    str
    cleaned_output: str
    output_mode:   str   = "code"   # "code" | "json"
    attempt_number: int  = 1


@dataclass
class AuditResult:
    request_id:          str                  = field(default_factory=make_request_id)
    audit_status:        AuditStatus          = AuditStatus.PASS
    passed:              bool                 = True
    failure_class:       FailureClass | None  = None
    drift_score:         float                = 0.0
    external_score:      float                = 0.0
    verification_passed: bool                 = True
    reasons:             list[str]            = field(default_factory=list)
    next_action:         RetryAction          = RetryAction.PASS
    next_model_role:     ModelRole | None     = None
    generic_hits:        list[str]            = field(default_factory=list)
    spec_violations:     list[str]            = field(default_factory=list)
    compile_error:       str | None           = None
    detail:              str                  = ""
