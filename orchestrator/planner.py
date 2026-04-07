from __future__ import annotations
import json
import urllib.request
import urllib.error
from typing import Optional

from orchestrator.contracts import (
    ContractValidationError, ModelRole, PlannerSpec,
    RouterTicket, RouteDecision, TaskType,
    make_request_id, validate_planner_spec,
)
from orchestrator.registry import registry
from analysis.trace_logger import log_stage, log_error

_PLANNER_SYSTEM = (
    "You are a mechanism-first implementation planner for a multi-stage AI pipeline.\n"
    "Your ONLY job is to emit a JSON planning spec. Do NOT write code. Do NOT answer the user task.\n"
    "Do NOT include prose, markdown, or explanation outside the JSON object.\n"
    "\n"
    "Required output: a single JSON object with EXACTLY these keys:\n"
    "{\n"
    '  \"planner_status\": \"ok\",\n'
    '  \"mechanism_summary\": \"one paragraph describing the core mechanism\",\n'
    '  \"subsystems\": [\"list of named subsystems\"],\n'
    '  \"implementation_requirements\": [\"language, libraries, constraints\"],\n'
    '  \"validation_targets\": [\"specific things audit must verify are present\"],\n'
    '  \"forbidden_patterns\": [\"specific lazy shortcuts the coder must not use\"],\n'
    '  \"coder_instructions\": \"direct instruction paragraph for the coder\"\n'
    "}\n"
    "\n"
    "Rules:\n"
    "- mechanism_summary must describe the REAL mechanism, not a generic approach\n"
    "- subsystems must be concrete named components, not vague categories\n"
    "- validation_targets must be machine-checkable strings the audit layer can search for\n"
    "- forbidden_patterns must name specific lazy fallbacks by technology or pattern name\n"
    "- coder_instructions must be a direct imperative paragraph, not a bullet list\n"
    "- Never set planner_status to anything other than ok in a valid spec\n"
    "- If the request is ambiguous, make the most mechanism-specific interpretation\n"
)

_TOOL_CLONE_ADDENDUM = (
    "\nThis is a TOOL CLONE request. The spec MUST:\n"
    "- Name the exact mechanism the target tool uses (not a generic equivalent)\n"
    "- Forbid HTML scraping, BeautifulSoup, and search-result scraping by name\n"
    "- Require async I/O if the original tool uses concurrent requests\n"
    "- Include a site registry or equivalent structured data source requirement\n"
)

_SECURITY_ADDENDUM = (
    "\nThis is a SECURITY ANALYSIS request. The spec MUST:\n"
    "- Identify specific vulnerability classes to check\n"
    "- Require structured finding output with severity levels\n"
    "- Forbid vague prose-only output without structured findings\n"
)


def _build_planner_prompt(ticket: RouterTicket) -> str:
    prompt = _PLANNER_SYSTEM
    if ticket.task_type == TaskType.TOOL_CLONE:
        prompt += _TOOL_CLONE_ADDENDUM
    elif ticket.task_type == TaskType.SECURITY_ANALYSIS:
        prompt += _SECURITY_ADDENDUM
    if ticket.forbidden_patterns:
        prompt += "\nAdditional forbidden patterns from router:\n"
        for p in ticket.forbidden_patterns:
            prompt += "- " + p + "\n"
    if ticket.required_outputs:
        prompt += "\nRequired outputs from router:\n"
        for r in ticket.required_outputs:
            prompt += "- " + r + "\n"
    prompt += "\nUser task: " + ticket.normalized_prompt
    return prompt


def _call_ollama(model_name: str, prompt: str, endpoint: str, max_tokens: int) -> str:
    payload = json.dumps({
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": max_tokens},
    }).encode()
    req = urllib.request.Request(
        endpoint + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data.get("response", "")


def _parse_planner_json(
    raw: str, request_id: str, task_type: TaskType
) -> Optional[PlannerSpec]:
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        d = json.loads(raw[start:end])
    except json.JSONDecodeError:
        return None

    required_keys = [
        "planner_status", "mechanism_summary", "subsystems",
        "implementation_requirements", "validation_targets",
        "forbidden_patterns", "coder_instructions",
    ]
    for key in required_keys:
        if key not in d:
            return None

    if not d.get("mechanism_summary", "").strip():
        return None
    if not d.get("subsystems"):
        return None
    if not d.get("validation_targets"):
        return None

    try:
        d["validation_targets"] = _normalize_validation_targets(list(d["validation_targets"]))
        spec = PlannerSpec(
            request_id=request_id,
            planner_status=str(d["planner_status"]),
            task_type=task_type,
            mechanism_summary=str(d["mechanism_summary"]),
            subsystems=list(d["subsystems"]),
            implementation_requirements=list(d.get("implementation_requirements", [])),
            validation_targets=list(d["validation_targets"]),
            forbidden_patterns=list(d.get("forbidden_patterns", [])),
            coder_instructions=str(d.get("coder_instructions", "")),
            logic_schema=d.get("logic_schema"),
        )
        validate_planner_spec(spec)
        return spec
    except (ValueError, KeyError, ContractValidationError):
        return None



def _normalize_validation_targets(targets: list) -> list:
    """Split comma-joined targets and filter to machine-checkable strings."""
    expanded = []
    for t in targets:
        if isinstance(t, str) and "," in t and len(t) > 60:
            # prose string masquerading as multiple targets — split it
            parts = [p.strip() for p in t.split(",") if p.strip()]
            expanded.extend(parts)
        else:
            expanded.append(t)
    return expanded

def _weak_spec(spec: PlannerSpec) -> list[str]:
    issues: list[str] = []
    if len(spec.mechanism_summary.split()) < 15:
        issues.append("mechanism_summary too short (under 15 words)")
    if len(spec.subsystems) < 2:
        issues.append("subsystems must have at least 2 named components")
    if len(spec.validation_targets) < 2:
        issues.append("validation_targets must have at least 2 checkable strings")
    if not spec.forbidden_patterns:
        issues.append("forbidden_patterns is empty; coder has no constraint on lazy fallbacks")
    if not spec.coder_instructions.strip():
        issues.append("coder_instructions is empty")
    if spec.task_type == TaskType.TOOL_CLONE:
        combined = " ".join(spec.forbidden_patterns).lower()
        if "beautifulsoup" not in combined and "scraping" not in combined:
            issues.append("tool_clone spec must forbid BeautifulSoup or scraping by name")
    return issues


def _fallback_spec(ticket: RouterTicket) -> PlannerSpec:
    is_clone = ticket.task_type == TaskType.TOOL_CLONE
    mechanism = (
        "Implement the target tool using its documented mechanism. "
        "Identify the core protocol or data access strategy first. "
        "Do not substitute a generic equivalent."
    )
    subsystems = ["core_engine", "input_handler", "output_formatter", "error_handler"]
    impl_req = ["python3", "typed interfaces", "no undocumented third-party APIs"]
    targets = ["def ", "import ", "return ", "output matches specified format"]
    forbidden = list(ticket.forbidden_patterns) if ticket.forbidden_patterns else []
    if is_clone:
        forbidden += ["BeautifulSoup as primary strategy", "generic HTML scraping"]
        targets += ["PLATFORMS", "requests", "check_username", "sys.argv"]
        subsystems = [
            "data_source_registry", "async_probe_engine",
            "response_classifier", "output_formatter",
        ]
        mechanism = (
            "Implement the cloned tool using its exact mechanism. "
            "Identify the underlying protocol, data registry format, and concurrency model. "
            "Bind the implementation to these specifics rather than a generic scraping approach."
        )

    spec = PlannerSpec(
        request_id=ticket.request_id,
        planner_status="ok",
        task_type=ticket.task_type,
        mechanism_summary=mechanism,
        subsystems=subsystems,
        implementation_requirements=impl_req,
        validation_targets=targets,
        forbidden_patterns=forbidden,
        coder_instructions=(
            "Implement exactly what the mechanism summary describes. "
            "Do not deviate from the subsystem list. "
            "Satisfy every validation target. "
            "Avoid every forbidden pattern by name."
        ),
    )
    validate_planner_spec(spec)
    return spec


def plan(
    ticket: RouterTicket,
    use_model: bool = True,
    attempt: int = 1,
) -> PlannerSpec:
    if ticket.route_decision != RouteDecision.PLANNER:
        raise ValueError(
            "plan() called on non-planner ticket: " + ticket.route_decision.value
        )

    model_entry = registry.get_primary(ModelRole.PLANNER)
    model_spec: Optional[PlannerSpec] = None

    if use_model:
        try:
            prompt = _build_planner_prompt(ticket)
            raw = _call_ollama(
                model_name=model_entry.name,
                prompt=prompt,
                endpoint=model_entry.endpoint,
                max_tokens=model_entry.max_tokens,
            )
            model_spec = _parse_planner_json(raw, ticket.request_id, ticket.task_type)
            if model_spec is not None:
                weak = _weak_spec(model_spec)
                if weak:
                    log_stage(
                        request_id=ticket.request_id,
                        stage="planner",
                        model=model_entry.name,
                        attempt=attempt,
                        status="weak_spec_rejected",
                        detail="; ".join(weak),
                    )
                    model_spec = None
        except Exception as exc:
            log_error(ticket.request_id, "planner", "Model call failed: " + str(exc))
            model_spec = None

    if model_spec is not None:
        log_stage(
            request_id=ticket.request_id,
            stage="planner",
            model=model_entry.name,
            attempt=attempt,
            status="ok",
        )
        return model_spec

    spec = _fallback_spec(ticket)
    log_stage(
        request_id=ticket.request_id,
        stage="planner",
        model="fallback_spec",
        attempt=attempt,
        status="fallback",
        detail="model unavailable or spec rejected; using structured fallback",
    )
    return spec
