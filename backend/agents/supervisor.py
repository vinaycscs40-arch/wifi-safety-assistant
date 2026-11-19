"""
Central Supervisor Agent / Orchestrator
Coordinates all three specialized agents, transfers information between them,
resolves conflicting recommendations, and returns one unified response.
"""
import time
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SupervisorOrchestrator:
    """
    Central Supervisor – orchestrates the three-agent pipeline.
    
    Workflow:
    1. Validate and understand the user request
    2. Assign task to Agent 1 (Risk Assessment) → IBM Granite
    3. Pass Agent 1 output to Agent 2 (Device Safety) → IBM Granite
    4. Pass Agents 1+2 output to Agent 3 (Incident Response) → Gemini/Granite
    5. Consolidate all outputs into one unified response
    6. Log metrics and persist to database
    """

    def __init__(self, ai_manager, db_manager, guardrails, agents: Dict):
        """
        agents: {
            'agent1': NetworkRiskAgent,
            'agent2': DeviceSafetyAgent,
            'agent3': IncidentResponseAgent,
        }
        """
        self.ai = ai_manager
        self.db = db_manager
        self.guardrails = guardrails
        self.agent1 = agents["agent1"]
        self.agent2 = agents["agent2"]
        self.agent3 = agents["agent3"]
        logger.info("Supervisor/Orchestrator initialized with 3 agents")

    def process_request(
        self,
        wifi_name: str,
        connection_type: str,
        location: str,
        user_context: str,
        client_ip: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Full pipeline execution.
        Returns unified response dict for the frontend.
        """
        t_start = time.time()
        task_id = None
        execution_log = []

        def log_step(step: str, status: str, details: str = ""):
            entry = {
                "step": step,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": details,
            }
            execution_log.append(entry)
            logger.info(f"[Supervisor] {step}: {status} {details}")

        try:
            # ── Step 0: Guardrail checks ──────────────────────────────────
            log_step("Guardrail Check", "running")
            guard_result = self.guardrails.validate_input(
                wifi_name=wifi_name,
                connection_type=connection_type,
                location=location,
                user_context=user_context,
                client_ip=client_ip,
            )
            if not guard_result["allowed"]:
                log_step("Guardrail Check", "blocked", guard_result["reason"])
                return self._blocked_response(guard_result, execution_log)
            log_step("Guardrail Check", "passed",
                     f"flags={guard_result.get('flags', [])}")

            # ── Step 1: Create task record ────────────────────────────────
            log_step("Task Creation", "running")
            task_id = self.db.create_task(
                wifi_name=wifi_name,
                connection_type=connection_type,
                location=location,
                user_context=user_context,
            )
            self.db.update_task(task_id, status="running")
            log_step("Task Creation", "complete", f"task_id={task_id}")

            # ── Step 2: Agent 1 – Network Risk Assessment ─────────────────
            log_step("Agent 1: Network Risk Assessment", "running")
            t1 = time.time()
            agent1_output = self.agent1.assess(
                wifi_name=wifi_name,
                connection_type=connection_type,
                location=location,
                user_context=user_context,
                task_id=task_id,
            )
            agent1_ms = round((time.time() - t1) * 1000, 1)
            self.db.update_task(task_id,
                                agent1_output=agent1_output,
                                risk_level=agent1_output.get("risk_level", "UNKNOWN"),
                                agent1_duration_ms=agent1_ms)
            self._log_model_call(task_id, agent1_output, "Agent 1")
            log_step("Agent 1: Network Risk Assessment", "complete",
                     f"risk={agent1_output.get('risk_level')} in {agent1_ms}ms")

            # ── Step 3: Agent 2 – Device Safety ───────────────────────────
            log_step("Agent 2: Device Safety & Prevention", "running")
            t2 = time.time()
            agent2_output = self.agent2.analyze(
                agent1_output=agent1_output,
                task_id=task_id,
            )
            agent2_ms = round((time.time() - t2) * 1000, 1)
            self.db.update_task(task_id,
                                agent2_output=agent2_output,
                                agent2_duration_ms=agent2_ms)
            self._log_model_call(task_id, agent2_output, "Agent 2")
            log_step("Agent 2: Device Safety & Prevention", "complete",
                     f"checklist_items={len(agent2_output.get('device_checklist',[]))} "
                     f"in {agent2_ms}ms")

            # ── Step 4: Agent 3 – Incident Response ───────────────────────
            log_step("Agent 3: Incident Response & Safety Guidance", "running")
            t3 = time.time()
            agent3_output = self.agent3.respond(
                agent1_output=agent1_output,
                agent2_output=agent2_output,
                task_id=task_id,
            )
            agent3_ms = round((time.time() - t3) * 1000, 1)
            self.db.update_task(task_id,
                                agent3_output=agent3_output,
                                agent3_duration_ms=agent3_ms)
            self._log_model_call(task_id, agent3_output, "Agent 3")
            log_step("Agent 3: Incident Response & Safety Guidance", "complete",
                     f"scenario={agent3_output.get('identified_scenario')} "
                     f"in {agent3_ms}ms")

            # ── Step 5: Consolidate ────────────────────────────────────────
            log_step("Supervisor Consolidation", "running")
            unified = self._consolidate(
                agent1_output, agent2_output, agent3_output,
                task_id, execution_log, t_start
            )
            total_ms = round((time.time() - t_start) * 1000, 1)

            models_used = list({
                agent1_output.get("model_used"),
                agent2_output.get("model_used"),
                agent3_output.get("model_used"),
            } - {None, ""})

            self.db.update_task(
                task_id,
                status="complete",
                supervisor_output=unified,
                total_duration_ms=total_ms,
                models_used=models_used,
                guardrail_flags=guard_result.get("flags", []),
            )
            log_step("Supervisor Consolidation", "complete", f"total={total_ms}ms")

            unified["execution_log"] = execution_log
            unified["total_duration_ms"] = total_ms
            return unified

        except Exception as e:
            logger.exception(f"[Supervisor] Pipeline error: {e}")
            if task_id:
                self.db.update_task(task_id, status="error",
                                    error_message=str(e))
            log_step("Pipeline", "error", str(e))
            return self._error_response(str(e), task_id, execution_log)

    # ── Private helpers ────────────────────────────────────────────────────

    def _consolidate(
        self,
        a1: Dict, a2: Dict, a3: Dict,
        task_id: str, execution_log: list, t_start: float
    ) -> Dict[str, Any]:
        """Merge outputs from all three agents into one clean response."""
        risk = a1.get("risk_level", "UNKNOWN")
        checklist = a2.get("device_checklist", [])
        final_report = a3.get("final_report", {})

        # ── B4: Active conflict resolution ───────────────────────────────────
        # Agent 3 may escalate severity based on detected incident scenario.
        # Supervisor picks the highest risk level across all agents.
        severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
        agent3_severity = a3.get("severity", risk)
        final_risk = risk
        if severity_rank.get(agent3_severity, 0) > severity_rank.get(risk, 0):
            final_risk = agent3_severity
            logger.info(
                f"[Supervisor] Conflict resolution: escalated risk "
                f"{risk} → {final_risk} (Agent 3 severity)"
            )

        # ── B8: Validate & sanitize final situation summary ───────────────────
        summary_text = a3.get("situation_summary", a1.get("summary", ""))
        if summary_text:
            validated = self.guardrails.validate_output(summary_text, final_risk)
            if not validated["valid"]:
                logger.warning(
                    f"[Supervisor] Output validation issues: {validated['issues']}"
                )
            summary_text = validated.get("sanitized_text", summary_text)

        return {
            "success": True,
            "task_id": task_id,
            "risk_level": final_risk,
            "risk_score": a1.get("risk_score", 0),
            "risk_summary": a1.get("summary", ""),
            "risk_explanation": a1.get("explanation", ""),
            "warning_signs": a1.get("warning_signs", []),
            "risk_factors": a1.get("risk_factors", []),
            "positive_indicators": a1.get("positive_indicators", []),
            "cert_in_reference": a1.get("cert_in_reference", ""),

            "device_checklist": checklist,
            "banking_guidance": a2.get("banking_guidance", {}),
            "threat_explanation": a2.get("threat_explanation", ""),
            "immediate_actions": a2.get("immediate_actions", []),
            "browsing_tips": a2.get("browsing_tips", []),
            "app_security": a2.get("app_security", []),
            "bengaluru_specific": a2.get("bengaluru_specific", ""),
            "recovery_note": a2.get("recovery_note", ""),

            "incident_scenario": a3.get("incident_scenario",
                                        a3.get("identified_scenario", "general")),
            "incident_severity": a3.get("severity", risk),
            "situation_summary": summary_text,
            "incident_immediate_steps": a3.get("immediate_steps",
                                               a3.get("immediate_response_steps", [])),
            "if_credentials_entered": a3.get("if_credentials_entered", ""),
            "reporting_guidance": a3.get("reporting_guidance", ""),
            "prevention_summary": a3.get("prevention_summary", ""),
            "bengaluru_transit_tip": a3.get("bengaluru_transit_tip", ""),
            "reporting_resources": a3.get("reporting_resources", []),

            "final_report": final_report,

            "agent_statuses": {
                "agent1": {
                    "name": a1.get("agent", "Agent 1"),
                    "status": a1.get("status", "complete"),
                    "model": a1.get("model_used", ""),
                    "provider": a1.get("provider", ""),
                    "duration_ms": a1.get("duration_ms", 0),
                },
                "agent2": {
                    "name": a2.get("agent", "Agent 2"),
                    "status": a2.get("status", "complete"),
                    "model": a2.get("model_used", ""),
                    "provider": a2.get("provider", ""),
                    "duration_ms": a2.get("duration_ms", 0),
                },
                "agent3": {
                    "name": a3.get("agent", "Agent 3"),
                    "status": a3.get("status", "complete"),
                    "model": a3.get("model_used", ""),
                    "provider": a3.get("provider", ""),
                    "duration_ms": a3.get("duration_ms", 0),
                },
            },
        }

    def _log_model_call(self, task_id: str, agent_output: Dict, agent_name: str):
        """Log AI model call metrics to database."""
        provider = agent_output.get("provider", "unknown")
        # Skip logging placeholder/none entries – they pollute analytics
        if not provider or provider in ("none", "unknown"):
            return
        try:
            self.db.log_model_call(
                task_id=task_id,
                provider=provider,
                model_id=agent_output.get("model_used", "unknown"),
                agent_name=agent_name,
                duration_ms=agent_output.get("duration_ms", 0),
                success=agent_output.get("status") not in ("error",),
                error=agent_output.get("error"),
            )
        except Exception as e:
            logger.warning(f"Failed to log model call: {e}")

    def _blocked_response(self, guard_result: Dict,
                          execution_log: list) -> Dict[str, Any]:
        return {
            "success": False,
            "blocked": True,
            "reason": guard_result.get("reason", "Request blocked by guardrails"),
            "risk_level": "UNKNOWN",
            "execution_log": execution_log,
        }

    def _error_response(self, error: str, task_id: Optional[str],
                        execution_log: list) -> Dict[str, Any]:
        return {
            "success": False,
            "error": error,
            "task_id": task_id,
            "risk_level": "UNKNOWN",
            "execution_log": execution_log,
            "reporting_resources": [
                {
                    "name": "Cyber Crime Helpline",
                    "helpline": "1930",
                    "url": "https://cybercrime.gov.in/",
                }
            ],
        }
