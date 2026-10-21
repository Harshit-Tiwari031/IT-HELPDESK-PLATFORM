"""Deterministic, side-effect-free simulations. These never access a real device."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    output: dict[str, Any]
    passed: bool | None
    reason: str


ALLOWED_TOOLS = {
    "simulated_network_connectivity": "Network connectivity check",
    "simulated_dns_resolution": "DNS resolution check",
    "simulated_service_health": "Service health check",
    "simulated_account_access": "Account access check",
}


def select_tool(issue: str, category: str) -> str:
    text = issue.casefold()
    if any(word in text for word in ("dns", "domain name", "website not found")):
        return "simulated_dns_resolution"
    if any(word in text for word in ("account", "login", "sign in", "password", "access", "mfa")):
        return "simulated_account_access"
    if any(word in text for word in ("service", "application", "app", "email", "outlook")):
        return "simulated_service_health"
    if category == "Network" or any(word in text for word in ("wifi", "wi-fi", "vpn", "internet", "network", "connect")):
        return "simulated_network_connectivity"
    return "simulated_service_health"


def execute_simulated_tool(tool_name: str, issue: str) -> ToolResult:
    """Execute an allowlisted simulation; reject unknown names and ignore arbitrary arguments."""
    if tool_name not in ALLOWED_TOOLS:
        raise ValueError("Tool is not in the simulated tool allowlist.")
    label = ALLOWED_TOOLS[tool_name]
    # An intentionally synthetic result suitable for teaching and UI demonstration only.
    if tool_name == "simulated_account_access":
        return ToolResult(
            output={"label": "SIMULATED", "tool": label, "result": "No account was accessed; live identity verification is unavailable."},
            passed=None,
            reason="Account checks require the user or campus IT to verify identity and live access.",
        )
    return ToolResult(
        output={"label": "SIMULATED", "tool": label, "result": "Sample check completed; no device, network, or service was contacted."},
        passed=True,
        reason="The deterministic demo check returned its expected sample response; this does not verify the user's real environment.",
    )
