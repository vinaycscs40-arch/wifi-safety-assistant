"""
Flask Application Entry Point
AI-Powered Public Wi-Fi Safety Assistant
IBM Inter-Institute Hackathon
"""
import sys
import os
import logging

# Ensure backend/ is on the Python path
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from config import Config, setup_logging
from database import get_db
from services.ai_model_manager import AIModelManager
from agents.agent1_risk import NetworkRiskAgent
from agents.agent2_device import DeviceSafetyAgent
from agents.agent3_incident import IncidentResponseAgent
from agents.supervisor import SupervisorOrchestrator
from security.guardrails import Guardrails

# ── Bootstrap ─────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "..", "frontend", "static"),
    template_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
)
app.config["SECRET_KEY"] = Config.SECRET_KEY
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ── Initialize singletons ──────────────────────────────────────────────────
db = get_db()
ai_manager = AIModelManager(Config)
guardrails = Guardrails(
    max_requests_per_minute=Config.RATE_LIMIT_PER_MINUTE,
    enable=Config.ENABLE_GUARDRAILS,
)

agent1 = NetworkRiskAgent(ai_manager)
agent2 = DeviceSafetyAgent(ai_manager)
agent3 = IncidentResponseAgent(ai_manager)

supervisor = SupervisorOrchestrator(
    ai_manager=ai_manager,
    db_manager=db,
    guardrails=guardrails,
    agents={"agent1": agent1, "agent2": agent2, "agent3": agent3},
)

logger.info("Application initialized successfully")


# ── Frontend serving ───────────────────────────────────────────────────────

@app.route("/")
def index():
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
    return send_from_directory(frontend_path, "index.html")


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)


# ── Core API ───────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    model_status = ai_manager.status()
    return jsonify({
        "status": "healthy",
        "service": "Wi-Fi Safety Assistant",
        "version": "1.0.0",
        "models": model_status,
        "database": "connected",
        "agents": {
            "agent1": "NetworkRiskAgent",
            "agent2": "DeviceSafetyAgent",
            "agent3": "IncidentResponseAgent",
            "supervisor": "SupervisorOrchestrator",
        },
    })


@app.route("/api/assess", methods=["POST"])
def assess():
    """
    Main endpoint: run full three-agent pipeline.
    
    Body (JSON):
    {
        "wifi_name": "CafeWifi_Free",
        "connection_type": "open",
        "location": "Namma Metro, Bengaluru",
        "user_context": "No login required, speed is good"
    }
    """
    data = request.get_json(silent=True) or {}
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    wifi_name = str(data.get("wifi_name", "")).strip()
    connection_type = str(data.get("connection_type", "unknown")).strip()
    location = str(data.get("location", "")).strip()
    user_context = str(data.get("user_context", "")).strip()

    if not wifi_name:
        return jsonify({"success": False, "error": "wifi_name is required"}), 400

    try:
        result = supervisor.process_request(
            wifi_name=wifi_name,
            connection_type=connection_type,
            location=location,
            user_context=user_context,
            client_ip=client_ip,
        )
        status_code = 200 if result.get("success") else (
            429 if result.get("reason", "").startswith("Rate") else 400
        )
        return jsonify(result), status_code
    except Exception as e:
        logger.exception(f"Assess endpoint error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/models/status", methods=["GET"])
def model_status():
    """Return status of all three AI model providers."""
    return jsonify({
        "success": True,
        "providers": ai_manager.status(),
        "primary": "IBM Granite (watsonx.ai)",
        "secondary": ["Google Gemini"],
        "disabled": ["Groq"],
    })


@app.route("/api/models/test", methods=["POST"])
def test_models():
    """
    Test all three AI providers independently.
    POST body: {} or {"provider": "granite"|"gemini"|"groq"|"all"}
    """
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "all")

    if provider == "all":
        results = ai_manager.test_all()
    elif provider == "granite":
        results = {"granite": ai_manager.granite.test_connection()}
    elif provider == "gemini":
        results = {"gemini": ai_manager.gemini.test_connection()}
    elif provider == "groq":
        results = {"groq": ai_manager.groq.test_connection()}
    else:
        return jsonify({"success": False, "error": "Unknown provider"}), 400

    any_success = any(r.get("success") for r in results.values())
    return jsonify({
        "success": any_success,
        "results": results,
    })


@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    """Return recent task history."""
    limit = min(int(request.args.get("limit", 20)), 100)
    tasks = db.get_recent_tasks(limit=limit)
    return jsonify({"success": True, "tasks": tasks, "count": len(tasks)})


@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id: str):
    """Return full details of a specific task."""
    task = db.get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": "Task not found"}), 404
    return jsonify({"success": True, "task": task})


@app.route("/api/analytics", methods=["GET"])
def analytics():
    """Return performance analytics."""
    data = db.get_analytics()
    model_status_data = ai_manager.status()
    return jsonify({
        "success": True,
        "analytics": data,
        "model_status": model_status_data,
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Conversational AI endpoint for the assistant interface.
    Uses IBM Granite for general cybersecurity Q&A.
    """
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    if not message:
        return jsonify({"success": False, "error": "message is required"}), 400

    # Guardrail check
    guard = guardrails.validate_input(
        wifi_name=message[:100],
        connection_type="",
        location="",
        user_context="",
        client_ip=client_ip,
    )
    if not guard["allowed"]:
        return jsonify({"success": False, "error": guard["reason"]}), 400

    system_ctx = """You are a friendly cybersecurity expert helping Bengaluru commuters 
stay safe on public Wi-Fi. Answer questions about Wi-Fi safety, cybersecurity, 
and digital hygiene. Keep responses concise and practical.
Reference CERT-In (cert-in.org.in) and report cyber crimes at cybercrime.gov.in or call 1930."""

    prompt = f"{system_ctx}\n\nUser question: {message}\n\nAnswer:"

    result = ai_manager.generate(
        prompt=prompt,
        provider="auto",
        max_tokens=600,
        temperature=0.4,
    )

    return jsonify({
        "success": result["success"],
        "response": result["text"],
        "model": result.get("model", ""),
        "provider": result.get("provider", ""),
        "error": result.get("error"),
    })


# ── Error handlers ─────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"success": False, "error": "Method not allowed"}), 405


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({"success": False, "error": "Internal server error"}), 500


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(
        f"Starting Wi-Fi Safety Assistant on {Config.HOST}:{Config.PORT}"
    )
    logger.info(
        f"AI Providers – Granite: {Config.has_granite()}, "
        f"Gemini: {Config.has_gemini()}, Groq: {Config.has_groq()}"
    )
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
    )
