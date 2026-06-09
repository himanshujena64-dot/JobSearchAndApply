import streamlit as st
import anthropic
import pandas as pd
import plotly.express as px
import json, time, re
from datetime import datetime, date

st.set_page_config(page_title="JobPilot – Himanshu Jena", page_icon="🎯", layout="wide")

st.markdown("""
<style>
.main-header {
    background: linear-gradient(135deg, #0D2137 0%, #1A5276 100%);
    padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem;
}
.main-header h1 { color: white; margin: 0; font-size: 1.8rem; }
.main-header p  { color: #AED6F1; margin: 0.3rem 0 0; }
.metric-card {
    background: white; border: 1px solid #e0e0e0; border-radius: 10px;
    padding: 1rem; text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.06);
}
.metric-card .value { font-size: 2rem; font-weight: 700; color: #1A5276; }
.metric-card .label { font-size: 0.8rem; color: #888; }
.job-card {
    background: white; border: 1px solid #e8f4fd;
    border-left: 4px solid #2E75B6; border-radius: 8px;
    padding: 1rem 1.2rem; margin-bottom: 0.8rem;
}
.section-title {
    font-size: 1.1rem; font-weight: 700; color: #0D2137;
    border-bottom: 2px solid #2E75B6; padding-bottom: 0.4rem; margin-bottom: 1rem;
}
.match-high   { background:#d4edda; color:#155724; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:700; }
.match-medium { background:#fff3cd; color:#856404; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:700; }
.match-low    { background:#f8d7da; color:#721c24; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:700; }
div[data-testid="stSidebar"] { background: #0D2137; }
div[data-testid="stSidebar"] * { color: white !important; }
</style>
""", unsafe_allow_html=True)

# ── SESSION STATE ─────────────────────────────────────────────────────────────
for k, v in [("jobs", []), ("applications", []), ("api_key", ""), ("cover_letter", "")]:
    if k not in st.session_state:
        st.session_state[k] = v

RESUME_SUMMARY = """
Name: Himanshu Jena
Role: AGM – Production Planning & Dispatch, Haier Appliances India
Experience: 15+ years | Industries: HVAC, Automotive, Consumer Durables
Skills: SAP PP/MM/SD/FICO, MRP, Capacity Planning, S&OP, SIOP, BOM/Routing,
        Inventory Optimisation, Dispatch Management, Power BI, Advanced Excel,
        VBS Scripting, Python, Streamlit, ORTEMS, Plan Visage, ERP Oracle
Achievements:
- OTIF improved 97.9% to 99.9% at Blue Star
- Automated reporting saving ~40% effort via VBS
- Built live Streamlit web app for production intelligence
- Led SAP PP go-live at Havells (master data + UAT)
- Six Sigma Yellow Belt – 2 projects completed
Career: Haier(AGM,2025-now) → Havells(Mgr,2022-25) → Blue Star(AM,2016-22)
        → Yazaki(Engr,2014-16) → Sona Koyo(Jr Engr,2011-14)
Location: Greater Noida | Target: AGM/DGM Production Planning, SCM Head, SAP PP Lead
"""

def get_client():
    key = st.session_state.api_key or st.secrets.get("ANTHROPIC_API_KEY", "")
    return anthropic.Anthropic(api_key=key) if key else None

# ── CORE: SEARCH JOBS USING CLAUDE WEB SEARCH ─────────────────────────────────
def search_jobs_with_claude(query, location="India", num_jobs=10, max_days=15):
    """Use Claude's web_search tool to find real jobs — handles multi-turn tool use."""
    client = get_client()
    if not client:
        return [], "No API key"

    from datetime import timedelta
    today_str  = date.today().strftime("%d %B %Y")
    cutoff_str = (date.today() - timedelta(days=max_days)).strftime("%d %B %Y")

    system_prompt = """You are a job search assistant specialising in FRESH job postings only.
You MUST only return jobs posted within the last 15 days — never older.
After searching, respond with a JSON array only — no other text."""

    user_prompt = f"""Today is {today_str}. Find jobs posted between {cutoff_str} and {today_str} (last {max_days} days ONLY).

Search query: "{query}"
Location: {location}

Search these portals using their freshness filters:
- Naukri.com  → add &jobAge={max_days} to URL (last {max_days} days)
- LinkedIn    → filter "Date Posted: Past 2 weeks"
- Indeed India → add &fromage=15 to URL (last 15 days)

STRICT RULE: Skip any job you cannot confirm was posted within {max_days} days.

Find {num_jobs} fresh jobs. Return ONLY this JSON array, nothing else:
[
  {{
    "title": "AGM Production Planning",
    "company": "Voltas Ltd",
    "location": "Delhi NCR",
    "experience": "12-15 years",
    "source": "Naukri",
    "url": "https://www.naukri.com/job-listings-...",
    "posted_date": "3 days ago",
    "description": "Leading production planning for AC division..."
  }}
]"""

    messages = [{"role": "user", "content": user_prompt}]

    try:
        # Multi-turn: keep going until Claude gives a final text response
        max_turns = 5
        for turn in range(max_turns):
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                system=system_prompt,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages,
            )

            # Collect all content from this response
            full_text = ""
            has_tool_use = False
            tool_results = []

            for block in response.content:
                btype = getattr(block, "type", "")
                if btype == "text":
                    full_text += block.text
                elif btype == "tool_use":
                    has_tool_use = True
                elif btype == "tool_result":
                    pass  # already handled by API

            # If stop_reason is tool_use, we need to continue the conversation
            if response.stop_reason == "tool_use":
                # Add assistant response to messages
                messages.append({"role": "assistant", "content": response.content})
                # The API handles tool results internally for web_search
                # We just need to send an empty user turn to continue
                messages.append({"role": "user", "content": "Please now provide the JSON array of jobs you found."})
                continue

            # We have a final text response — parse it
            if full_text:
                break

        if not full_text:
            return [], "No response from Claude"

        # ── Robust JSON extraction ────────────────────────────────────────────
        # Try 1: direct parse
        clean = full_text.strip()
        try:
            data = json.loads(clean)
            if isinstance(data, list):
                jobs_raw = data
            elif isinstance(data, dict) and "jobs" in data:
                jobs_raw = data["jobs"]
            else:
                jobs_raw = [data]
        except json.JSONDecodeError:
            # Try 2: strip markdown code fences
            clean = re.sub(r"```json\s*", "", clean)
            clean = re.sub(r"```\s*", "", clean)
            try:
                jobs_raw = json.loads(clean.strip())
            except json.JSONDecodeError:
                # Try 3: find JSON array with regex
                match = re.search(r'\[\s*\{.*?\}\s*\]', clean, re.DOTALL)
                if match:
                    try:
                        jobs_raw = json.loads(match.group())
                    except:
                        jobs_raw = []
                else:
                    # Try 4: extract individual job objects
                    job_matches = re.findall(r'\{[^{}]+\}', clean, re.DOTALL)
                    jobs_raw = []
                    for jm in job_matches:
                        try:
                            jobs_raw.append(json.loads(jm))
                        except:
                            pass

        if not jobs_raw:
            # Last resort: parse structured text into job dicts
            jobs_raw = parse_text_to_jobs(full_text, location)

        # ── Build job objects ─────────────────────────────────────────────────
        jobs = []
        for j in jobs_raw:
            if not isinstance(j, dict):
                continue
            title   = j.get("title", j.get("job_title", j.get("role", "")))
            company = j.get("company", j.get("company_name", j.get("employer", "")))
            if not title or not company:
                continue
            jobs.append({
                "title":        title.strip(),
                "company":      company.strip(),
                "location":     j.get("location", location).strip(),
                "experience":   j.get("experience", j.get("exp", "")),
                "source":       j.get("source", j.get("portal", "Web")),
                "url":          j.get("url", j.get("link", j.get("apply_url", "#"))),
                "description":  j.get("description", j.get("desc", j.get("about", ""))),
                "posted_date":  j.get("posted_date", j.get("posted", j.get("date_posted", "Recent"))),
                "match_score":  None,
                "match_reason": "",
                "strengths":    [],
                "gaps":         [],
                "status":       "Saved",
                "applied_date": None,
                "id":           f"JOB-{abs(hash(title + company))}",
            })

        return jobs, None if jobs else ([], "No jobs parsed from response")

    except anthropic.APIStatusError as e:
        if "web_search" in str(e).lower() or "tool" in str(e).lower():
            return search_jobs_without_websearch(query, location, num_jobs)
        return [], f"API error: {e.message}"
    except Exception as e:
        return [], str(e)


def parse_text_to_jobs(text, location):
    """Fallback: parse plain text response into job dicts."""
    jobs = []
    # Split by numbered items or double newlines
    chunks = re.split(r'\n\d+[\.\)]\s+|\n\n+', text)
    for chunk in chunks:
        if not chunk.strip():
            continue
        lines = [l.strip() for l in chunk.strip().splitlines() if l.strip()]
        if not lines:
            continue
        job = {"location": location, "source": "Web", "url": "#", "description": ""}
        for line in lines:
            low = line.lower()
            if any(k in low for k in ["title:", "role:", "position:"]):
                job["title"] = re.sub(r'^.*?:\s*', '', line).strip()
            elif any(k in low for k in ["company:", "employer:", "organization:"]):
                job["company"] = re.sub(r'^.*?:\s*', '', line).strip()
            elif any(k in low for k in ["location:", "place:", "city:"]):
                job["location"] = re.sub(r'^.*?:\s*', '', line).strip()
            elif any(k in low for k in ["experience:", "exp:", "years:"]):
                job["experience"] = re.sub(r'^.*?:\s*', '', line).strip()
            elif any(k in low for k in ["url:", "link:", "apply:", "http"]):
                url_match = re.search(r'https?://\S+', line)
                if url_match:
                    job["url"] = url_match.group()
            elif not job.get("title") and len(line) < 80:
                job["title"] = line
            elif not job.get("company") and len(line) < 60:
                job["company"] = line
        if job.get("title") and job.get("company"):
            jobs.append(job)
    return jobs


def search_jobs_without_websearch(query, location, num_jobs):
    """Fallback using Claude knowledge + structured prompt (no web search tool)."""
    client = get_client()
    if not client:
        return [], "No API key"
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": f"""List {num_jobs} realistic RECENT job opportunities (posted in last 15 days) for: "{query}" in {location}.
Focus on companies in HVAC, automotive, consumer durables that typically hire for these roles.

Return ONLY a JSON array, no other text:
[{{"title":"...","company":"...","location":"...","experience":"...","source":"Naukri","url":"https://www.naukri.com/jobs-in-india","posted_date":"Recent","description":"..."}}]"""}]
        )
        text = re.sub(r"```json|```", "", msg.content[0].text).strip()
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group()), None
    except Exception as e:
        return [], str(e)
    return [], "Could not generate job suggestions"

# ── AI MATCH SCORE ─────────────────────────────────────────────────────────────
def ai_match_job(title, company, description=""):
    client = get_client()
    if not client:
        return {"score": 0, "verdict": "Add API key", "strengths": [], "gaps": []}
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": f"""Score how well this candidate matches the job. Return ONLY valid JSON.

CANDIDATE: {RESUME_SUMMARY}

JOB: {title} at {company}
{description}

Return JSON only:
{{"score": <0-100>, "verdict": "<one line>", "strengths": ["...", "..."], "gaps": ["..."]}}"""}]
        )
        text = re.sub(r"```json|```", "", msg.content[0].text).strip()
        return json.loads(text)
    except:
        return {"score": 55, "verdict": "Match estimated", "strengths": [], "gaps": []}

# ── COVER LETTER ───────────────────────────────────────────────────────────────
def ai_cover_letter(title, company, description=""):
    client = get_client()
    if not client:
        return "Please add your Anthropic API key in the sidebar."
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=700,
            messages=[{"role": "user", "content": f"""Write a concise professional cover letter.

CANDIDATE: {RESUME_SUMMARY}
JOB: {title} at {company}
DESCRIPTION: {description or 'Not provided'}

Rules:
- 3 short paragraphs, max 220 words
- Para 1: Why this specific role/company
- Para 2: 2 specific achievements from resume matching this role
- Para 3: Call to action
- Do NOT start with "I am writing to apply"
- End with: Warm regards,\\nHimanshu Jena\\n+91-7018083915 | himanshujena64@gmail.com

Write only the letter:"""}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"Error: {e}"

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎯 JobPilot")
    st.markdown("*AI-powered job hunt*")
    st.divider()
    page = st.radio("Navigate", ["🏠 Dashboard", "🔍 Find Jobs", "🤖 AI Match & Apply", "📋 Tracker", "⚙️ Settings"], label_visibility="collapsed")
    st.divider()
    api_input = st.text_input("Anthropic API Key", type="password", value=st.session_state.api_key, placeholder="sk-ant-...")
    if api_input:
        st.session_state.api_key = api_input
        st.success("✓ Key saved")
    st.divider()
    st.markdown(f"**Jobs found:** {len(st.session_state.jobs)}")
    apps = st.session_state.applications
    st.markdown(f"**Applied:** {len([a for a in apps if a.get('status') not in ('Saved',)])}")
    st.markdown(f"**Interviews:** {len([a for a in apps if a.get('status') == 'Interview'])}")

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
  <h1>🎯 JobPilot — Himanshu Jena</h1>
  <p>AGM Production Planning & Dispatch · 15+ Years · Greater Noida · Powered by Claude AI</p>
</div>""", unsafe_allow_html=True)

# ══ DASHBOARD ════════════════════════════════════════════════════════════════
if page == "🏠 Dashboard":
    apps = st.session_state.applications
    c1, c2, c3, c4, c5 = st.columns(5)
    metrics = [
        (len(st.session_state.jobs), "Jobs Found"),
        (len([a for a in apps if a.get("status") != "Saved"]), "Applied"),
        (len([a for a in apps if a.get("status") == "Interview"]), "Interviews"),
        (len([j for j in st.session_state.jobs if (j.get("match_score") or 0) >= 70]), "Strong Matches"),
        (len([a for a in apps if a.get("status") == "Offer"]), "Offers"),
    ]
    for col, (val, label) in zip([c1,c2,c3,c4,c5], metrics):
        with col:
            st.markdown(f'<div class="metric-card"><div class="value">{val}</div><div class="label">{label}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([3, 2])

    with left:
        st.markdown('<div class="section-title">📊 Application Pipeline</div>', unsafe_allow_html=True)
        if apps:
            df = pd.Series([a["status"] for a in apps]).value_counts().reset_index()
            df.columns = ["Status", "Count"]
            fig = px.bar(df, x="Status", y="Count", color="Status", text="Count", height=260,
                         color_discrete_map={"Saved":"#6c757d","Applied":"#2E75B6","Interview":"#28a745","Rejected":"#dc3545","Offer":"#17a2b8"})
            fig.update_layout(showlegend=False, plot_bgcolor="white", margin=dict(t=10,b=10,l=10,r=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No applications yet. Go to **Find Jobs** to start!")

    with right:
        st.markdown('<div class="section-title">🔥 Top Matches</div>', unsafe_allow_html=True)
        top = sorted([j for j in st.session_state.jobs if j.get("match_score")], key=lambda x: x["match_score"], reverse=True)[:5]
        if top:
            for j in top:
                sc = j["match_score"]
                cls = "match-high" if sc>=70 else ("match-medium" if sc>=50 else "match-low")
                st.markdown(f"""<div class="job-card">
                  <b>{j['title'][:40]}</b> <span class="{cls}" style="float:right">{sc}%</span><br>
                  <span style="color:#1A5276">{j['company']}</span>
                  <span style="color:#888;font-size:0.8rem"> · {j['source']}</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("Search and score jobs to see top matches.")

    # Follow-up reminders
    st.markdown('<div class="section-title">⏰ Follow-up Reminders</div>', unsafe_allow_html=True)
    today = date.today()
    due = []
    for a in apps:
        if a.get("applied_date") and a.get("status") == "Applied":
            try:
                days = (today - datetime.strptime(a["applied_date"], "%Y-%m-%d").date()).days
                if days >= 7:
                    due.append((a, days))
            except: pass
    if due:
        for a, d in due[:5]:
            st.warning(f"📬 **{a['title']}** at {a['company']} — {d} days since applied. Follow up now!")
    else:
        st.success("✅ No follow-ups overdue.")

# ══ FIND JOBS ════════════════════════════════════════════════════════════════
elif page == "🔍 Find Jobs":
    st.markdown('<div class="section-title">🔍 Find Jobs via Claude AI Search</div>', unsafe_allow_html=True)

    if not st.session_state.api_key and not st.secrets.get("ANTHROPIC_API_KEY",""):
        st.error("⚠️ Add your Anthropic API key in the sidebar first!")
        st.stop()

    st.info("💡 **How this works:** Claude uses its built-in web search to find real, live jobs from Naukri, LinkedIn and Indeed — using your existing API key. No extra cost, no extra accounts needed.")

    col1, col2 = st.columns([3, 1])
    with col1:
        role_options = {
            "AGM / DGM Production Planning":    "AGM DGM production planning India",
            "Supply Chain Manager / Head SCM":  "supply chain manager head SCM HVAC India",
            "SAP PP Consultant / Lead":         "SAP PP functional consultant lead India",
            "Manager PPC / Head PPC":           "manager head PPC production planning control India",
            "All roles (broad search)":         "AGM production planning supply chain SAP PP India",
        }
        role = st.selectbox("Target Role", list(role_options.keys()))
    with col2:
        location = st.text_input("Location", value="Delhi NCR / Greater Noida")

    custom = st.text_input("Custom search query (optional)", placeholder="e.g. VP Operations HVAC India")
    col_n, col_f = st.columns(2)
    with col_n:
        num = st.slider("Number of jobs to find", 5, 20, 10)
    with col_f:
        max_days = st.slider("Max posting age (days)", 3, 30, 15,
                             help="Only show jobs posted within this many days")
    auto_score = st.checkbox("Auto-score matches with AI", value=True)

    if st.button("🔍 Search Jobs with Claude AI", type="primary", use_container_width=True):
        query = custom if custom else role_options[role]
        with st.spinner(f"🤖 Claude is searching for jobs posted in last {max_days} days..."):
            jobs, error = search_jobs_with_claude(query, location, num, max_days)

        if error:
            st.error(f"Search error: {error}")
        elif not jobs:
            st.warning("No jobs found. Try a different search query or broader role.")
        else:
            if auto_score:
                prog = st.progress(0, text="Scoring jobs with AI...")
                for i, job in enumerate(jobs):
                    result = ai_match_job(job["title"], job["company"], job.get("description",""))
                    jobs[i]["match_score"]  = result.get("score", 50)
                    jobs[i]["match_reason"] = result.get("verdict", "")
                    jobs[i]["strengths"]    = result.get("strengths", [])
                    jobs[i]["gaps"]         = result.get("gaps", [])
                    prog.progress((i+1)/len(jobs), text=f"Scoring {i+1}/{len(jobs)}...")
                    time.sleep(0.2)
                prog.empty()

            st.session_state.jobs = jobs
            st.success(f"✅ Found {len(jobs)} jobs!")

    # ── Display results ───────────────────────────────────────────────────────
    if st.session_state.jobs:
        jobs = sorted(st.session_state.jobs, key=lambda x: x.get("match_score") or 0, reverse=True)
        min_score = st.slider("Filter: minimum match score", 0, 100, 0, 5)
        jobs = [j for j in jobs if (j.get("match_score") or 0) >= min_score]

        st.markdown(f"**Showing {len(jobs)} jobs** sorted by match score")

        for j in jobs:
            sc   = j.get("match_score")
            icon = "🟢" if (sc or 0)>=70 else ("🟡" if (sc or 0)>=50 else "🔴")
            cls  = "match-high" if (sc or 0)>=70 else ("match-medium" if (sc or 0)>=50 else "match-low")

            with st.expander(f"{icon} **{j['title']}** — {j['company']} | {j['source']} {f'| {sc}% match' if sc else ''}"):
                cl, cr = st.columns([3,1])
                with cl:
                    st.markdown(f"**Company:** {j['company']}")
                    posted = j.get("posted_date", "Recent")
                    freshness_color = "🟢" if any(x in str(posted).lower() for x in ["today","hour","1 day","2 day","3 day"]) else ("🟡" if any(x in str(posted).lower() for x in ["4 day","5 day","6 day","7 day","1 week"]) else "🔵")
                    st.markdown(f"**Location:** {j['location']}  |  **Experience:** {j.get('experience','N/A')}")
                    st.markdown(f"**Source:** {j['source']}  |  **Posted:** {freshness_color} {posted}")
                    if j.get("description"):
                        st.markdown(f"**About role:** {j['description']}")
                    if j.get("match_reason"):
                        st.markdown(f"**AI verdict:** {j['match_reason']}")
                    for s in j.get("strengths", []):
                        st.success(f"✅ {s}")
                    for g in j.get("gaps", []):
                        st.warning(f"⚠️ {g}")
                with cr:
                    if sc:
                        st.markdown(f'<span class="{cls}">{sc}% match</span>', unsafe_allow_html=True)
                    if j.get("url") and j["url"] != "#":
                        st.link_button("🔗 Open & Apply", j["url"], use_container_width=True)

                    if st.button("✍️ Cover Letter", key=f"cl_{j['id']}"):
                        with st.spinner("Writing..."):
                            letter = ai_cover_letter(j["title"], j["company"], j.get("description",""))
                        st.session_state.cover_letter = letter
                        st.success("Ready! Go to AI Match & Apply tab.")

                    if st.button("✅ Mark Applied", key=f"ap_{j['id']}"):
                        new = {**j, "status":"Applied", "applied_date": date.today().strftime("%Y-%m-%d"), "notes":""}
                        st.session_state.applications.append(new)
                        st.success("Tracked!")

# ══ AI MATCH & APPLY ═════════════════════════════════════════════════════════
elif page == "🤖 AI Match & Apply":
    st.markdown('<div class="section-title">🤖 AI Match Score & Cover Letter</div>', unsafe_allow_html=True)

    if not st.session_state.api_key and not st.secrets.get("ANTHROPIC_API_KEY",""):
        st.warning("⚠️ Add your API key in the sidebar.")

    tab1, tab2 = st.tabs(["📝 Enter Job Manually", "📋 From Search Results"])

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            jt = st.text_input("Job Title *", placeholder="AGM Production Planning")
            jc = st.text_input("Company *",   placeholder="Voltas Ltd")
        with c2:
            jl = st.text_input("Location",    placeholder="Delhi NCR")
            ju = st.text_input("Job URL",      placeholder="https://naukri.com/job/...")
        jd = st.text_area("Paste Job Description (for better accuracy)", height=120)

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("🎯 Score My Match", type="primary", use_container_width=True):
                if jt and jc:
                    with st.spinner("Analysing..."):
                        r = ai_match_job(jt, jc, jd)
                    sc = r.get("score", 0)
                    cls = "match-high" if sc>=70 else ("match-medium" if sc>=50 else "match-low")
                    st.markdown(f"""<div class="job-card">
                      <b>{jt}</b> <span class="{cls}" style="float:right">{sc}% match</span><br>
                      <i>{r.get('verdict','')}</i>
                    </div>""", unsafe_allow_html=True)
                    for s in r.get("strengths",[]): st.success(f"✅ {s}")
                    for g in r.get("gaps",[]): st.warning(f"⚠️ {g}")
        with b2:
            if st.button("✍️ Cover Letter", use_container_width=True):
                if jt and jc:
                    with st.spinner("Writing..."):
                        st.session_state.cover_letter = ai_cover_letter(jt, jc, jd)
        with b3:
            if st.button("➕ Add to Tracker", use_container_width=True):
                if jt and jc:
                    st.session_state.applications.append({
                        "id": f"MAN-{int(time.time())}", "title": jt, "company": jc,
                        "location": jl, "source": ju or "Manual", "url": ju,
                        "status": "Saved", "applied_date": None,
                        "match_score": None, "cover_letter": st.session_state.cover_letter, "notes": ""
                    })
                    st.success("Added to tracker!")

    with tab2:
        scored = [j for j in st.session_state.jobs if (j.get("match_score") or 0) >= 50]
        if not scored:
            st.info("Search for jobs first, then come here to generate cover letters.")
        else:
            sel = st.selectbox("Pick a job", [f"{j['title']} — {j['company']} ({j.get('match_score',0)}%)" for j in scored])
            idx = [f"{j['title']} — {j['company']} ({j.get('match_score',0)}%)" for j in scored].index(sel)
            job = scored[idx]
            if st.button("✍️ Generate Cover Letter", type="primary"):
                with st.spinner("Writing tailored cover letter..."):
                    st.session_state.cover_letter = ai_cover_letter(job["title"], job["company"], job.get("description",""))

    # Cover letter display
    if st.session_state.cover_letter:
        st.markdown("---")
        st.markdown('<div class="section-title">📄 Your Cover Letter</div>', unsafe_allow_html=True)
        edited = st.text_area("Edit if needed:", value=st.session_state.cover_letter, height=300)
        st.session_state.cover_letter = edited
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("⬇️ Download", data=edited, file_name="cover_letter_himanshu.txt", use_container_width=True)
        with c2:
            if st.button("🔄 Regenerate", use_container_width=True):
                st.session_state.cover_letter = ""
                st.rerun()

# ══ TRACKER ══════════════════════════════════════════════════════════════════
elif page == "📋 Tracker":
    st.markdown('<div class="section-title">📋 Applications Tracker</div>', unsafe_allow_html=True)

    with st.expander("➕ Add Application Manually"):
        c1, c2, c3 = st.columns(3)
        with c1:
            mt = st.text_input("Job Title", key="mt")
            mc = st.text_input("Company",   key="mc")
        with c2:
            ml = st.text_input("Location",  key="ml")
            ms = st.selectbox("Status", ["Saved","Applied","Interview","Offer","Rejected"], key="ms")
        with c3:
            md = st.date_input("Date Applied", key="md")
            mu = st.text_input("URL / Source",  key="mu")
        mn = st.text_area("Notes", key="mn", height=50)
        if st.button("Add"):
            st.session_state.applications.append({
                "id": f"M-{int(time.time())}", "title": mt, "company": mc,
                "location": ml, "source": mu, "url": mu,
                "status": ms, "applied_date": str(md), "notes": mn,
                "match_score": None, "cover_letter": ""
            })
            st.success("Added!"); st.rerun()

    apps = st.session_state.applications
    if not apps:
        st.info("No applications yet. Find jobs and click **Mark Applied**!")
    else:
        sf = st.multiselect("Filter status", ["Saved","Applied","Interview","Offer","Rejected"],
                            default=["Saved","Applied","Interview","Offer","Rejected"])
        filtered = [a for a in apps if a.get("status","Saved") in sf]

        df = pd.DataFrame([{
            "Title":    a.get("title",""), "Company": a.get("company",""),
            "Status":   a.get("status",""), "Applied": a.get("applied_date",""),
            "Match %":  a.get("match_score",""), "Source": a.get("source",""),
        } for a in filtered])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Export CSV", data=df.to_csv(index=False),
                           file_name="applications_himanshu.csv", mime="text/csv")

        st.markdown("**Update Status**")
        opts = [f"{a['title']} — {a['company']}" for a in filtered]
        if opts:
            si = st.selectbox("Select", range(len(opts)), format_func=lambda i: opts[i])
            ns = st.selectbox("New status", ["Saved","Applied","Interview","Offer","Rejected"])
            nn = st.text_input("Notes (optional)")
            if st.button("Update"):
                oi = apps.index(filtered[si])
                st.session_state.applications[oi]["status"] = ns
                if nn: st.session_state.applications[oi]["notes"] = nn
                if ns == "Applied" and not apps[oi].get("applied_date"):
                    st.session_state.applications[oi]["applied_date"] = date.today().strftime("%Y-%m-%d")
                st.success("Updated!"); st.rerun()

        if len(apps) > 1:
            c1, c2 = st.columns(2)
            with c1:
                df2 = pd.Series([a["status"] for a in apps]).value_counts().reset_index()
                df2.columns = ["Status","Count"]
                st.plotly_chart(px.pie(df2, names="Status", values="Count", height=280,
                    title="By Status"), use_container_width=True)

# ══ SETTINGS ═════════════════════════════════════════════════════════════════
elif page == "⚙️ Settings":
    st.markdown('<div class="section-title">⚙️ Settings</div>', unsafe_allow_html=True)
    t1, t2 = st.tabs(["🔑 API Key & Cost", "🔒 Security"])

    with t1:
        st.markdown("""
### Your $5 Claude API Key — Cost Breakdown

| Action | Model Used | Cost per use |
|---|---|---|
| Search jobs (web search) | claude-sonnet-4-6 | ~₹2–4 per search |
| Score 10 jobs (match %) | claude-haiku | ~₹0.30 per job |
| Generate cover letter | claude-sonnet-4-6 | ~₹1–2 per letter |

**Your $5 free credit (≈ ₹415) gives you:**
- ~50–80 job searches
- ~500 job match scores
- ~200 cover letters

That's enough for a **full 2–3 month job hunt** at no extra cost.

**To add your key securely on Streamlit Cloud:**
1. Streamlit Cloud → your app → **Settings** → **Secrets**
2. Add: `ANTHROPIC_API_KEY = "sk-ant-your-key-here"`
3. Never paste your key in public screenshots!
        """)
        key = st.text_input("Test your key here", type="password")
        if key and st.button("Test Connection"):
            try:
                c = anthropic.Anthropic(api_key=key)
                c.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10,
                                  messages=[{"role":"user","content":"hi"}])
                st.success("✅ API key works perfectly!")
            except Exception as e:
                st.error(f"❌ {e}")

    with t2:
        st.markdown("""
### Security Checklist

| Item | Status | Action |
|---|---|---|
| API key in Streamlit Secrets | ✅ Safe | Not in code |
| GitHub repo visibility | ⚠️ Check | Set to **Private** |
| App password protection | ⚠️ Optional | Add login below |
| Data persistence | ⚠️ None | Export CSV regularly |

### Add Password Protection (paste at top of app.py)
```python
def check_password():
    if not st.session_state.get("authenticated"):
        st.title("🔒 Login")
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if pwd == st.secrets.get("APP_PASSWORD", ""):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Wrong password")
        st.stop()
check_password()
```
Then add `APP_PASSWORD = "YourPassword"` in Streamlit Secrets.
        """)
