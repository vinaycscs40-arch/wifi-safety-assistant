"""
Agent 3: Incident Response & Safety Guidance Agent
Receives aggregated findings from Agents 1 & 2.
Provides incident response, phishing awareness, and generates final safety report.
Uses Gemini (secondary model) with Granite as backup.
"""
import re
import json
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Official Indian cybersecurity reporting resources
# ---------------------------------------------------------------------------
REPORTING_RESOURCES = [
    {
        "name": "National Cyber Crime Reporting Portal",
        "url": "https://cybercrime.gov.in/",
        "helpline": "1930",
        "description": "Report cyber crimes including phishing, fraud and account compromise",
    },
    {
        "name": "CERT-In (Indian Computer Emergency Response Team)",
        "url": "https://www.cert-in.org.in/",
        "email": "cert-in@cert-in.org.in",
        "description": "Report cybersecurity incidents and get advisories",
    },
    {
        "name": "I4C (Indian Cyber Crime Coordination Centre)",
        "url": "https://i4c.mha.gov.in/",
        "description": "MHA's coordinating body for cybercrime response",
    },
    {
        "name": "RBI Ombudsman (for banking fraud)",
        "url": "https://cms.rbi.org.in/",
        "helpline": "14448",
        "description": "Report banking fraud and unauthorized transactions",
    },
]

PHISHING_INDICATORS = [
    "asks for password on login portal",
    "unexpected login page",
    "certificate error",
    "ssl warning",
    "redirected to unknown site",
    "pop-up asking for credentials",
    "suspicious redirect",
    "unfamiliar captive portal",
    "login page looks like bank",
    "sent otp on unknown site",
]

IMMEDIATE_RESPONSE_BY_SCENARIO = {
    "phishing": [
        "Do NOT enter any credentials on the suspicious page",
        "Close the browser immediately",
        "Disconnect from the Wi-Fi network",
        "Change passwords for any accounts you may have accessed",
        "Enable 2FA on affected accounts immediately",
        "Check your bank/UPI for unauthorized transactions",
        "Report the incident at cybercrime.gov.in or call 1930",
    ],
    "account_compromise": [
        "Change passwords for ALL accounts accessed on this network",
        "Start with email, then banking, then social media",
        "Enable two-factor authentication on all accounts",
        "Check active sessions in account settings and log out all unknown devices",
        "Alert your bank to watch for suspicious transactions",
        "Report to National Cyber Crime Reporting Portal (1930)",
        "Consider informing your contacts if social media was compromised",
    ],
    "fake_portal": [
        "Immediately disconnect from the network",
        "Do NOT enter any information on the portal",
        "If you entered credentials: change those passwords immediately",
        "Report the fake access point location to CERT-In",
        "Warn others around you about the suspicious network",
    ],
    "general": [
        "Disconnect from the suspicious network",
        "Switch to mobile data (4G/5G)",
        "Monitor accounts for unusual activity",
        "Keep emergency contacts handy: Cyber Helpline 1930",
    ],
}


class IncidentResponseAgent:
    """
    Agent 3 – Incident Response & Safety Guidance.
    
    Responsibilities:
    - Receive findings from Agents 1 & 2
    - Provide incident response for phishing/account compromise/fake portals
    - Direct users to official reporting resources
    - Generate comprehensive final safety report
    """

    AGENT_NAME = "Agent 3: Incident Response & Safety Guidance"
    PRIMARY_PROVIDER = "gemini"    # Gemini for incident response (Groq disabled)
    BACKUP_PROVIDER = "granite"    # Fallback to Granite if Gemini unavailable

    SYSTEM_PROMPT = """You are an incident response specialist for cybersecurity in India.
You have received a complete risk assessment and device safety analysis.
Your job is to provide clear incident response guidance and generate a final safety report.

RULES:
- Provide actionable, immediate steps for the specific risk scenario
- Reference official Indian resources: CERT-In, I4C, cybercrime.gov.in, helpline 1930
- Use clear, simple language for non-technical users  
- Never claim any network is safe
- Prioritize user safety and data protection

Return JSON with these exact keys:
{
  "incident_scenario": "identified scenario: phishing | account_compromise | fake_portal | suspicious_network | general",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "situation_summary": "plain language summary of the situation",
  "immediate_steps": ["ordered list of immediate actions to take"],
  "if_credentials_entered": "specific advice if user already entered credentials",
  "reporting_guidance": "how and where to report this incident",
  "prevention_summary": "3-4 key points to prevent this in future",
  "bengaluru_transit_tip": "specific tip for Bengaluru metro/bus/railway station users"
}"""

    def __init__(self, ai_manager):
        self.ai = ai_manager
        logger.info(f"{self.AGENT_NAME} initialized")

    def respond(
        self,
        agent1_output: Dict[str, Any],
        agent2_output: Dict[str, Any],
        task_id: str = None,
    ) -> Dict[str, Any]:
        """
        Main entry point.
        Synthesizes all findings and produces incident response + final report.
        """
        risk_level = agent1_output.get("risk_level", "MEDIUM")
        wifi_name = agent1_output.get("input", {}).get("wifi_name", "unknown")
        location = agent1_output.get("input", {}).get("location", "unknown")
        warning_signs = agent1_output.get("warning_signs", [])
        user_context = agent1_output.get("input", {}).get("user_context", "")

        logger.info(
            f"[{self.AGENT_NAME}] Processing final report: risk={risk_level} "
            f"wifi='{wifi_name}'"
        )

        # Determine incident scenario from context
        scenario = self._identify_scenario(warning_signs, user_context)
        immediate_steps = IMMEDIATE_RESPONSE_BY_SCENARIO.get(
            scenario, IMMEDIATE_RESPONSE_BY_SCENARIO["general"]
        )

        prompt = f"""{self.SYSTEM_PROMPT}

## Complete Assessment Summary

### From Agent 1 (Network Risk Assessment):
- **Risk Level:** {risk_level}
- **Wi-Fi Network:** {wifi_name}
- **Location:** {location}
- **Warning Signs:** {', '.join(warning_signs) if warning_signs else 'None detected'}
- **Risk Explanation:** {agent1_output.get('explanation', '')}

### From Agent 2 (Device Safety):
- **Threat Explanation:** {agent2_output.get('threat_explanation', '')}
- **Immediate Actions Recommended:** {', '.join(agent2_output.get('immediate_actions', [])[:3])}

### User Additional Context:
{user_context or 'No additional context provided'}

Identified Scenario: {scenario}

Provide a comprehensive incident response and final safety report as JSON.
Return ONLY valid JSON, no markdown fences."""

        # Try primary (Groq) then backup (Gemini)
        result = self.ai.generate(
            prompt=prompt,
            provider=self.PRIMARY_PROVIDER,
            max_tokens=900,
            temperature=0.2,
        )
        if not result["success"]:
            logger.warning(f"[{self.AGENT_NAME}] Primary provider failed, trying backup")
            result = self.ai.generate(
                prompt=prompt,
                provider=self.BACKUP_PROVIDER,
                max_tokens=900,
                temperature=0.2,
            )

        agent_output: Dict[str, Any] = {
            "agent": self.AGENT_NAME,
            "task_id": task_id,
            "status": "complete" if result["success"] else "complete_with_fallback",
            "model_used": result.get("model", "unknown"),
            "provider": result.get("provider", "unknown"),
            "duration_ms": result.get("duration_ms", 0),
            "risk_level_received": risk_level,
            "identified_scenario": scenario,
            "immediate_response_steps": immediate_steps,
            "reporting_resources": REPORTING_RESOURCES,
        }

        if result["success"]:
            parsed = self._parse_llm_output(result["text"], scenario, risk_level,
                                            wifi_name, location)
            agent_output.update(parsed)
        else:
            agent_output.update(self._fallback_response(scenario, risk_level,
                                                        wifi_name, location))
            agent_output["error"] = result.get("error")

        # Always generate a structured final report
        agent_output["final_report"] = self._generate_final_report(
            agent1_output, agent2_output, agent_output, task_id
        )

        logger.info(
            f"[{self.AGENT_NAME}] Done: scenario={scenario} "
            f"in {agent_output.get('duration_ms',0)}ms"
        )
        return agent_output

    def _identify_scenario(self, warning_signs: List[str],
                           user_context: str) -> str:
        ctx = (user_context or "").lower()
        signs = " ".join(warning_signs).lower() if warning_signs else ""
        combined = ctx + " " + signs

        if any(w in combined for w in ["phishing", "login portal", "fake portal",
                                        "redirected", "sent otp"]):
            return "phishing"
        if any(w in combined for w in ["account", "compromised", "logged in",
                                        "unauthorized", "hacked"]):
            return "account_compromise"
        if any(w in combined for w in ["fake", "impersonate", "evil twin",
                                        "duplicate", "same name"]):
            return "fake_portal"
        return "general"

    def _parse_llm_output(self, text: str, scenario: str, risk_level: str,
                          wifi_name: str, location: str) -> Dict[str, Any]:
        clean = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
        try:
            return json.loads(clean)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Agent3: LLM JSON parse failed, using fallback")
            return self._fallback_response(scenario, risk_level, wifi_name, location)

    def _fallback_response(self, scenario: str, risk_level: str,
                           wifi_name: str, location: str) -> Dict[str, Any]:
        severity_map = {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}
        return {
            "incident_scenario": scenario,
            "severity": severity_map.get(risk_level, "MEDIUM"),
            "situation_summary": (
                f"You are connected to '{wifi_name}' at {location}, "
                f"which has been assessed as {risk_level} risk. "
                f"This falls under the '{scenario}' scenario category."
            ),
            "immediate_steps": IMMEDIATE_RESPONSE_BY_SCENARIO.get(
                scenario, IMMEDIATE_RESPONSE_BY_SCENARIO["general"]
            ),
            "if_credentials_entered": (
                "If you entered any passwords or sensitive information: "
                "immediately change those passwords, enable 2FA, "
                "check bank statements, and report to 1930."
            ),
            "reporting_guidance": (
                "Report at cybercrime.gov.in or call the Cyber Crime Helpline 1930. "
                "For cybersecurity incidents, email CERT-In: cert-in@cert-in.org.in"
            ),
            "prevention_summary": (
                "1. Always use a VPN on public Wi-Fi. "
                "2. Use mobile data for banking. "
                "3. Verify network names with staff before connecting. "
                "4. Enable 2FA on all important accounts."
            ),
            "bengaluru_transit_tip": (
                "On Namma Metro, KSRTC, or BMTC: verify the official network name "
                "with station staff before connecting. "
                "Use BSNL/Jio/Airtel 4G for sensitive activities. "
                "Cyber Crime Helpline: 1930"
            ),
        }

    def _generate_final_report(
        self,
        agent1: Dict, agent2: Dict, agent3: Dict, task_id: str
    ) -> Dict[str, Any]:
        """Generate structured final safety report combining all three agents."""
        risk = agent1.get("risk_level", "UNKNOWN")
        risk_colors = {"HIGH": "#ef4444", "MEDIUM": "#f59e0b", "LOW": "#22c55e",
                       "UNKNOWN": "#6b7280"}

        checklist = agent2.get("device_checklist", [])
        critical_items = [i for i in checklist if i.get("priority") == "CRITICAL"]
        high_items = [i for i in checklist if i.get("priority") == "HIGH"]

        return {
            "report_id": task_id or "N/A",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "risk_level": risk,
            "risk_color": risk_colors.get(risk, "#6b7280"),
            "network": agent1.get("input", {}).get("wifi_name", "Unknown"),
            "location": agent1.get("input", {}).get("location", "Unknown"),
            "risk_score": agent1.get("risk_score", 0),
            "summary": agent1.get("summary", ""),
            "warning_signs": agent1.get("warning_signs", []),
            "critical_actions": [i["action"] for i in critical_items],
            "high_priority_actions": [i["action"] for i in high_items],
            "banking_recommendation": agent2.get("banking_guidance", {}).get(
                "recommendation", ""
            ),
            "incident_scenario": agent3.get("identified_scenario", "general"),
            "immediate_steps": agent3.get("immediate_steps",
                                           agent3.get("immediate_response_steps", [])),
            "reporting_resources": REPORTING_RESOURCES,
            "agents_participated": [
                agent1.get("agent", "Agent 1"),
                agent2.get("agent", "Agent 2"),
                agent3.get("agent", "Agent 3"),
            ],
            "models_used": list({
                agent1.get("model_used", ""),
                agent2.get("model_used", ""),
                agent3.get("model_used", ""),
            } - {"", None}),
        }
