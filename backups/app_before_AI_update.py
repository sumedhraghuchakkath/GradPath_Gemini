"""Undergraduate career dashboard with resume coaching and daily-feed support."""

from __future__ import annotations

import hashlib
import io
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None
try:
    from sklearn.linear_model import LinearRegression
except ImportError:
    LinearRegression = None

APP_DIR = Path(__file__).resolve().parent
LOCAL_CSV = APP_DIR / "hiring_data.csv"
FEED_REQUIRED = {"Year", "Sector", "Job_Role", "Hiring_Count", "Location"}
COLORS = ["#2563EB", "#0F9D8A", "#8B5CF6", "#F59E0B", "#E85D75", "#0891B2"]
BLUE = "#2563EB"
TEAL = "#0F9D8A"

st.set_page_config(
    page_title="GradPath | Resume, Courses & Careers",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .stApp { background: #F4F7FC; }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] { background: #13223D; }
    [data-testid="stSidebar"] * { color: #EDF3FC; }
    [data-testid="stSidebar"] [data-baseweb="tag"] { background: #24436D; }
    .hero { padding: 1.65rem 1.9rem; border-radius: 20px; color: white;
      background: linear-gradient(115deg, #13223D 0%, #1C4774 58%, #11877F 100%);
      margin: .2rem 0 1.1rem; box-shadow: 0 12px 28px rgba(19,34,61,.15); }
    .hero h1 { font-family: 'Manrope', sans-serif; font-size: 2rem; margin: 0 0 .35rem; }
    .hero p { color: #DCEBFA; font-size: 1rem; margin: 0; }
    .eyebrow { text-transform: uppercase; letter-spacing: .13em; font-size: .72rem;
      color: #98F0DF; font-weight: 700; margin-bottom: .45rem; }
    div[data-testid="stMetric"] { background: white; border: 1px solid #E4EAF3;
      padding: .95rem 1.05rem; border-radius: 15px; box-shadow: 0 4px 14px rgba(19,34,61,.04); }
    div[data-testid="stMetricLabel"] { color: #58677E; }
    div[data-testid="stMetricValue"] { color: #13223D; font-family: 'Manrope', sans-serif; }
    h2, h3 { font-family: 'Manrope', sans-serif !important; color: #13223D; }
    .hint { color: #58677E; margin-top: -.55rem; margin-bottom: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_local_history(path: str) -> pd.DataFrame:
    return normalize_market_frame(pd.read_csv(path))


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def fetch_daily_feed(csv_url: str, token: str) -> tuple[pd.DataFrame, str]:
    """Fetch an authorized, normalized CSV at most once per day."""
    headers = {"Accept": "text/csv"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(csv_url, headers=headers)
    with urlopen(request, timeout=20) as response:
        body = response.read()
    if not body:
        raise ValueError("The trend feed returned an empty file.")
    frame = normalize_market_frame(pd.read_csv(io.BytesIO(body)))
    return frame, datetime.now().astimezone().isoformat(timespec="minutes")


def normalize_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data.columns = [str(column).strip() for column in data.columns]
    keep = ~pd.Index(data.columns).str.lower().str.startswith("unnamed")
    data = data.loc[:, keep]
    missing = sorted(FEED_REQUIRED.difference(data.columns))
    if missing:
        raise ValueError("Trend file is missing required columns: " + ", ".join(missing))
    for column in ["Year", "Hiring_Count", "Hiring_Growth_%", "Placement_Count", "Average_Salary", "Source_Page"]:
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    for column in ["Demand_Trend", "Month", "Source", "Company"]:
        if column not in data.columns:
            data[column] = "Not supplied"
        data[column] = data[column].fillna("Not supplied").astype(str).str.strip()
    for column in ["Sector", "Job_Role", "Location"]:
        data[column] = data[column].fillna("Unknown").astype(str).str.strip()
    for column in ["Hiring_Growth_%", "Placement_Count", "Average_Salary"]:
        if column not in data.columns:
            data[column] = float("nan")
    data = data.dropna(subset=["Year", "Hiring_Count"])
    data["Year"] = data["Year"].astype(int)
    return data


def read_feed_settings() -> tuple[str, str]:
    url = os.environ.get("JOBS_TRENDS_CSV_URL", "").strip()
    token = os.environ.get("JOBS_TRENDS_API_TOKEN", "").strip()
    try:
        settings = st.secrets.get("jobs", {})
        url = str(settings.get("csv_url", url)).strip()
        token = str(settings.get("api_token", token)).strip()
    except Exception:
        pass
    return url, token


def load_market_data() -> tuple[pd.DataFrame, str, str, str | None]:
    """Prefer the configured daily feed; retain the local file only as history."""
    url, token = read_feed_settings()
    if url:
        try:
            data, checked_at = fetch_daily_feed(url, token)
            return data, "Authorized daily feed", checked_at, None
        except Exception as error:
            fallback = load_local_history(str(LOCAL_CSV)) if LOCAL_CSV.exists() else pd.DataFrame()
            return fallback, "Historical CSV fallback", "Not refreshed", str(error)
    history = load_local_history(str(LOCAL_CSV)) if LOCAL_CSV.exists() else pd.DataFrame()
    return history, "Historical CSV (static)", "Not refreshed", None


def extract_docx_text(file_bytes: bytes) -> str:
    """Read DOCX paragraphs using the standard library; do not write the upload."""
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines = []
    for paragraph in root.findall(".//w:p", ns):
        line = "".join(item.text or "" for item in paragraph.findall(".//w:t", ns))
        if line.strip():
            lines.append(line)
    return "\n".join(lines)


def extract_resume_text(filename: str, file_bytes: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return file_bytes.decode("utf-8-sig", errors="replace").strip()
    if suffix == ".docx":
        return extract_docx_text(file_bytes).strip()
    if suffix == ".pdf":
        if PdfReader is None:
            raise RuntimeError("PDF reading needs pypdf. Install the project packages with: pip install -r requirements.txt")
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            raise ValueError("This PDF is password-protected. Upload an unlocked copy.")
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    raise ValueError("Upload a PDF, DOCX or TXT resume.")


SECTION_NAMES = {
    "summary": {"summary", "professional summary", "profile", "career objective", "objective", "about me"},
    "education": {"education", "academic background", "academic qualifications", "qualification"},
    "experience": {"experience", "work experience", "internship", "internships", "employment"},
    "projects": {"projects", "academic projects", "project experience"},
    "skills": {"skills", "technical skills", "core skills", "skills and tools"},
    "certifications": {"certifications", "certificates", "courses"},
    "achievements": {"achievements", "awards", "activities", "leadership"},
}


def split_resume_sections(text: str) -> dict[str, str]:
    sections = {name: [] for name in SECTION_NAMES}
    sections["other"] = []
    active = "other"
    for line in text.splitlines():
        heading = re.sub(r"[^a-z ]", "", line.lower()).strip()
        found = next((name for name, aliases in SECTION_NAMES.items() if heading in aliases), None)
        if found:
            active = found
        elif line.strip():
            sections[active].append(line.rstrip())
    result = {name: "\n".join(lines).strip() for name, lines in sections.items()}
    if not any(result[name] for name in SECTION_NAMES):
        result["other"] = text.strip()
    return result


SKILL_TERMS = [
    "Python", "SQL", "Excel", "Power BI", "Tableau", "Java", "JavaScript",
    "C++", "C#", "React", "Node.js", "Git", "AWS", "Azure", "Docker",
    "Machine Learning", "Data Analysis", "Statistics", "Pandas", "NumPy",
    "Communication", "Leadership", "Project Management", "Financial Modeling",
    "SEO", "Digital Marketing", "Figma", "Networking", "Cybersecurity",
    "AutoCAD", "SolidWorks", "Research", "Writing",
]


def detect_skills(text: str) -> list[str]:
    folded = text.casefold()
    return [skill for skill in SKILL_TERMS if skill.casefold() in folded]


def detect_cgpa(text: str) -> tuple[float | None, float | None]:
    pattern = r"(?i)\b(?:cgpa|c\.g\.p\.a\.|gpa|grade point average)\b\s*[:=\-]?\s*(\d{1,2}(?:\.\d{1,2})?)\s*(?:/\s*(10|4|100))?"
    match = re.search(pattern, text)
    if match:
        value = float(match.group(1))
        maximum = float(match.group(2) or (10 if value <= 10 else 100))
        if 0 <= value <= maximum:
            return value, maximum
    return None, None


def extract_contact_lines(text: str) -> list[str]:
    found = []
    for line in text.splitlines()[:18]:
        line = line.strip()
        if line and (
            re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", line)
            or re.search(r"(?:\+?\d[\d ()-]{8,}\d)", line)
            or not found
        ):
            found.append(line)
        if len(found) >= 4:
            break
    return found


STOP_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "will", "your",
    "you", "are", "our", "have", "has", "was", "were", "who", "what",
    "when", "where", "how", "not", "but", "can", "all", "any", "job",
    "role", "work", "team", "using", "use", "able", "ability", "must",
    "should", "their", "they", "them", "into", "about", "over", "under",
}


def description_terms(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", text.casefold())
    return list(dict.fromkeys(word for word in words if word not in STOP_WORDS))[:50]


def compare_resume_to_job(text: str, description: str) -> tuple[list[str], list[str]]:
    terms = description_terms(description)
    folded = text.casefold()
    return [word for word in terms if word in folded], [word for word in terms if word not in folded]


def build_resume_draft(
    text: str,
    sections: dict[str, str],
    skills: list[str],
    target_role: str,
    cgpa: float | None,
    cgpa_max: float,
    contact_lines: list[str],
) -> str:
    """Create an editable, fact-preserving outline; never invent achievements."""
    blocks = [
        f"TARGET ROLE: {target_role}",
        "",
        "NAME AND CONTACT",
        "\n".join(contact_lines) if contact_lines else "[Add your name, email, phone and professional profile link]",
        "",
        "PROFILE SUMMARY",
        sections["summary"] or "[Write 2-3 lines about your degree, strongest verified skills, and target role.]",
        "",
        "EDUCATION",
        sections["education"] or "[Add degree, institution, expected graduation and verified CGPA/marks.]",
    ]
    if cgpa is not None:
        blocks.extend(["", f"CGPA / GPA (as provided): {cgpa:g} / {cgpa_max:g}"])
    blocks.extend([
        "",
        "ROLE-RELEVANT SKILLS",
        ", ".join(skills) if skills else "[Add only skills you can demonstrate.]",
        "",
        "PROJECTS",
        sections["projects"] or "[Add 1-3 projects. For each: problem, your contribution, tools, and a result you can verify.]",
        "",
        "INTERNSHIP / EXPERIENCE",
        sections["experience"] or "[Add internships, part-time work, volunteering or relevant campus roles, if any.]",
        "",
        "CERTIFICATIONS",
        sections["certifications"] or "[Add completed, verifiable courses or certifications, if any.]",
    ])
    for name, heading in [("achievements", "ACHIEVEMENTS"), ("other", "OTHER ORIGINAL CONTENT TO REVIEW")]:
        if sections.get(name):
            blocks.extend(["", heading, sections[name]])
    blocks.extend([
        "",
        "Before using this draft: replace every bracketed instruction, verify each fact, and remove any section that does not apply.",
        "",
        "ORIGINAL RESUME TEXT - KEEP AND REVIEW",
        text,
    ])
    return "\n".join(blocks).strip()


def role_learning_plan(role: str) -> tuple[str, list[str], list[tuple[str, str]]]:
    name = role.casefold()
    if any(term in name for term in ["data", "analytics", "business analyst", "machine learning", "ai"]):
        family = "Data and analytics"
        topics = ["spreadsheets", "SQL", "Python basics", "statistics", "dashboard storytelling"]
        tasks = [
            ("Weeks 1-2 · foundations", "Refresh spreadsheets, basic statistics and clear chart reading."),
            ("Weeks 3-5 · guided learning", "Study SQL and Python basics; practise with small exercises."),
            ("Weeks 6-8 · proof of skill", "Build one data project with a question, cleaned data, a chart and a short conclusion."),
            ("Weeks 9-10 · portfolio", "Write a short project README and add accurate project bullets to your resume."),
            ("Weeks 11-12 · applications", "Practise explaining your decisions and apply to internships or graduate roles that fit your experience."),
        ]
    elif any(term in name for term in ["software", "developer", "engineer", "cloud", "devops", "cyber", "network", "it support"]):
        family = "Software and technology"
        topics = ["programming fundamentals", "data structures", "Git", "APIs", "testing and debugging"]
        tasks = [
            ("Weeks 1-2 · foundations", "Choose one main programming language and practise core concepts."),
            ("Weeks 3-5 · guided learning", "Study data structures, Git and basic testing."),
            ("Weeks 6-8 · proof of skill", "Build one small working app or tool and document your own contribution."),
            ("Weeks 9-10 · portfolio", "Add setup instructions, screenshots and a clear project summary."),
            ("Weeks 11-12 · applications", "Practise explaining trade-offs and solving entry-level coding problems."),
        ]
    elif any(term in name for term in ["finance", "account", "credit", "risk", "investment", "bank", "underwriter"]):
        family = "Finance and business"
        topics = ["spreadsheet analysis", "accounting or finance fundamentals", "business writing", "SQL basics", "financial modelling"]
        tasks = [
            ("Weeks 1-2 · foundations", "Review accounting, finance or business concepts connected to the role."),
            ("Weeks 3-5 · guided learning", "Practise spreadsheets, clear business writing and basic data handling."),
            ("Weeks 6-8 · proof of skill", "Create a small business analysis using public data and label your assumptions."),
            ("Weeks 9-10 · portfolio", "Explain calculations, assumptions and limits in a one-page summary."),
            ("Weeks 11-12 · applications", "Practise role-specific questions and compare employer requirements."),
        ]
    elif any(term in name for term in ["marketing", "sales", "brand", "content", "media", "communication"]):
        family = "Marketing and communication"
        topics = ["audience research", "writing", "spreadsheet analysis", "digital analytics", "portfolio storytelling"]
        tasks = [
            ("Weeks 1-2 · foundations", "Learn audience, channel and measurement basics."),
            ("Weeks 3-5 · guided learning", "Practise writing, content planning and simple campaign analysis."),
            ("Weeks 6-8 · proof of skill", "Build a sample campaign or portfolio and label it as a student project."),
            ("Weeks 9-10 · portfolio", "Show your brief, choices, sample work and how you would measure results."),
            ("Weeks 11-12 · applications", "Practise presenting ideas and explaining the evidence behind them."),
        ]
    else:
        family = "Role-focused graduate preparation"
        topics = ["role-specific fundamentals", "spreadsheets and data literacy", "communication", "project planning", "portfolio evidence"]
        tasks = [
            ("Weeks 1-2 · foundations", "Break the target role into tasks and learn its common terms."),
            ("Weeks 3-5 · guided learning", "Choose a beginner course connected to one important role task."),
            ("Weeks 6-8 · proof of skill", "Complete a small project, case study or practical exercise."),
            ("Weeks 9-10 · portfolio", "Describe your decisions, tools and verified result in your resume."),
            ("Weeks 11-12 · applications", "Practise interviews and apply to internships or graduate roles that match your experience."),
        ]
    return family, topics, tasks


def career_bot_answer(question: str, role: str, cgpa_text: str, resume_loaded: bool) -> tuple[str, list[tuple[str, str]]]:
    q = question.casefold()
    links: list[tuple[str, str]] = []
    if any(word in q for word in ["resume", "cv", "ats", "curriculum vitae"]):
        answer = (
            f"For a {role} application, keep your resume easy to scan: put relevant projects and verified skills near the top, "
            "use clear section headings, and tailor wording to each real job description. Add a missing keyword only if it describes real experience. "
            + ("Your uploaded resume is available in Resume Coach." if resume_loaded else "Upload a resume in Resume Coach for a checklist.")
        )
        links = [("National Career Service", "https://www.ncs.gov.in/")]
    elif any(word in q for word in ["cgpa", "gpa", "marks", "grade"]):
        answer = (
            (f"Your profile shows {cgpa_text}. " if cgpa_text else "")
            + "CGPA may matter for some roles or courses, but cut-offs vary by institution and employer. Check the exact current rule, "
            "and show projects, skills and experience alongside grades."
        )
        links = [("National Career Service", "https://www.ncs.gov.in/")]
    elif any(word in q for word in ["course", "learn", "study", "certification"]):
        family, topics, _ = role_learning_plan(role)
        answer = f"For {role} ({family}), useful areas to explore include: {', '.join(topics)}. Check the course dates, cost and certificate rules before enrolling."
        links = [("Search SWAYAM courses", "https://swayam.gov.in/search_courses"), ("Search NPTEL courses", "https://nptel.ac.in/courses")]
    elif any(word in q for word in ["internship", "job", "vacancy", "apply", "search"]):
        answer = "Start with official job boards, your college placement cell and employer career pages. Check the employer before sharing personal information; do not pay a recruiter to apply."
        links = [("National Career Service - India", "https://www.ncs.gov.in/")]
    elif any(word in q for word in ["roadmap", "plan", "prepare", "career"]):
        family, topics, _ = role_learning_plan(role)
        answer = f"For {role}, a useful first step is {topics[0]}. Open Course Roadmap for a 12-week plan for {family.lower()}."
        links = [("SWAYAM course search", "https://swayam.gov.in/search_courses"), ("NCS career services", "https://www.ncs.gov.in/")]
    else:
        answer = "I can help with resumes, CGPA, course search, internships and role-based roadmaps. For other topics, search the exact question and verify details with the institution or employer."
        links = [("National Career Service", "https://www.ncs.gov.in/"), ("SWAYAM courses", "https://swayam.gov.in/search_courses")]
    return answer, links


def feed_setup_text() -> str:
    return (
        "Add an authorized normalized CSV feed in .streamlit/secrets.toml under [jobs] as csv_url = "
        '"https://your-approved-feed.csv". If needed, add api_token = "YOUR_TOKEN" there. '
        "The CSV must include Year, Sector, Job_Role, Hiring_Count and Location."
    )


st.sidebar.markdown("## GradPath")
st.sidebar.caption("Undergraduate resume, course and career planning")
if st.sidebar.button("Refresh trend feed now", width="stretch", key="refresh_market"):
    fetch_daily_feed.clear()
    st.rerun()

market, market_source, fetched_at, feed_error = load_market_data()

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Undergraduate career launchpad</div>
      <h1>GradPath</h1>
      <p>Turn your resume, CGPA and goals into a practical plan for courses, projects and graduate opportunities.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if market.empty:
    st.error("No usable job-trend data is available. Add a valid historical CSV or an authorized daily feed.")
    st.stop()

if market_source == "Authorized daily feed":
    st.sidebar.success(f"Trend feed fetched: {fetched_at}")
    st.sidebar.caption("A successful feed response is cached for up to 24 hours.")
elif feed_error:
    st.sidebar.warning("Live feed unavailable; showing historical data.")
    st.sidebar.caption(feed_error)
    st.sidebar.caption(feed_setup_text())
else:
    st.sidebar.info("Historical sample data only — daily feed not configured.")
    st.sidebar.caption(feed_setup_text())

years = sorted(market["Year"].dropna().astype(int).unique().tolist())
sectors = sorted(market["Sector"].dropna().astype(str).unique().tolist())
roles = sorted(market["Job_Role"].dropna().astype(str).unique().tolist())
sources = sorted(market["Source"].dropna().astype(str).unique().tolist()) if "Source" in market else []

market_tab, resume_tab, roadmap_tab, chat_tab, about_tab = st.tabs(
    ["📈 Market trends", "📄 Resume Coach", "🎓 Course Roadmap", "💬 Career Help Chat", "⚙️ Data & privacy"]
)

with market_tab:
    st.subheader("Explore job-market records")
    if market_source != "Authorized daily feed":
        st.warning("These are historical sample records, not today's live job market. Configure an authorized daily feed before treating the charts as current.")
    else:
        st.success(f"Feed retrieved {fetched_at}. Check the provider's publication date to see how recent its records are.")
    c1, c2, c3 = st.columns(3)
    selected_years = c1.multiselect("Year", years, default=years, key="market_years")
    selected_sectors = c2.multiselect("Work area", sectors, default=sectors, key="market_sectors")
    selected_sources = c3.multiselect("Source", sources, default=sources, key="market_sources") if sources else []
    filtered = market[
        market["Year"].isin(selected_years)
        & market["Sector"].isin(selected_sectors)
        & (market["Source"].isin(selected_sources) if sources else True)
    ].copy()
    if filtered.empty:
        st.info("No records match those filters. Select at least one year and work area.")
    else:
        top_sector = filtered.groupby("Sector")["Hiring_Count"].mean().idxmax()
        growth = filtered["Hiring_Growth_%"].mean()
        median_salary = filtered["Average_Salary"].median()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Records", f"{len(filtered):,}")
        k2.metric("Highest average work area", str(top_sector))
        k3.metric("Mean reported growth", f"{growth:+.1f}%" if pd.notna(growth) else "—")
        k4.metric("Median salary value", f"{median_salary:,.1f}" if pd.notna(median_salary) else "—")
        st.caption("Hiring figures and salary units follow the source records; they are not guaranteed job totals or salary offers.")
        left, right = st.columns(2)
        history = filtered.groupby(["Year", "Sector"], as_index=False).agg(Reported_Hiring=("Hiring_Count", "mean"))
        top_sectors = filtered.groupby("Sector")["Hiring_Count"].mean().nlargest(6).index.tolist()
        fig = px.line(history[history["Sector"].isin(top_sectors)], x="Year", y="Reported_Hiring", color="Sector", markers=True,
                      color_discrete_sequence=COLORS, labels={"Reported_Hiring": "Average hiring figure", "Year": "Year"})
        fig.update_layout(template="plotly_white", height=380, hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10))
        left.plotly_chart(fig, width="stretch", config={"displaylogo": False})
        left.caption("Recorded trend for up to six work areas. Missing years mean the source has no record for that year.")
        sector_data = filtered.groupby("Sector", as_index=False).agg(Reported_Hiring=("Hiring_Count", "mean")).nlargest(10, "Reported_Hiring").sort_values("Reported_Hiring")
        fig = px.bar(sector_data, x="Reported_Hiring", y="Sector", orientation="h", text_auto=".3s",
                     color="Reported_Hiring", color_continuous_scale=["#B7D8FF", BLUE],
                     labels={"Reported_Hiring": "Average hiring figure", "Sector": "Work area"})
        fig.update_layout(template="plotly_white", height=380, coloraxis_showscale=False, margin=dict(l=10, r=10, t=20, b=10))
        right.plotly_chart(fig, width="stretch", config={"displaylogo": False})
        right.caption("Top ten work areas in the selected records.")
        left, right = st.columns(2)
        role_data = filtered.groupby("Job_Role", as_index=False).agg(Reported_Hiring=("Hiring_Count", "mean")).nlargest(10, "Reported_Hiring").sort_values("Reported_Hiring")
        fig = px.bar(role_data, x="Reported_Hiring", y="Job_Role", orientation="h", text_auto=".3s",
                     color="Reported_Hiring", color_continuous_scale=["#CDE6FF", BLUE],
                     labels={"Reported_Hiring": "Average hiring figure", "Job_Role": "Job title"})
        fig.update_layout(template="plotly_white", height=420, coloraxis_showscale=False, margin=dict(l=10, r=10, t=20, b=10))
        left.plotly_chart(fig, width="stretch", config={"displaylogo": False})
        salary = filtered.groupby("Sector", as_index=False).agg(Median_Salary=("Average_Salary", "median")).dropna().nlargest(10, "Median_Salary").sort_values("Median_Salary")
        if not salary.empty:
            fig = px.bar(salary, x="Median_Salary", y="Sector", orientation="h", text_auto=".2f",
                         color="Median_Salary", color_continuous_scale=["#B7F0E8", TEAL],
                         labels={"Median_Salary": "Median salary value", "Sector": "Work area"})
            fig.update_layout(template="plotly_white", height=420, coloraxis_showscale=False, margin=dict(l=10, r=10, t=20, b=10))
            right.plotly_chart(fig, width="stretch", config={"displaylogo": False})
        if "Demand_Trend" in filtered:
            trend = filtered.groupby("Demand_Trend", as_index=False).size().rename(columns={"size": "Records"})
            fig = px.bar(trend, x="Demand_Trend", y="Records", color="Demand_Trend", color_discrete_sequence=COLORS,
                         labels={"Demand_Trend": "Source trend label", "Records": "Number of records"})
            fig.update_layout(template="plotly_white", height=300, showlegend=False, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
        with st.expander("Experimental machine-learning trend estimate"):
            st.write("A simple linear model extends past average hiring figures. Use it to explore a possible direction, not as a promise about future vacancies.")
            if LinearRegression is None:
                st.info("Install project packages to enable the trend model.")
            else:
                horizon = st.slider("Years to sketch ahead", 1, 3, 2, key="market_forecast_horizon")
                forecast_choices = filtered.groupby("Sector")["Hiring_Count"].mean().nlargest(5).index.tolist()
                chosen = st.multiselect("Work areas to sketch", sectors, default=forecast_choices, key="market_forecast_sectors")
                historic = filtered[filtered["Sector"].isin(chosen)].groupby(["Year", "Sector"], as_index=False).agg(
                    Reported_Hiring=("Hiring_Count", "mean")
                )
                if not historic.empty:
                    historic["Line"] = "Recorded data"
                    estimates = []
                    skipped = []
                    for sector in chosen:
                        series = historic[historic["Sector"] == sector].dropna(subset=["Year", "Reported_Hiring"]).sort_values("Year")
                        if series["Year"].nunique() < 3:
                            skipped.append(sector)
                            continue
                        model = LinearRegression().fit(series[["Year"]], series["Reported_Hiring"])
                        future_years = list(range(int(series["Year"].max()) + 1, int(series["Year"].max()) + horizon + 1))
                        values = model.predict(pd.DataFrame({"Year": future_years}))
                        estimates.extend(
                            {"Year": year, "Sector": sector, "Reported_Hiring": max(0, float(value)), "Line": "Model estimate"}
                            for year, value in zip(future_years, values)
                        )
                    combined = pd.concat([historic, pd.DataFrame(estimates)], ignore_index=True)
                    fig = px.line(combined, x="Year", y="Reported_Hiring", color="Sector", line_dash="Line", markers=True,
                                  color_discrete_sequence=COLORS,
                                  labels={"Year": "Year", "Reported_Hiring": "Average hiring figure", "Line": "Recorded or estimated"})
                    fig.update_layout(template="plotly_white", height=390, hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10))
                    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
                    if skipped:
                        st.caption("Need at least three different years for a trend estimate: " + ", ".join(skipped))
                    st.caption("The estimate uses only the currently selected records. Uneven years or sources can make it unreliable.")
                else:
                    st.info("Select at least one work area with records.")

with resume_tab:
    st.subheader("Resume Coach for undergraduates")
    st.write("Upload a resume, choose a target role, and get a structure checklist and preparation tips. The upload is processed in this session; this app code does not write it to disk.")
    st.caption("Avoid uploading a resume on a shared computer. A scanned image-only PDF may need OCR before text can be read.")
    if st.button("Clear resume from this session", key="clear_resume"):
        for key in ["resume_text", "resume_digest", "resume_error", "resume_name", "resume_file", "verified_cgpa", "verified_cgpa_scale"]:
            st.session_state.pop(key, None)
        st.rerun()
    uploaded = st.file_uploader("Upload PDF, DOCX or TXT", type=["pdf", "docx", "txt"], max_upload_size=10, key="resume_file")
    if uploaded is None:
        st.info("Upload a resume to check its sections, find a CGPA if the document contains one, and get role-specific tips.")
    else:
        file_bytes = uploaded.getvalue()
        digest = hashlib.sha256(file_bytes).hexdigest()
        if st.session_state.get("resume_digest") != digest:
            try:
                extracted = extract_resume_text(uploaded.name, file_bytes)
                if len(extracted.strip()) < 40:
                    raise ValueError("I could not find readable text. If this is a scanned PDF, create a text-based copy or run OCR first.")
                st.session_state["resume_text"] = extracted
                st.session_state["resume_digest"] = digest
                st.session_state["resume_name"] = uploaded.name
                st.session_state.pop("resume_error", None)
            except Exception as error:
                st.session_state["resume_error"] = str(error)
        if st.session_state.get("resume_error"):
            st.error(st.session_state["resume_error"])
        elif st.session_state.get("resume_text"):
            resume_text = st.session_state["resume_text"]
            sections = split_resume_sections(resume_text)
            skills = detect_skills(resume_text)
            detected_cgpa, detected_scale = detect_cgpa(resume_text)
            contacts = extract_contact_lines(resume_text)
            default_role = next((role for role in roles if role.casefold() in resume_text.casefold()), roles[0] if roles else "Graduate role")
            target_role = st.selectbox("Role you want to apply for", roles or ["Graduate role"],
                                       index=roles.index(default_role) if default_role in roles else 0,
                                       key="resume_target_role")
            job_description = st.text_area("Optional: paste a job description to compare it with your resume", height=125, key="resume_job_description")
            detected_scale = detected_scale if detected_scale in (4.0, 10.0, 100.0) else 10.0
            formats = {100.0: "Percentage / 100", 10.0: "CGPA / 10", 4.0: "GPA / 4"}
            scales = [100.0, 10.0, 4.0]
            scale = st.selectbox("Marks format", scales, index=scales.index(detected_scale),
                                 format_func=lambda value: formats[value], key=f"resume_scale_{digest[:10]}")
            initial_mark = detected_cgpa if detected_scale == scale else None
            mark = st.number_input(
                "Overall CGPA / marks (edit if the resume value is incorrect)",
                min_value=0.0, max_value=float(scale), value=initial_mark,
                step=1.0 if scale == 100 else 0.1, format="%.2f",
                key=f"resume_mark_{digest[:10]}_{scale:g}",
            )
            st.session_state["verified_cgpa"] = float(mark) if mark is not None else None
            st.session_state["verified_cgpa_scale"] = float(scale)
            present, missing = compare_resume_to_job(resume_text, job_description) if job_description.strip() else ([], [])
            checklist = {
                "Contact details": bool(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", resume_text)),
                "Education section": bool(sections["education"]),
                "Projects or practical work": bool(sections["projects"] or sections["experience"]),
                "Skills section": bool(sections["skills"] or skills),
                "Clear summary": bool(sections["summary"]),
                "Certifications or achievements": bool(sections["certifications"] or sections["achievements"]),
            }
            score = round(100 * sum(checklist.values()) / len(checklist))
            m1, m2, m3 = st.columns(3)
            m1.metric("Resume structure checklist", f"{score}/100", help="Completeness check only, not an interview or hiring probability.")
            m2.metric("Recognized skills", str(len(skills)))
            m3.metric("CGPA / marks", f"{mark:g} / {scale:g}" if mark is not None else "Not found or entered")
            st.caption("This score checks whether common sections appear. It does not predict ATS results, interviews or job offers.")
            left, right = st.columns(2)
            with left:
                st.markdown("#### Your resume checklist")
                for label, present_section in checklist.items():
                    st.write(("✅ " if present_section else "⬜ ") + label)
            with right:
                st.markdown("#### Suggested resume version")
                st.write("Use a simple, one-column, editable resume tailored to this role. Put relevant projects and verified skills near the top; keep education and CGPA accurate.")
                st.write(f"**Target role:** {target_role}")
                st.write("**Skills detected:** " + (", ".join(skills) if skills else "No built-in skill keywords detected; check manually."))
            if job_description.strip():
                st.markdown("#### Job-description word comparison")
                st.caption("Words found in both: " + (", ".join(present[:15]) or "No overlap detected"))
                st.caption("Words in the job description not found in the resume: " + (", ".join(missing[:15]) or "None detected"))
                st.info("Only add a missing word if it truthfully describes your skills or experience.")
            family, topics, _ = role_learning_plan(target_role)
            st.markdown("#### How to prepare")
            st.write(f"For {family}, explore: {', '.join(topics)}.")
            st.write("Strengthen project bullets with your actual task, tools you used, and results you can support with evidence.")
            draft = build_resume_draft(resume_text, sections, skills, target_role, mark, float(scale), contacts)
            st.download_button(
                "Download ATS-friendly editable resume outline (.txt)",
                data=draft.encode("utf-8"),
                file_name="resume_outline_for_editing.txt",
                mime="text/plain",
                width="stretch",
            )
            st.caption("The outline preserves your original text and adds bracketed prompts. Review every fact and remove prompts before applying.")
            with st.expander("Review extracted resume text"):
                st.text_area("Extracted text", resume_text, height=280, disabled=True, key=f"resume_preview_{digest[:10]}")

with roadmap_tab:
    st.subheader("Course and career roadmap")
    st.write("Choose a graduate role to build a practical learning and project plan. CGPA is context; it is not used as a universal course gate.")
    target = st.selectbox("Target role", roles or ["Graduate role"], key="roadmap_target_role")
    family, topics, milestones = role_learning_plan(target)
    resume_text = st.session_state.get("resume_text", "")
    recognized = detect_skills(resume_text) if resume_text else []
    st.markdown(f"### Suggested learning area: {family}")
    st.write("**Topics to explore:** " + ", ".join(topics))
    if resume_text:
        st.caption("Recognized skills in your resume: " + (", ".join(recognized) if recognized else "No built-in keywords detected; review manually."))
    resume_cgpa, cgpa_scale = detect_cgpa(resume_text) if resume_text else (None, None)
    profile_mark = st.session_state.get("verified_cgpa", resume_cgpa)
    profile_scale = st.session_state.get("verified_cgpa_scale", cgpa_scale)
    if profile_mark is not None and profile_scale:
        normalized_mark = 100 * float(profile_mark) / float(profile_scale)
        if normalized_mark < 60:
            course_level = "Build the foundations first"
            course_advice = "Start with beginner-friendly lessons, short practice exercises and one guided project before moving to advanced certificates."
        elif normalized_mark < 80:
            course_level = "Mix core learning with applied practice"
            course_advice = "Choose an intermediate course for the role, practise each topic, and use a project to find areas that need more study."
        else:
            course_level = "Add a focused specialization"
            course_advice = "Consider an advanced or specialization course for the role, while building a substantial project that shows how you use the ideas."
        st.info(f"Verified profile marks: {float(profile_mark):g}/{float(profile_scale):g}. Suggested study approach: **{course_level}**. {course_advice}")
        st.caption("Marks help choose a starting pace; they do not prove skill or determine eligibility. Check each course's entry rules and use projects to assess your current level.")
    else:
        st.info("Upload your resume in Resume Coach to detect CGPA, or use the roadmap without it. Course topics are chosen from the target role.")
    for milestone, details in milestones:
        st.markdown(f"**{milestone}** — {details}")
    search_terms = quote_plus(" ".join(topics))
    c1, c2 = st.columns(2)
    c1.link_button("Search these topics on SWAYAM", "https://swayam.gov.in/search_courses?searchText=" + search_terms, width="stretch")
    c2.link_button("Explore NPTEL courses", "https://nptel.ac.in/courses", width="stretch")
    st.caption("Check the course provider for current dates, fees, entry rules and certificate conditions.")

with chat_tab:
    st.subheader("Career Help Chat")
    st.write("Ask about resumes, CGPA, courses, internships or how to find opportunities. This is a topic-based guide with official links, not a general-purpose AI model.")
    current_resume = st.session_state.get("resume_text", "")
    detected, maximum = detect_cgpa(current_resume) if current_resume else (None, None)
    cgpa_context = f"{detected:g}/{maximum:g}" if detected is not None else ""
    if "career_chat_history" not in st.session_state:
        st.session_state["career_chat_history"] = []
    for message in st.session_state["career_chat_history"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            for label, url in message.get("links", []):
                st.markdown(f"[{label}]({url})")
    question = st.chat_input("Ask a career or resume question")
    if question:
        st.session_state["career_chat_history"].append({"role": "user", "content": question})
        selected_role = st.session_state.get("roadmap_target_role", roles[0] if roles else "graduate role")
        answer, links = career_bot_answer(question, selected_role, cgpa_context, bool(current_resume))
        st.session_state["career_chat_history"].append({"role": "assistant", "content": answer, "links": links})
        st.rerun()
    st.markdown("**Helpful places to search**")
    st.markdown("- [National Career Service - jobs, internships and career services](https://www.ncs.gov.in/)")
    st.markdown("- [SWAYAM - search courses](https://swayam.gov.in/search_courses)")
    st.markdown("- [NPTEL courses](https://nptel.ac.in/courses)")
    topic = st.text_input("Need another search? Enter a topic", key="career_search")
    if topic.strip():
        st.link_button("Search the web for this topic", "https://www.google.com/search?q=" + quote_plus(topic.strip()))

with about_tab:
    st.subheader("Data freshness and privacy")
    st.markdown(f"**Trend source:** {market_source}  \n**Last retrieved:** {fetched_at}")
    if market_source != "Authorized daily feed":
        st.warning("The existing CSV is historical sample data. The dashboard cannot make it current on its own.")
        st.code(feed_setup_text(), language="text")
        st.write("The authorized provider must publish a normalized CSV containing Year, Sector, Job_Role, Hiring_Count and Location. The app checks it when opened and caches a successful fetch for up to 24 hours. It does not scrape job websites.")
    else:
        st.write("The authorized feed is fetched at most once per 24 hours while the dashboard is being used. The provider's publication date may be older than the retrieval time.")
    if feed_error:
        st.error("Daily feed error: " + feed_error)
    st.markdown("#### Resume handling")
    st.write("Resume text is extracted in the app process for this session. The app code does not save the uploaded file or extracted text to disk. Clearing the upload or ending the session removes the session data. For a public deployment, tell students where the app is hosted and review its privacy setup before accepting resumes.")
    st.markdown("#### Project data limits")
    st.write("The historical file includes hiring figures, job roles, sectors, locations, sources, salary values and placement values. It does not include verified skill requirements, qualification rules or individual student outcomes. Resume checks and course roadmaps are explainable guidance, not ML predictions of hiring success.")

st.divider()
st.caption("GradPath · Undergraduate resume and career planning · Verify course rules and job details with their original provider.")
