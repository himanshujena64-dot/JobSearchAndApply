import streamlit as st
import anthropic
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
import json
import time
import re
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import urllib.parse

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="JobPilot – Himanshu's Job Tracker",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CUSTOM CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #0D2137 0%, #1A5276 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .main-header h1 { color: white; margin: 0; font-size: 2rem; }
    .main-header p  { color: #AED6F1; margin: 0.3rem 0 0; font-size: 1rem; }

    .metric-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        text-align: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
    .metric-card .value { font-size: 2rem; font-weight: 700; color: #1A5276; }
    .metric-card .label { font-size: 0.8rem; color: #888; margin-top: 0.2rem; }

    .job-card {
        background: white;
        border: 1px solid #e8f4fd;
        border-left: 4px solid #2E75B6;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    .job-card:hover { border-left-color: #F0B429; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    .job-card h4 { margin: 0 0 0.2rem; color: #0D2137; font-size: 1rem; }
    .job-card .company { color: #1A5276; font-weight: 600; font-size: 0.9rem; }
    .job-card .meta { color: #888; font-size: 0.8rem; margin-top: 0.3rem; }

    .match-badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
    }
    .match-high   { background: #d4edda; color: #155724; }
    .match-medium { background: #fff3cd; color: #856404; }
    .match-low    { background: #f8d7da; color: #721c24; }

    .status-badge {
        display: inline-block;
        padding: 0.15rem 0.5rem;
        border-radius: 12px;
        font-size: 0.72rem;
        font-weight: 600;
    }
    .status-applied    { background: #cce5ff; color: #004085; }
    .status-interview  { background: #d4edda; color: #155724; }
    .status-rejected   { background: #f8d7da; color: #721c24; }
    .status-saved      { background: #e2e3e5; color: #383d41; }
    .status-offer      { background: #d1ecf1; color: #0c5460; }

    .cover-letter-box {
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 1.2rem;
        font-size: 0.88rem;
        line-height: 1.7;
        white-space: pre-wrap;
        max-height: 400px;
        overflow-y: auto;
    }
    .section-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #0D2137;
        border-bottom: 2px solid #2E75B6;
        padding-bottom: 0.4rem;
        margin-bottom: 1rem;
    }
    div[data-testid="stSidebar"] { background: #0D2137; }
    div[data-testid="stSidebar"] * { color: white !important; }
    div[data-testid="stSidebar"] .stSelectbox label,
    div[data-testid="stSidebar"] .stTextInput label { color: #AED6F1 !important; }
</style>
""", unsafe_allow_html=True)

# ── SESSION STATE ─────────────────────────────────────────────────────────────
if "jobs"         not in st.session_state: st.session_state.jobs = []
if "applications" not in st.session_state: st.session_state.applications = []
if "api_key"      not in st.session_state: st.session_state.api_key = ""
if "cover_letter" not in st.session_state: st.session_state.cover_letter = ""
if "match_result" not in st.session_state: st.session_state.match_result = {}

# ── RESUME SUMMARY (used for AI matching) ─────────────────────────────────────
RESUME_SUMMARY = """
Name: Himanshu Jena
Current Role: Assistant General Manager – Production Planning & Dispatch, Haier Appliances India
Experience: 15+ years in Production Planning, Supply Chain, Dispatch Management
Industries: HVAC (Air Conditioners), Automotive, Consumer Durables

Key Skills:
- SAP PP, SAP MM, SAP SD, SAP FICO
- MRP Execution, Capacity Planning, S&OP, SIOP, MPS
- BOM, Routing, Material Master, Engineering Change Management
- Inventory Optimisation (RM/WIP/FG), Dispatch Management
- Power BI Dashboards, Advanced Excel, VBS Scripting, Python, Streamlit
- ORTEMS, Plan Visage APS, ERP Oracle
- Six Sigma Yellow Belt, Lean, KANBAN, FIFO

Key Achievements:
- Improved OTIF from 97.9% to 99.9% at Blue Star
- Automated reporting saving ~40% effort via VBS scripting
- Built live Streamlit web app for production intelligence
- Led SAP PP go-live at Havells (master data + UAT)
- Completed 2 Six Sigma projects

Career Progression:
- Haier Appliances: AGM Production Planning & Dispatch (Sep 2025–Present)
- Havells India: Manager PPC (Oct 2022–Sep 2025)
- Blue Star: Asst Manager PPC (Sep 2016–Sep 2022)
- Yazaki India: Engineer PPC (Dec 2014–Sep 2016)
- Sona Koyo: Junior Engineer PPC (Aug 2011–Nov 2014)

Location: Greater Noida, India
Target Roles: AGM/DGM/GM Production Planning, Supply Chain Manager, SAP PP Consultant
Target Salary: Senior/AGM level (₹25–40 LPA range)
"""

# ── JOB SEARCH SCRAPER ────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

SEARCH_QUERIES = {
    "Production Planning / PPC":  ["AGM production planning", "DGM production planning HVAC", "Manager PPC supply chain"],
    "Supply Chain Manager":        ["Supply chain manager Greater Noida", "SCM AGM India", "head supply chain HVAC"],
    "SAP PP Consultant":           ["SAP PP consultant India", "SAP PP functional lead", "SAP production planning"],
    "All of the above":            ["AGM production planning", "supply chain manager HVAC", "SAP PP lead India", "DGM PPC"],
}

def scrape_indeed(query, location="India", max_results=15):
    """Scrape Indeed India for jobs."""
    jobs = []
    try:
        encoded_q   = urllib.parse.quote(query)
        encoded_loc = urllib.parse.quote(location)
        url = f"https://in.indeed.com/jobs?q={encoded_q}&l={encoded_loc}&sort=date"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.find_all("div", class_=re.compile(r"job_seen_beacon|jobsearch-ResultsList"))
        for card in cards[:max_results]:
            title_el   = card.find(["h2","h3"], class_=re.compile(r"jobTitle|title"))
            company_el = card.find("span",  class_=re.compile(r"companyName|company"))
            loc_el     = card.find("div",   class_=re.compile(r"companyLocation|location"))
            link_el    = card.find("a",     href=True)
            if not title_el: continue
            link = "https://in.indeed.com" + link_el["href"] if link_el and link_el["href"].startswith("/") else (link_el["href"] if link_el else "#")
            jobs.append({
                "title":    title_el.get_text(strip=True),
                "company":  company_el.get_text(strip=True) if company_el else "N/A",
                "location": loc_el.get_text(strip=True)     if loc_el     else location,
                "source":   "Indeed",
                "url":      link,
                "posted":   "Recent",
                "match_score": None,
                "match_reason": "",
                "status":   "Saved",
                "applied_date": None,
                "cover_letter": "",
                "id": f"IND-{hash(title_el.get_text()+str(company_el))}"
            })
    except Exception as e:
        st.warning(f"Indeed scrape issue: {e}")
    return jobs

def scrape_naukri(query, max_results=15):
    """Scrape Naukri.com for jobs."""
    jobs = []
    try:
        encoded_q = urllib.parse.quote(query.replace(" ", "-"))
        url = f"https://www.naukri.com/{encoded_q}-jobs"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.find_all("article", class_=re.compile(r"jobTuple|job-tuple"))
        for card in cards[:max_results]:
            title_el   = card.find(["a","h2"], class_=re.compile(r"title|jobTitle"))
            company_el = card.find(["a","span"], class_=re.compile(r"company|companyInfo"))
            loc_el     = card.find(["span","li"], class_=re.compile(r"location|loc"))
            exp_el     = card.find(["span","li"], class_=re.compile(r"experience|exp"))
            if not title_el: continue
            link = title_el.get("href","#") if title_el.name == "a" else "#"
            jobs.append({
                "title":    title_el.get_text(strip=True),
                "company":  company_el.get_text(strip=True) if company_el else "N/A",
                "location": loc_el.get_text(strip=True)     if loc_el     else "India",
                "experience": exp_el.get_text(strip=True)   if exp_el     else "",
                "source":   "Naukri",
                "url":      link if link.startswith("http") else "https://www.naukri.com" + link,
                "posted":   "Recent",
                "match_score": None,
                "match_reason": "",
                "status":   "Saved",
                "applied_date": None,
                "cover_letter": "",
                "id": f"NAU-{hash(title_el.get_text()+str(company_el))}"
            })
    except Exception as e:
        st.warning(f"Naukri scrape issue: {e}")
    return jobs

def get_linkedin_search_url(query):
    """Generate LinkedIn job search URL (opens in browser — LinkedIn blocks scraping)."""
    encoded = urllib.parse.quote(query)
    return f"https://www.linkedin.com/jobs/search/?keywords={encoded}&location=India&f_TPR=r86400&sortBy=DD"

# ── AI FUNCTIONS ───────────────────────────────────────────────────────────────
def get_client():
    key = st.session_state.api_key or st.secrets.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)

def ai_match_job(job_title, job_company, job_description=""):
    """Score how well Himanshu matches this job using Claude."""
    client = get_client()
    if not client:
        return {"score": 0, "verdict": "⚠️ Add API key", "strengths": [], "gaps": []}
    prompt = f"""You are an expert recruiter. Score how well this candidate matches the job.

CANDIDATE RESUME:
{RESUME_SUMMARY}

JOB:
Title: {job_title}
Company: {job_company}
Description: {job_description or "Not provided — judge by title only"}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "score": <integer 0-100>,
  "verdict": "<one line summary>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "gaps": ["<gap 1>", "<gap 2>"]
}}"""
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)
    except Exception as e:
        return {"score": 50, "verdict": f"Could not parse: {e}", "strengths": [], "gaps": []}

def ai_cover_letter(job_title, job_company, job_description=""):
    """Generate a tailored cover letter using Claude."""
    client = get_client()
    if not client:
        return "⚠️ Please add your Anthropic API key in the sidebar."
    prompt = f"""Write a professional, concise cover letter for this job application.

CANDIDATE:
{RESUME_SUMMARY}

JOB:
Title: {job_title}
Company: {job_company}
Description: {job_description or "Focus on the role title"}

Guidelines:
- 3 short paragraphs, no longer than 250 words total
- Paragraph 1: Why this role and company specifically
- Paragraph 2: 2-3 specific achievements from resume that match the role
- Paragraph 3: Call to action
- Professional but warm tone
- Do NOT use generic phrases like "I am writing to apply..."
- Start with something specific about the role or company
- End with: "Warm regards,\\nHimanshu Jena\\n+91-7018083915 | himanshujena64@gmail.com"

Write the cover letter only, no commentary."""
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"Error generating cover letter: {e}"

def ai_batch_score(jobs):
    """Score multiple jobs efficiently."""
    client = get_client()
    if not client:
        return jobs
    for i, job in enumerate(jobs):
        if job.get("match_score") is not None:
            continue
        result = ai_match_job(job["title"], job["company"])
        jobs[i]["match_score"]  = result.get("score", 50)
        jobs[i]["match_reason"] = result.get("verdict", "")
        jobs[i]["strengths"]    = result.get("strengths", [])
        jobs[i]["gaps"]         = result.get("gaps", [])
        time.sleep(0.3)  # rate limit
    return jobs

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎯 JobPilot")
    st.markdown("*Your AI-powered job hunt*")
    st.divider()

    page = st.radio("Navigate", [
        "🏠 Dashboard",
        "🔍 Find Jobs",
        "🤖 AI Match & Apply",
        "📋 Applications Tracker",
        "⚙️ Settings",
    ], label_visibility="collapsed")

    st.divider()
    st.markdown("**API Key**")
    api_input = st.text_input("Anthropic API Key", type="password",
                               value=st.session_state.api_key,
                               placeholder="sk-ant-...",
                               help="Get free key at console.anthropic.com")
    if api_input:
        st.session_state.api_key = api_input
        st.success("✓ Key saved")

    st.divider()
    st.markdown(f"**Total jobs found:** {len(st.session_state.jobs)}")
    apps = st.session_state.applications
    st.markdown(f"**Applications sent:** {len([a for a in apps if a['status'] != 'Saved'])}")
    st.markdown(f"**Interviews:** {len([a for a in apps if a['status'] == 'Interview'])}")

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
  <h1>🎯 JobPilot — Himanshu Jena</h1>
  <p>AGM Production Planning & Dispatch · 15+ Years · Greater Noida</p>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Dashboard":
    apps = st.session_state.applications

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f'<div class="metric-card"><div class="value">{len(st.session_state.jobs)}</div><div class="label">Jobs Found</div></div>', unsafe_allow_html=True)
    with c2:
        applied = len([a for a in apps if a["status"] not in ("Saved",)])
        st.markdown(f'<div class="metric-card"><div class="value">{applied}</div><div class="label">Applied</div></div>', unsafe_allow_html=True)
    with c3:
        interviews = len([a for a in apps if a["status"] == "Interview"])
        st.markdown(f'<div class="metric-card"><div class="value">{interviews}</div><div class="label">Interviews</div></div>', unsafe_allow_html=True)
    with c4:
        high_match = len([j for j in st.session_state.jobs if (j.get("match_score") or 0) >= 70])
        st.markdown(f'<div class="metric-card"><div class="value">{high_match}</div><div class="label">Strong Matches</div></div>', unsafe_allow_html=True)
    with c5:
        offers = len([a for a in apps if a["status"] == "Offer"])
        st.markdown(f'<div class="metric-card"><div class="value">{offers}</div><div class="label">Offers</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.markdown('<div class="section-title">📊 Application Pipeline</div>', unsafe_allow_html=True)
        if apps:
            status_counts = pd.Series([a["status"] for a in apps]).value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            colors_map = {"Saved":"#6c757d","Applied":"#2E75B6","Interview":"#28a745","Rejected":"#dc3545","Offer":"#17a2b8"}
            fig = px.bar(status_counts, x="Status", y="Count",
                         color="Status", color_discrete_map=colors_map,
                         text="Count", height=280)
            fig.update_layout(showlegend=False, plot_bgcolor="white",
                              margin=dict(t=20,b=20,l=20,r=20))
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📭 No applications yet. Go to **Find Jobs** to get started!")

    with col_r:
        st.markdown('<div class="section-title">🔥 Top Matches</div>', unsafe_allow_html=True)
        scored = [j for j in st.session_state.jobs if j.get("match_score") is not None]
        top    = sorted(scored, key=lambda x: x["match_score"], reverse=True)[:5]
        if top:
            for j in top:
                score = j["match_score"]
                badge = "match-high" if score >= 70 else ("match-medium" if score >= 50 else "match-low")
                st.markdown(f"""
                <div class="job-card">
                  <h4>{j['title'][:45]}{'…' if len(j['title'])>45 else ''}</h4>
                  <span class="company">{j['company']}</span>
                  <span class="match-badge {badge}" style="float:right">{score}% match</span>
                  <div class="meta">📍 {j['location']} &nbsp;|&nbsp; {j['source']}</div>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("Score jobs in **AI Match & Apply** to see top matches here.")

    # Follow-up reminders
    st.markdown('<div class="section-title">⏰ Follow-up Reminders</div>', unsafe_allow_html=True)
    today = date.today()
    reminders = []
    for a in apps:
        if a.get("applied_date") and a["status"] == "Applied":
            try:
                ap_date = datetime.strptime(a["applied_date"], "%Y-%m-%d").date()
                days_since = (today - ap_date).days
                if days_since >= 7:
                    reminders.append({**a, "days_since": days_since})
            except: pass
    if reminders:
        for r in reminders[:5]:
            st.warning(f"📬 **{r['title']}** at {r['company']} — applied {r['days_since']} days ago. Time to follow up!")
    else:
        st.success("✅ No follow-ups due right now.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: FIND JOBS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Find Jobs":
    st.markdown('<div class="section-title">🔍 Search Jobs</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        role_filter = st.selectbox("Job Role Category", list(SEARCH_QUERIES.keys()))
    with col2:
        portal = st.selectbox("Portal", ["All", "Naukri", "Indeed", "LinkedIn"])
    with col3:
        custom_query = st.text_input("Custom search (optional)", placeholder="e.g. VP Operations")

    col_a, col_b = st.columns([1, 3])
    with col_a:
        search_btn = st.button("🔍 Search Now", use_container_width=True, type="primary")
    with col_b:
        auto_score = st.checkbox("Auto-score with AI after search", value=True,
                                 help="Uses Claude API to score each job — costs ~₹0.50 per job")

    # LinkedIn quick links (always shown)
    st.markdown("**LinkedIn Quick Search Links** (opens in new tab):")
    lc = st.columns(4)
    queries_flat = SEARCH_QUERIES.get(role_filter, [])
    for i, q in enumerate(queries_flat[:4]):
        with lc[i % 4]:
            url = get_linkedin_search_url(q)
            st.markdown(f'<a href="{url}" target="_blank">🔗 {q[:25]}</a>', unsafe_allow_html=True)

    if search_btn:
        queries = [custom_query] if custom_query else SEARCH_QUERIES.get(role_filter, [])
        found_jobs = []

        with st.spinner("🔍 Searching job portals..."):
            for q in queries:
                if portal in ("All", "Naukri"):
                    found_jobs += scrape_naukri(q, max_results=10)
                if portal in ("All", "Indeed"):
                    found_jobs += scrape_indeed(q, max_results=10)

        # Deduplicate
        seen, unique = set(), []
        for j in found_jobs:
            key = f"{j['title'].lower()[:30]}_{j['company'].lower()[:20]}"
            if key not in seen:
                seen.add(key)
                unique.append(j)

        if unique:
            if auto_score and st.session_state.api_key:
                with st.spinner(f"🤖 AI scoring {len(unique)} jobs..."):
                    unique = ai_batch_score(unique)

            st.session_state.jobs = unique
            st.success(f"✅ Found {len(unique)} unique jobs!")
        else:
            st.warning("No jobs scraped. Portals may be blocking. Try LinkedIn links above.")

    # Display jobs
    if st.session_state.jobs:
        st.markdown(f"<br>**{len(st.session_state.jobs)} jobs found** — sorted by match score", unsafe_allow_html=True)

        score_filter = st.slider("Minimum match score", 0, 100, 0, 5,
                                  help="Filter jobs by AI match score")
        display_jobs = [j for j in st.session_state.jobs
                        if (j.get("match_score") or 0) >= score_filter]
        display_jobs = sorted(display_jobs, key=lambda x: x.get("match_score") or 0, reverse=True)

        for j in display_jobs:
            score = j.get("match_score")
            if score is None:
                badge_html = '<span class="match-badge" style="background:#eee;color:#666">Not scored</span>'
            elif score >= 70:
                badge_html = f'<span class="match-badge match-high">{score}% ✓ Strong</span>'
            elif score >= 50:
                badge_html = f'<span class="match-badge match-medium">{score}% ~ Fair</span>'
            else:
                badge_html = f'<span class="match-badge match-low">{score}% ✗ Low</span>'

            with st.expander(f"**{j['title']}** — {j['company']} | {j['source']}"):
                c_left, c_right = st.columns([3, 1])
                with c_left:
                    st.markdown(f"**Company:** {j['company']}")
                    st.markdown(f"**Location:** {j['location']}")
                    st.markdown(f"**Source:** {j['source']}  |  **Posted:** {j.get('posted','Recent')}")
                    if j.get("match_reason"):
                        st.markdown(f"**AI Verdict:** {j['match_reason']}")
                    if j.get("strengths"):
                        st.markdown("**Your strengths for this role:**")
                        for s in j["strengths"]:
                            st.markdown(f"  ✅ {s}")
                    if j.get("gaps"):
                        st.markdown("**Potential gaps:**")
                        for g in j["gaps"]:
                            st.markdown(f"  ⚠️ {g}")
                with c_right:
                    st.markdown(badge_html, unsafe_allow_html=True)
                    st.markdown(f'<a href="{j["url"]}" target="_blank"><button style="width:100%;padding:0.5rem;background:#2E75B6;color:white;border:none;border-radius:6px;cursor:pointer;margin-top:0.5rem">🔗 View Job</button></a>', unsafe_allow_html=True)

                    if st.button("🤖 Generate Cover Letter", key=f"cl_{j['id']}"):
                        with st.spinner("Writing cover letter..."):
                            letter = ai_cover_letter(j["title"], j["company"])
                        st.session_state.cover_letter = letter
                        st.session_state.match_result = j
                        st.success("Cover letter ready! Go to **AI Match & Apply** tab.")

                    if st.button("✅ Mark as Applied", key=f"app_{j['id']}"):
                        new_app = {**j, "status": "Applied",
                                   "applied_date": date.today().strftime("%Y-%m-%d"),
                                   "notes": ""}
                        st.session_state.applications.append(new_app)
                        st.success("Added to Applications Tracker!")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: AI MATCH & APPLY
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🤖 AI Match & Apply":
    st.markdown('<div class="section-title">🤖 AI Match & Cover Letter Generator</div>', unsafe_allow_html=True)

    if not st.session_state.api_key:
        st.warning("⚠️ Add your Anthropic API key in the sidebar first! Get a free key at console.anthropic.com")

    tab1, tab2 = st.tabs(["📝 Manual Job Entry", "📋 From Job List"])

    with tab1:
        st.markdown("**Enter job details manually (e.g. from LinkedIn)**")
        col1, col2 = st.columns(2)
        with col1:
            jt = st.text_input("Job Title", placeholder="AGM Production Planning")
            jc = st.text_input("Company Name", placeholder="Voltas Ltd")
        with col2:
            jl = st.text_input("Location", placeholder="Greater Noida / Delhi NCR")
            js = st.text_input("Source / URL", placeholder="https://linkedin.com/jobs/...")

        jd = st.text_area("Job Description (paste here for better matching)",
                           height=150, placeholder="Paste the full job description here for most accurate AI matching...")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🎯 Score My Match", use_container_width=True, type="primary"):
                if jt and jc:
                    with st.spinner("Analysing match..."):
                        result = ai_match_job(jt, jc, jd)
                    score = result.get("score", 0)
                    badge = "match-high" if score >= 70 else ("match-medium" if score >= 50 else "match-low")
                    st.markdown(f"""
                    <div class="job-card">
                      <h4>{jt}</h4>
                      <span class="company">{jc}</span>
                      <span class="match-badge {badge}" style="float:right">{score}% match</span>
                      <div class="meta" style="margin-top:0.5rem">{result.get('verdict','')}</div>
                    </div>""", unsafe_allow_html=True)

                    if result.get("strengths"):
                        st.markdown("**Your strengths:**")
                        for s in result["strengths"]: st.success(f"✅ {s}")
                    if result.get("gaps"):
                        st.markdown("**Potential gaps:**")
                        for g in result["gaps"]: st.warning(f"⚠️ {g}")
        with col_btn2:
            if st.button("✍️ Generate Cover Letter", use_container_width=True):
                if jt and jc:
                    with st.spinner("Writing tailored cover letter..."):
                        letter = ai_cover_letter(jt, jc, jd)
                    st.session_state.cover_letter = letter

        if st.button("➕ Add to Tracker", use_container_width=True) and jt and jc:
            new_app = {
                "id": f"MAN-{hash(jt+jc)}",
                "title": jt, "company": jc, "location": jl,
                "source": js or "Manual", "url": js,
                "status": "Saved", "applied_date": None,
                "match_score": None, "match_reason": "", "notes": "",
                "cover_letter": st.session_state.cover_letter,
            }
            st.session_state.applications.append(new_app)
            st.success("✅ Added to Applications Tracker!")

    with tab2:
        scored_jobs = [j for j in st.session_state.jobs if j.get("match_score", 0) >= 60]
        if not scored_jobs:
            st.info("No scored jobs yet. Go to **Find Jobs** and search first.")
        else:
            selected = st.selectbox("Pick a job",
                                    [f"{j['title']} — {j['company']} ({j.get('match_score',0)}%)" for j in scored_jobs])
            idx = [f"{j['title']} — {j['company']} ({j.get('match_score',0)}%)" for j in scored_jobs].index(selected)
            job = scored_jobs[idx]

            if st.button("✍️ Generate Cover Letter for This Job", type="primary"):
                with st.spinner("Writing cover letter..."):
                    letter = ai_cover_letter(job["title"], job["company"])
                st.session_state.cover_letter = letter

    # Cover letter display
    if st.session_state.cover_letter:
        st.markdown("---")
        st.markdown('<div class="section-title">📄 Generated Cover Letter</div>', unsafe_allow_html=True)
        edited = st.text_area("Edit if needed:", value=st.session_state.cover_letter, height=320)
        st.session_state.cover_letter = edited

        col1, col2, col3 = st.columns(3)
        with col1:
            st.download_button("⬇️ Download Cover Letter",
                               data=edited, file_name="cover_letter_himanshu.txt",
                               mime="text/plain", use_container_width=True)
        with col2:
            if st.button("📋 Copy to Clipboard (select all)", use_container_width=True):
                st.info("Select all text in the box above and copy (Ctrl+A, Ctrl+C)")
        with col3:
            if st.button("🔄 Regenerate", use_container_width=True):
                st.session_state.cover_letter = ""
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: APPLICATIONS TRACKER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 Applications Tracker":
    st.markdown('<div class="section-title">📋 Applications Tracker</div>', unsafe_allow_html=True)

    # Add manual entry
    with st.expander("➕ Add Application Manually"):
        c1, c2, c3 = st.columns(3)
        with c1:
            m_title   = st.text_input("Job Title", key="m_title")
            m_company = st.text_input("Company",   key="m_company")
        with c2:
            m_loc     = st.text_input("Location",  key="m_loc")
            m_source  = st.text_input("Source/URL", key="m_source")
        with c3:
            m_status  = st.selectbox("Status", ["Saved","Applied","Interview","Offer","Rejected"], key="m_status")
            m_date    = st.date_input("Applied Date", key="m_date")
        m_notes = st.text_area("Notes", key="m_notes", height=60)
        if st.button("Add Application"):
            st.session_state.applications.append({
                "id": f"MAN-{int(time.time())}",
                "title": m_title, "company": m_company,
                "location": m_loc, "source": m_source, "url": m_source,
                "status": m_status, "applied_date": str(m_date),
                "match_score": None, "match_reason": "", "notes": m_notes,
                "cover_letter": "",
            })
            st.success("Application added!")
            st.rerun()

    apps = st.session_state.applications
    if not apps:
        st.info("📭 No applications tracked yet. Find jobs and click **Mark as Applied**!")
    else:
        # Filters
        f1, f2 = st.columns(2)
        with f1:
            status_filter = st.multiselect("Filter by status",
                                           ["Saved","Applied","Interview","Offer","Rejected"],
                                           default=["Saved","Applied","Interview","Offer","Rejected"])
        with f2:
            sort_by = st.selectbox("Sort by", ["Date Applied","Match Score","Company"])

        filtered = [a for a in apps if a.get("status","Saved") in status_filter]

        if sort_by == "Match Score":
            filtered = sorted(filtered, key=lambda x: x.get("match_score") or 0, reverse=True)
        elif sort_by == "Company":
            filtered = sorted(filtered, key=lambda x: x.get("company",""))
        else:
            filtered = sorted(filtered, key=lambda x: x.get("applied_date") or "0000", reverse=True)

        # Table view
        if filtered:
            df = pd.DataFrame([{
                "Title":        a.get("title",""),
                "Company":      a.get("company",""),
                "Location":     a.get("location",""),
                "Status":       a.get("status","Saved"),
                "Applied":      a.get("applied_date",""),
                "Match %":      a.get("match_score",""),
                "Source":       a.get("source",""),
            } for a in filtered])
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Download
            csv = df.to_csv(index=False)
            st.download_button("⬇️ Export to CSV", data=csv,
                               file_name="job_applications_himanshu.csv",
                               mime="text/csv")

        # Status updater
        st.markdown("---")
        st.markdown("**Update Application Status**")
        if filtered:
            options = [f"{a['title']} — {a['company']}" for a in filtered]
            sel_idx  = st.selectbox("Select application", range(len(options)),
                                    format_func=lambda i: options[i])
            new_status = st.selectbox("New status", ["Saved","Applied","Interview","Offer","Rejected"])
            new_notes  = st.text_input("Add notes")
            if st.button("Update Status"):
                orig_idx = apps.index(filtered[sel_idx])
                st.session_state.applications[orig_idx]["status"] = new_status
                if new_notes:
                    st.session_state.applications[orig_idx]["notes"] = new_notes
                if new_status == "Applied" and not apps[orig_idx].get("applied_date"):
                    st.session_state.applications[orig_idx]["applied_date"] = date.today().strftime("%Y-%m-%d")
                st.success("✅ Updated!")
                st.rerun()

        # Charts
        if len(apps) > 1:
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                status_df = pd.Series([a["status"] for a in apps]).value_counts().reset_index()
                status_df.columns = ["Status","Count"]
                fig = px.pie(status_df, names="Status", values="Count",
                             title="Applications by Status",
                             color_discrete_sequence=px.colors.qualitative.Set2)
                fig.update_layout(height=300, margin=dict(t=40,b=0))
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                src_df = pd.Series([a["source"] for a in apps]).value_counts().reset_index()
                src_df.columns = ["Source","Count"]
                fig2 = px.bar(src_df, x="Source", y="Count", title="Applications by Source",
                              color="Count", color_continuous_scale="Blues")
                fig2.update_layout(height=300, margin=dict(t=40,b=0), showlegend=False)
                st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ Settings":
    st.markdown('<div class="section-title">⚙️ Settings & Info</div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["🔑 API Key", "📄 Resume Profile", "ℹ️ How to Deploy"])

    with tab1:
        st.markdown("### Anthropic API Key")
        st.markdown("""
        **How to get your free API key:**
        1. Go to [console.anthropic.com](https://console.anthropic.com)
        2. Sign up with your email
        3. Go to **API Keys** → **Create Key**
        4. Copy the key (starts with `sk-ant-...`)
        5. Paste it in the sidebar

        **Cost estimate for this app:**
        - Job match scoring (Haiku): ~₹0.30–0.50 per job
        - Cover letter (Sonnet): ~₹1–2 per letter
        - Free credits on signup: **$5 ≈ ₹415** → enough for 200+ cover letters
        """)
        key_val = st.text_input("Your API Key", type="password", value=st.session_state.api_key)
        if key_val:
            st.session_state.api_key = key_val
            if st.button("Test API Key"):
                try:
                    client = anthropic.Anthropic(api_key=key_val)
                    client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10,
                                           messages=[{"role":"user","content":"Hi"}])
                    st.success("✅ API key works!")
                except Exception as e:
                    st.error(f"❌ Key error: {e}")

    with tab2:
        st.markdown("### Your Resume Profile")
        st.markdown("*This is what the AI uses to score jobs and write cover letters.*")
        st.code(RESUME_SUMMARY, language="text")
        st.info("To customise this, edit the `RESUME_SUMMARY` variable in `app.py`")

    with tab3:
        st.markdown("### 🚀 How to Deploy on Streamlit Cloud (Free)")
        st.markdown("""
        **Step 1 — Push to GitHub:**
        ```bash
        git init
        git add .
        git commit -m "Initial JobPilot app"
        git remote add origin https://github.com/YOUR_USERNAME/jobpilot.git
        git push -u origin main
        ```

        **Step 2 — Deploy on Streamlit Cloud (Free):**
        1. Go to [share.streamlit.io](https://share.streamlit.io)
        2. Sign in with GitHub
        3. Click **New App** → select your repo → set `app.py` as main file
        4. Click **Deploy** — live in 2 minutes!

        **Step 3 — Add your API key securely:**
        - In Streamlit Cloud → your app → **Settings** → **Secrets**
        - Add: `ANTHROPIC_API_KEY = "sk-ant-your-key-here"`
        - This keeps your key safe (not in code)

        **Files needed in your repo:**
        ```
        jobpilot/
        ├── app.py            ← main app
        ├── requirements.txt  ← dependencies
        └── README.md         ← optional
        ```

        **That's it! Your app will be live at:**
        `https://your-username-jobpilot.streamlit.app`
        """)
