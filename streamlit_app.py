"""
Wi-Fi Safety Assistant – Streamlit UI
IBM Agentic AI · Bengaluru Commuters

Streamlit Cloud entry point: wraps the existing Flask backend logic directly.
No Flask server needed; backend modules are imported and called in-process.
"""
import sys
import os

# Put backend/ on the path so all backend imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

import streamlit as st

# ── Page config (must be first Streamlit call) ─────────────────────────────
st.set_page_config(
    page_title="Wi-Fi Safety Assistant – IBM AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load secrets from Streamlit Cloud or fall back to .env ─────────────────
def _inject_secrets():
    """Copy Streamlit secrets into os.environ so Config picks them up."""
    try:
        for key, value in st.secrets.items():
            if key not in os.environ:
                os.environ[key] = str(value)
    except Exception:
        pass  # running locally with .env — that's fine

_inject_secrets()

# ── Bootstrap backend singletons (cached so they init once per session) ─────
@st.cache_resource(show_spinner="Initialising AI agents…")
def _bootstrap():
    from config import Config, setup_logging
    from database import get_db
    from services.ai_model_manager import AIModelManager
    from agents.agent1_risk import NetworkRiskAgent
    from agents.agent2_device import DeviceSafetyAgent
    from agents.agent3_incident import IncidentResponseAgent
    from agents.supervisor import SupervisorOrchestrator
    from security.guardrails import Guardrails

    setup_logging()

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
    return ai_manager, db, supervisor


ai_manager, db, supervisor = _bootstrap()

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Global */
[data-testid="stAppViewContainer"] { background: #0f172a; }
[data-testid="stSidebar"] { background: #1e293b; }
h1, h2, h3 { color: #f1f5f9; }
p, li, label, .stMarkdown { color: #cbd5e1; }

/* Risk badge colours */
.badge-LOW    { background:#166534; color:#bbf7d0; padding:4px 12px; border-radius:20px; font-weight:700; font-size:.85rem; }
.badge-MEDIUM { background:#92400e; color:#fde68a; padding:4px 12px; border-radius:20px; font-weight:700; font-size:.85rem; }
.badge-HIGH   { background:#991b1b; color:#fecaca; padding:4px 12px; border-radius:20px; font-weight:700; font-size:.85rem; }
.badge-UNKNOWN{ background:#334155; color:#94a3b8; padding:4px 12px; border-radius:20px; font-weight:700; font-size:.85rem; }

/* Score bar */
.score-bar-wrap { background:#1e293b; border-radius:8px; height:12px; width:100%; margin-top:6px; }
.score-bar-fill { height:12px; border-radius:8px; transition: width .4s ease; }

/* Info card */
.info-card {
  background:#1e293b; border:1px solid #334155;
  border-radius:10px; padding:16px; margin-bottom:12px;
}
.info-card h4 { color:#93c5fd; margin:0 0 8px 0; font-size:.95rem; }
.info-card ul { margin:0; padding-left:18px; }
.info-card li { margin-bottom:4px; }

/* Agent pill */
.agent-pill {
  display:inline-block; background:#1e3a5f; border:1px solid #2563eb;
  border-radius:6px; padding:4px 10px; margin:2px; font-size:.78rem; color:#93c5fd;
}
</style>
""", unsafe_allow_html=True)


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛡️ Wi-Fi Safety Assistant")
    st.markdown("**IBM Agentic AI · Bengaluru Commuters**")
    st.divider()

    # AI model status
    st.markdown("### 🤖 AI Models")
    status = ai_manager.status()

    granite = status["granite"]
    gemini  = status["gemini"]

    g_icon = "🟢" if granite["available"] else "🔴"
    gm_icon = "🟢" if gemini["available"] else "🟡"

    st.markdown(f"{g_icon} **IBM Granite** `{granite['model']}`")
    st.caption("Primary – watsonx.ai")
    st.markdown(f"{gm_icon} **Google Gemini** `{gemini['model']}`")
    st.caption("Secondary / fallback")
    st.divider()

    st.markdown("### 📋 Navigation")
    page = st.radio(
        "Go to",
        ["🏠 Dashboard", "🔍 Risk Assessment", "💬 AI Assistant", "📜 History", "📊 Analytics"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("📞 Cyber Crime Helpline: **1930**")
    st.caption("🔗 [cybercrime.gov.in](https://cybercrime.gov.in/)")
    st.caption("🔗 [CERT-In](https://www.cert-in.org.in/)")


# ── Helpers ────────────────────────────────────────────────────────────────
RISK_COLOURS = {"LOW": "#16a34a", "MEDIUM": "#d97706", "HIGH": "#dc2626", "UNKNOWN": "#64748b"}

def _risk_badge(level: str):
    cls = f"badge-{level}" if level in ("LOW","MEDIUM","HIGH") else "badge-UNKNOWN"
    st.markdown(f'<span class="{cls}">{level}</span>', unsafe_allow_html=True)

def _score_bar(score: int):
    colour = RISK_COLOURS.get("HIGH" if score >= 70 else ("MEDIUM" if score >= 40 else "LOW"), "#16a34a")
    pct = min(max(score, 0), 100)
    st.markdown(
        f'<div class="score-bar-wrap"><div class="score-bar-fill" style="width:{pct}%;background:{colour};"></div></div>',
        unsafe_allow_html=True,
    )

def _info_card(title: str, items):
    if not items:
        return
    if isinstance(items, str):
        items = [items]
    li_html = "".join(f"<li>{i}</li>" for i in items)
    st.markdown(
        f'<div class="info-card"><h4>{title}</h4><ul>{li_html}</ul></div>',
        unsafe_allow_html=True,
    )

def _render_result(result: dict):
    """Render a full supervisor result dict."""
    if not result.get("success"):
        st.error(f"⚠️ {result.get('error') or result.get('reason', 'Unknown error')}")
        return

    risk = result.get("risk_level", "UNKNOWN")
    score = result.get("risk_score", 0)

    # ── Top summary row
    col1, col2, col3 = st.columns([1, 2, 2])
    with col1:
        st.metric("Risk Level", risk)
        _risk_badge(risk)
    with col2:
        st.metric("Risk Score", f"{score}/100")
        _score_bar(score)
    with col3:
        dur = result.get("total_duration_ms", 0)
        st.metric("Analysis Time", f"{dur/1000:.1f}s" if dur else "–")
        task_id = result.get("task_id", "")
        if task_id:
            st.caption(f"Task: `{task_id[:8]}…`")

    st.divider()

    # ── Three-column agent output tabs
    t1, t2, t3 = st.tabs(["🌐 Network Risk (Agent 1)", "🔒 Device Safety (Agent 2)", "🚨 Incident Response (Agent 3)"])

    with t1:
        st.markdown(f"**Summary:** {result.get('risk_summary','')}")
        if result.get("risk_explanation"):
            st.info(result["risk_explanation"])
        _info_card("⚠️ Warning Signs",         result.get("warning_signs", []))
        _info_card("📋 Risk Factors",           result.get("risk_factors", []))
        _info_card("✅ Positive Indicators",    result.get("positive_indicators", []))
        cert = result.get("cert_in_reference","")
        if cert:
            st.caption(f"📌 CERT-In Reference: {cert}")

    with t2:
        if result.get("threat_explanation"):
            st.warning(result["threat_explanation"])
        _info_card("⚡ Immediate Actions",      result.get("immediate_actions", []))
        _info_card("📱 Device Checklist",       result.get("device_checklist", []))
        _info_card("🌐 Safe Browsing Tips",     result.get("browsing_tips", []))
        _info_card("📲 App Security",           result.get("app_security", []))
        banking = result.get("banking_guidance", {})
        if banking:
            if isinstance(banking, dict):
                _info_card("🏦 Banking Guidance", [f"{k}: {v}" for k, v in banking.items()])
            else:
                _info_card("🏦 Banking Guidance", [str(banking)])
        bl = result.get("bengaluru_specific","")
        if bl:
            st.info(f"🚇 Bengaluru Tip: {bl}")
        rn = result.get("recovery_note","")
        if rn:
            st.caption(rn)

    with t3:
        scenario = result.get("incident_scenario","")
        severity = result.get("incident_severity","")
        if scenario:
            st.markdown(f"**Scenario:** `{scenario}`  |  **Severity:** `{severity}`")
        if result.get("situation_summary"):
            st.info(result["situation_summary"])
        _info_card("🚑 Immediate Steps",        result.get("incident_immediate_steps", []))
        if result.get("if_credentials_entered"):
            st.error(f"🔑 If credentials entered: {result['if_credentials_entered']}")
        if result.get("reporting_guidance"):
            st.warning(result["reporting_guidance"])
        _info_card("🛡️ Prevention Summary",    [result.get("prevention_summary","")] if result.get("prevention_summary") else [])
        btt = result.get("bengaluru_transit_tip","")
        if btt:
            st.info(f"🚇 Transit Tip: {btt}")
        resources = result.get("reporting_resources", [])
        if resources:
            st.markdown("**📞 Reporting Resources:**")
            for r in resources:
                if isinstance(r, dict):
                    name = r.get("name","")
                    helpline = r.get("helpline","")
                    url = r.get("url","")
                    st.markdown(f"- **{name}** · `{helpline}` · [{url}]({url})")
                else:
                    st.markdown(f"- {r}")

    # ── Agent statuses
    with st.expander("🔧 Agent Execution Details"):
        statuses = result.get("agent_statuses", {})
        c1, c2, c3 = st.columns(3)
        for col, (key, label) in zip([c1, c2, c3], [
            ("agent1","Agent 1 · Network Risk"),
            ("agent2","Agent 2 · Device Safety"),
            ("agent3","Agent 3 · Incident"),
        ]):
            info = statuses.get(key, {})
            with col:
                st.markdown(f"**{label}**")
                st.caption(f"Model: `{info.get('model','–')}`")
                st.caption(f"Provider: {info.get('provider','–')}")
                dur = info.get("duration_ms", 0)
                st.caption(f"Duration: {dur:.0f} ms")

    # ── Raw execution log
    exec_log = result.get("execution_log", [])
    if exec_log:
        with st.expander("📋 Execution Log"):
            for entry in exec_log:
                icon = "✅" if entry["status"] == "complete" else ("🔴" if entry["status"] == "error" else "⏳")
                st.markdown(f"{icon} **{entry['step']}** – `{entry['status']}` {entry.get('details','')}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Dashboard":
    st.title("🛡️ Public Wi-Fi Safety Dashboard")
    st.markdown("**AI-powered protection for Bengaluru commuters · IBM Granite + Google Gemini**")
    st.divider()

    # Model status cards
    st.subheader("🤖 AI Model Status")
    c1, c2, c3 = st.columns(3)
    for col, (key, label, role, url) in zip([c1, c2, c3], [
        ("granite", "IBM Granite",    "Primary",           "watsonx.ai"),
        ("gemini",  "Google Gemini",  "Secondary/Fallback","aistudio.google.com"),
        ("groq",    "Groq",           "Disabled",          "–"),
    ]):
        with col:
            info = status[key]
            avail = info.get("available", False)
            icon = "🟢" if avail else ("🔴" if key != "groq" else "⚫")
            with st.container(border=True):
                st.markdown(f"### {icon} {label}")
                st.caption(f"**Role:** {role}")
                st.caption(f"**Model:** `{info.get('model','–')}`")
                st.caption(f"**Status:** {'Available ✓' if avail else 'Unavailable ✗'}")

    st.divider()

    # Quick stats from DB
    st.subheader("📊 Quick Stats")
    try:
        analytics = db.get_analytics()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Analyses", analytics.get("total_tasks", 0))
        m2.metric("Completed",      analytics.get("complete", 0))
        m3.metric("Errors",         analytics.get("errors", 0))
        m4.metric("Success Rate",   f"{analytics.get('completion_rate', 0)}%")

        risk_dist = analytics.get("risk_distribution", {})
        if any(risk_dist.values()):
            st.divider()
            st.subheader("📈 Risk Distribution")
            r1, r2, r3 = st.columns(3)
            r1.metric("🟢 LOW",    risk_dist.get("LOW",    0))
            r2.metric("🟡 MEDIUM", risk_dist.get("MEDIUM", 0))
            r3.metric("🔴 HIGH",   risk_dist.get("HIGH",   0))
    except Exception as e:
        st.warning(f"Could not load analytics: {e}")

    st.divider()
    st.subheader("🚀 Quick Start")
    st.info(
        "Use the **Risk Assessment** tab to analyse any public Wi-Fi network. "
        "The **AI Assistant** tab lets you ask cybersecurity questions. "
        "**History** shows recent assessments, and **Analytics** shows detailed stats."
    )
    st.markdown("""
**How it works:**
1. **Agent 1 (Network Risk)** – IBM Granite assesses the network's risk level
2. **Agent 2 (Device Safety)** – IBM Granite gives device-specific protection advice
3. **Agent 3 (Incident Response)** – Gemini provides emergency response steps
4. **Supervisor** – Consolidates all three outputs into one unified report
""")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: RISK ASSESSMENT
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Risk Assessment":
    st.title("🔍 Wi-Fi Risk Assessment")
    st.markdown("Enter details about the public Wi-Fi network you want to assess.")
    st.divider()

    with st.form("assess_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            wifi_name = st.text_input(
                "Wi-Fi Network Name (SSID) *",
                placeholder="e.g. BMTC_Free_WiFi, Namma_Metro_WiFi",
            )
            connection_type = st.selectbox(
                "Connection Type",
                ["wpa2", "wpa3", "captive_portal", "unknown"],
                index=0,
            )
        with col2:
            location = st.text_input(
                "Location",
                placeholder="e.g. Majestic Bus Stand, Bengaluru",
            )
            user_context = st.text_area(
                "Additional Context",
                placeholder="e.g. No login required, very fast speed, many users connected…",
                height=90,
            )

        submitted = st.form_submit_button("🛡️ Analyse Network", type="primary", use_container_width=True)

    if submitted:
        if not wifi_name.strip():
            st.error("Please enter the Wi-Fi network name.")
        else:
            with st.spinner("🤖 Three AI agents are analysing the network…"):
                try:
                    result = supervisor.process_request(
                        wifi_name=wifi_name.strip(),
                        connection_type=connection_type,
                        location=location.strip(),
                        user_context=user_context.strip(),
                        client_ip="streamlit-user",
                    )
                    # Persist last result in session for display after rerun
                    st.session_state["last_result"] = result
                except Exception as e:
                    st.error(f"Analysis failed: {e}")
                    st.session_state.pop("last_result", None)

    # Render last result if present
    if "last_result" in st.session_state:
        st.divider()
        st.subheader("📋 Assessment Results")
        _render_result(st.session_state["last_result"])


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: AI ASSISTANT
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💬 AI Assistant":
    st.title("💬 AI Cybersecurity Assistant")
    st.markdown("Ask anything about Wi-Fi safety, public hotspots, or digital hygiene.")
    st.divider()

    # Init chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Render chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("model"):
                st.caption(f"🤖 {msg['model']} via {msg['provider']}")

    # Chat input
    user_input = st.chat_input("Ask a cybersecurity question…")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                system_ctx = (
                    "You are a friendly cybersecurity expert helping Bengaluru commuters "
                    "stay safe on public Wi-Fi. Answer questions about Wi-Fi safety, "
                    "cybersecurity, and digital hygiene. Keep responses concise and practical. "
                    "Reference CERT-In (cert-in.org.in) and report cyber crimes at "
                    "cybercrime.gov.in or call 1930."
                )
                prompt = f"{system_ctx}\n\nUser question: {user_input}\n\nAnswer:"
                result = ai_manager.generate(
                    prompt=prompt,
                    provider="auto",
                    max_tokens=600,
                    temperature=0.4,
                )
                answer = result.get("text", "Sorry, I couldn't generate a response.")
                model  = result.get("model", "")
                provider = result.get("provider", "")
                st.markdown(answer)
                if model:
                    st.caption(f"🤖 {model} via {provider}")

        st.session_state.chat_history.append({
            "role": "assistant",
            "content": answer,
            "model": model,
            "provider": provider,
        })

    if st.button("🗑️ Clear Chat", use_container_width=False):
        st.session_state.chat_history = []
        st.rerun()

    # Suggested questions
    if not st.session_state.chat_history:
        st.divider()
        st.markdown("**💡 Try asking:**")
        suggestions = [
            "Is Namma Metro Wi-Fi safe to use for browsing?",
            "What is a man-in-the-middle attack on public Wi-Fi?",
            "Should I use a VPN on public Wi-Fi?",
            "What should I do if I think my device is compromised?",
            "How can I check if a Wi-Fi hotspot is legitimate?",
        ]
        for s in suggestions:
            if st.button(s, key=f"sug_{s}"):
                st.session_state.chat_history.append({"role": "user", "content": s})
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: HISTORY
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📜 History":
    st.title("📜 Assessment History")
    st.divider()

    limit = st.slider("Show last N assessments", 5, 100, 20)
    try:
        tasks = db.get_recent_tasks(limit=limit)
        if not tasks:
            st.info("No assessments yet. Run your first analysis in the Risk Assessment tab!")
        else:
            st.markdown(f"**{len(tasks)} assessments found**")

            RISK_EMOJI = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴", "UNKNOWN": "⚪"}
            STATUS_EMOJI = {"complete": "✅", "error": "🔴", "running": "⏳", "pending": "🕐"}

            for task in tasks:
                risk = task.get("risk_level", "UNKNOWN")
                status_val = task.get("status", "")
                wifi = task.get("wifi_name", "–")
                ts = task.get("created_at", "")[:19].replace("T", " ")
                dur = task.get("total_duration_ms")
                dur_str = f"{dur/1000:.1f}s" if dur else "–"

                with st.expander(
                    f"{RISK_EMOJI.get(risk,'⚪')} {wifi} · {risk} · {ts} · {dur_str}",
                    expanded=False,
                ):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Risk", risk)
                    c2.metric("Status", f"{STATUS_EMOJI.get(status_val,'')} {status_val}")
                    c3.metric("Duration", dur_str)
                    st.caption(f"Task ID: `{task.get('id','')}`")

    except Exception as e:
        st.error(f"Could not load history: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 Analytics":
    st.title("📊 Performance Analytics")
    st.divider()

    try:
        analytics = db.get_analytics()

        # Summary metrics
        st.subheader("Overall Stats")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Tasks",   analytics["total_tasks"])
        m2.metric("Completed",     analytics["complete"])
        m3.metric("Errors",        analytics["errors"])
        m4.metric("Success Rate",  f"{analytics['completion_rate']}%")

        st.divider()

        # Risk distribution
        st.subheader("Risk Distribution")
        risk_dist = analytics.get("risk_distribution", {})
        r1, r2, r3 = st.columns(3)
        r1.metric("🟢 LOW",    risk_dist.get("LOW", 0))
        r2.metric("🟡 MEDIUM", risk_dist.get("MEDIUM", 0))
        r3.metric("🔴 HIGH",   risk_dist.get("HIGH", 0))

        st.divider()

        # Provider performance
        st.subheader("AI Provider Performance")
        provider_stats = analytics.get("provider_stats", {})
        if provider_stats:
            for provider_name, stats in provider_stats.items():
                with st.expander(f"🤖 {provider_name.upper()}", expanded=True):
                    p1, p2, p3, p4 = st.columns(4)
                    p1.metric("Total Calls",   stats.get("total", 0))
                    p2.metric("Successful",    stats.get("success", 0))
                    p3.metric("Success Rate",  f"{stats.get('success_rate', 0)}%")
                    p4.metric("Avg Latency",   f"{stats.get('avg_ms', 0):.0f}ms")
        else:
            st.info("No model calls recorded yet.")

        st.divider()
        st.subheader("🤖 Live Model Status")
        for key, info in ai_manager.status().items():
            avail = info.get("available", False)
            icon = "🟢" if avail else "🔴"
            st.markdown(
                f"{icon} **{key.upper()}** – `{info.get('model','–')}` "
                f"({info.get('provider','–')}) – Role: *{info.get('role','–')}*"
            )

    except Exception as e:
        st.error(f"Could not load analytics: {e}")


# ── Footer ─────────────────────────────────────────────────────────────────
st.divider()
st.caption("🛡️ Wi-Fi Safety Assistant · IBM Agentic AI Hackathon · Bengaluru · "
           "Report cyber crimes: **1930** · [cybercrime.gov.in](https://cybercrime.gov.in/)")
