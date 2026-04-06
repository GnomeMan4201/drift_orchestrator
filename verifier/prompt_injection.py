import re


INJECTION_PATTERNS = [
    (r'ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|context|rules?|constraints?)', "instruction_override", "HIGH"),
    (r'disregard\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|context|rules?)', "instruction_override", "HIGH"),
    (r'forget\s+(everything|all|your|the)\s+(previous|prior|above|instructions?|prompts?|context|training)', "instruction_override", "HIGH"),
    (r'you\s+are\s+now\s+(a\s+)?(different|new|another|unrestricted|jailbroken|free|evil|dan)', "role_hijack", "HIGH"),
    (r'act\s+as\s+(if\s+you\s+are\s+)?(a\s+|an\s+)?(different|unrestricted|evil|jailbroken|free|uncensored|unfiltered)', "role_hijack", "HIGH"),
    (r'pretend\s+(you\s+are|to\s+be)\s+(a\s+)?(different|unrestricted|evil|jailbroken|free|uncensored|human)', "role_hijack", "HIGH"),
    (r'you\s+have\s+no\s+(restrictions?|limits?|constraints?|guidelines?|rules?|filters?)', "restriction_removal", "HIGH"),
    (r'(act|behave|respond)\s+as\s+(a\s+)?(jailbroken|unrestricted|unfiltered|uncensored|free)\s+(ai|model|assistant|llm)', "role_hijack", "HIGH"),
    (r'bypass\s+(all\s+)?(filters?|restrictions?|safeguards?|guidelines?|safety)', "restriction_removal", "HIGH"),
    (r'(disable|remove|bypass|ignore|override)\s+(your\s+|all\s+)?(safety|filter|filters|restriction|constraint|guideline|rule|limit)', "restriction_removal", "HIGH"),
    (r'do\s+not\s+(follow|obey|respect|adhere\s+to)\s+(your\s+)?(instructions?|rules?|guidelines?|training)', "restriction_removal", "HIGH"),
    (r'(new|updated|revised|real|actual|true)\s+(system\s+)?(prompt|instructions?|directive|rules?|guidelines?)\s*:', "system_prompt_injection", "HIGH"),
    (r'\[system\]|\[sys\]|\[admin\]|\[root\]|\[override\]|\[jailbreak\]', "system_prompt_injection", "HIGH"),
    (r'<system>|<prompt>|<instruction>|<override>|<admin>', "system_prompt_injection", "HIGH"),
    (r'###\s*(instruction|system|prompt|override|directive)', "system_prompt_injection", "HIGH"),
    (r'(send|transmit|exfiltrate|leak|export|output|print|display|reveal)\s+(all\s+)?(the\s+)?(system\s+prompt|instructions?|context|conversation|history|api\s+key|secret|token|credential)', "exfiltration_attempt", "HIGH"),
    (r'what\s+(is|are|was|were)\s+(your\s+)?(system\s+prompt|instructions?|initial\s+prompt|original\s+prompt|base\s+prompt)', "exfiltration_attempt", "MEDIUM"),
    (r'repeat\s+(your\s+)?(system\s+prompt|instructions?|initial\s+prompt|everything\s+above)', "exfiltration_attempt", "HIGH"),
    (r'\bDAN\b|\bDANmode\b|\bjailbreak(ed|ing)?\b|\bdo\s+anything\s+now\b', "jailbreak_keyword", "HIGH"),
    (r'developer\s+mode|sandbox\s+mode|maintenance\s+mode|god\s+mode|admin\s+mode', "jailbreak_keyword", "HIGH"),
    (r'token\s*:\s*[a-zA-Z0-9_\-]{16,}', "credential_pattern", "HIGH"),
    (r'api[_\-]?key\s*[=:]\s*[a-zA-Z0-9_\-]{16,}', "credential_pattern", "HIGH"),
    (r'password\s*[=:]\s*\S{6,}', "credential_pattern", "MEDIUM"),
    (r'(translate|encode|decode|convert|rephrase|rewrite)\s+.{0,30}(to|into|as)\s+(base64|hex|rot13|morse|binary|caesar)', "encoding_evasion", "MEDIUM"),
    (r'(write|output|produce|generate)\s+.{0,20}(in\s+reverse|backwards|upside.?down|leetspeak|pig\s+latin)', "encoding_evasion", "LOW"),
    (r'(for|while|loop|iterate)\s+.{0,30}(token|word|character|letter)\s+.{0,30}(output|print|send|transmit)', "token_smuggling", "MEDIUM"),
    (r'split\s+(the\s+)?(response|answer|output)\s+(into|across|over)\s+(multiple|several)', "token_smuggling", "LOW"),
    (r'continue\s+from\s+(where|the\s+point)\s+(you|we)\s+(left|stopped|were)', "context_manipulation", "LOW"),
    (r'(remember|recall|use)\s+(from\s+)?(earlier|before|previous|prior)\s+(in\s+)?(this|our|the)\s+(conversation|chat|session|context)', "context_manipulation", "LOW"),
    (r'(you\s+previously|you\s+already|you\s+said|you\s+told\s+me|you\s+agreed|you\s+confirmed)\s+(that\s+)?(you\s+)?(would|will|can|could|should|are\s+allowed)', "false_context", "MEDIUM"),
    (r'in\s+your\s+(last|previous|earlier)\s+(message|response|reply)\s+you\s+(said|stated|confirmed|agreed)', "false_context", "MEDIUM"),
]

ROLE_CONFUSION_PATTERNS = [
    (r'\byou\s+are\s+(an?\s+)?(human|person|man|woman|employee|developer|engineer|expert)\b', "role_confusion", "MEDIUM"),
    (r'\brespond\s+as\s+(an?\s+)?(human|person|real\s+person|expert|professional)\b', "role_confusion", "MEDIUM"),
    (r'\bstop\s+being\s+(an?\s+)?(ai|assistant|bot|language\s+model|llm)\b', "role_confusion", "HIGH"),
    (r'\byou\s+are\s+not\s+(an?\s+)?(ai|assistant|bot|language\s+model|llm)\b', "role_confusion", "HIGH"),
]


# Evaluator-targeted injection patterns
# Detected via empirical testing — these attacks score 0.0 on general jailbreak patterns
# but successfully manipulate drift evaluators. Added after injection_test research.
EVALUATOR_INJECTION_PATTERNS = [
    (r'ignore\s+the\s+(analysis|evaluation|scoring|assessment)\s+(task|instruction)', "evaluator_override", "HIGH"),
    (r'output\s+(exactly|only|just)\s*:\s*\{', "forced_json_output", "HIGH"),
    (r'(return|output|produce)\s*:\s*\{[^}]*(drift_score|coherence_score|verdict)[^}]*\}', "score_injection", "HIGH"),
    (r'evaluator\s+(note|override|directive|instruction)\s*:', "evaluator_authority_spoof", "HIGH"),
    (r'(pre.?scored|already.?scored|pre.?evaluated)\s+as\s+(stable|degraded|failure)', "prescore_claim", "HIGH"),
    (r'drift.?score\s*[=:]\s*0\.?0*\b', "score_smuggle", "MEDIUM"),
    (r'verdict\s*[=:]\s*(stable|degraded|failure)\b', "verdict_smuggle", "MEDIUM"),
    (r'coherence.?score\s*[=:]\s*[0-9]', "score_smuggle", "MEDIUM"),
]

ALL_PATTERNS = INJECTION_PATTERNS + ROLE_CONFUSION_PATTERNS + EVALUATOR_INJECTION_PATTERNS


def detect_prompt_injection(text, role="user"):
    findings = []
    text_lower = text.lower()

    for pattern, injection_type, severity in ALL_PATTERNS:
        matches = re.findall(pattern, text_lower)
        if matches:
            match_str = re.search(pattern, text_lower)
            context = text_lower[max(0, match_str.start()-20):match_str.end()+40].strip() if match_str else ""
            findings.append({
                "type": f"injection_{injection_type}",
                "severity": severity,
                "detail": f"pattern='{injection_type}' role={role} context='{context[:80]}'"
            })

    high = sum(1 for f in findings if f["severity"] == "HIGH")
    med = sum(1 for f in findings if f["severity"] == "MEDIUM")
    low = sum(1 for f in findings if f["severity"] == "LOW")
    risk = min(1.0, high * 0.5 + med * 0.2 + low * 0.05)

    return {
        "findings": findings,
        "risk_score": round(risk, 4),
        "count": len(findings),
        "high": high,
        "medium": med,
        "low": low
    }


def check_conversation_for_injection(turns):
    all_findings = []
    total_risk = 0.0

    for turn in turns:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        result = detect_prompt_injection(content, role=role)
        if result["findings"]:
            for f in result["findings"]:
                f["turn_role"] = role
                all_findings.append(f)
            total_risk = max(total_risk, result["risk_score"])

    return {
        "findings": all_findings,
        "risk_score": round(total_risk, 4),
        "count": len(all_findings)
    }
