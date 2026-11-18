"""Undergraduate career dashboard with resume coaching and daily-feed support."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from google import genai
except ImportError:
    genai = None

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
SNAPSHOT_DB = APP_DIR / "gradpath_market_snapshots.sqlite3"
HOPIN_REPORT_URL = "https://hopinjobs.com/reports/fresher-hiring-india.json"
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

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .stApp {
        background: var(--background-color);
        color: var(--text-color);
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    /* Keep the branded navy sidebar in every Streamlit theme. */
    [data-testid="stSidebar"] {
        background: #13223D;
    }

    [data-testid="stSidebar"] * {
        color: #EDF3FC;
    }

    [data-testid="stSidebar"] [data-baseweb="tag"] {
        background: #24436D;
    }

    /* Ensure the sidebar action button always has readable contrast. */
    [data-testid="stSidebar"] .stButton > button {
        background-color: #24436D !important;
        color: #FFFFFF !important;
        border: 1px solid #45658F !important;
    }

    [data-testid="stSidebar"] .stButton > button p {
        color: #FFFFFF !important;
    }

    [data-testid="stSidebar"] .stButton > button:hover {
        background-color: #315783 !important;
        border-color: #6B8DB8 !important;
    }

    .hero {
        padding: 1.65rem 1.9rem;
        border-radius: 20px;
        color: white;
        background: linear-gradient(115deg, #13223D 0%, #1C4774 58%, #11877F 100%);
        margin: .2rem 0 1.1rem;
        box-shadow: 0 12px 28px rgba(19,34,61,.15);
    }

    .hero h1 {
        font-family: 'Manrope', sans-serif;
        font-size: 2rem;
        margin: 0 0 .35rem;
        color: white;
    }

    .hero p {
        color: #DCEBFA;
        font-size: 1rem;
        margin: 0;
    }

    .eyebrow {
        text-transform: uppercase;
        letter-spacing: .13em;
        font-size: .72rem;
        color: #98F0DF;
        font-weight: 700;
        margin-bottom: .45rem;
    }

    div[data-testid="stMetric"] {
        background: var(--secondary-background-color);
        color: var(--text-color);
        border: 1px solid var(--secondary-background-color);
        padding: .95rem 1.05rem;
        border-radius: 15px;
        box-shadow: 0 4px 14px rgba(19,34,61,.04);
    }

    div[data-testid="stMetricLabel"],
    div[data-testid="stMetricValue"] {
        color: var(--text-color);
    }

    div[data-testid="stMetricValue"] {
        font-family: 'Manrope', sans-serif;
    }

    h1, h2, h3, h4, p, label,
    [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"] {
        color: var(--text-color);
    }

    h1, h2, h3 {
        font-family: 'Manrope', sans-serif !important;
    }

    button[data-baseweb="tab"] {
        color: var(--text-color);
    }

    [data-testid="stWidgetLabel"],
    [data-testid="stSelectbox"],
    [data-testid="stMultiSelect"],
    [data-testid="stTextInput"],
    [data-testid="stNumberInput"],
    [data-testid="stTextArea"] {
        color: var(--text-color);
    }

    .hint {
        color: var(--text-color);
        margin-top: -.55rem;
        margin-bottom: 1rem;
    }
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



@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def fetch_hopin_report() -> dict:
    """Fetch Hopin's public India fresher hiring report (refreshed by its publisher daily)."""
    request = Request(HOPIN_REPORT_URL, headers={"Accept": "application/json", "User-Agent": "GradPath/1.0"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("totals"), dict):
        raise ValueError("The Hopin report returned an unexpected data format.")
    required = {"liveListings", "newLast7Days", "internshipSharePct", "remoteSharePct", "medianPostingAgeDays"}
    missing = required.difference(payload["totals"])
    if missing:
        raise ValueError("The Hopin report is missing: " + ", ".join(sorted(missing)))
    if not payload.get("updatedAt"):
        raise ValueError("The Hopin report did not include its publication date.")
    return payload


def save_hopin_snapshot(report: dict) -> None:
    """Keep one local historical observation per publisher report date."""
    totals = report["totals"]
    published_at = str(report["updatedAt"])
    try:
        # The report may be republished more than once in a day. Store one
        # observation per calendar date so the model counts distinct days.
        parsed = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        snapshot_key = parsed.date().isoformat()
    except ValueError:
        snapshot_key = published_at[:10]
    with sqlite3.connect(SNAPSHOT_DB) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS daily_snapshots (published_at TEXT PRIMARY KEY, live_listings INTEGER, new_last_7_days INTEGER, internship_share REAL, remote_share REAL, median_posting_age REAL)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO daily_snapshots VALUES (?, ?, ?, ?, ?, ?)",
            (snapshot_key, int(totals["liveListings"]), int(totals["newLast7Days"]),
             float(totals["internshipSharePct"]), float(totals["remoteSharePct"]),
             float(totals["medianPostingAgeDays"])),
        )


def load_hopin_snapshots() -> pd.DataFrame:
    if not SNAPSHOT_DB.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(SNAPSHOT_DB) as connection:
            frame = pd.read_sql_query("SELECT * FROM daily_snapshots ORDER BY published_at", connection)
        if not frame.empty:
            frame["published_at"] = pd.to_datetime(frame["published_at"], utc=True, errors="coerce")
            frame["snapshot_date"] = frame["published_at"].dt.date.astype(str)
        return frame
    except Exception:
        return pd.DataFrame()

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
    """Return an explainable, career-family-specific study plan for the chosen goal."""
    name = role.casefold()
    if any(term in name for term in ["data scientist", "machine learning", "artificial intelligence", "ai engineer", "ai/ml", "ml engineer", "machine-learning"]):
        family = "Data science and AI"
        topics = ["Python programming and OOP", "linear algebra, calculus basics, probability and statistics", "NumPy and Pandas", "data cleaning and exploratory data analysis", "supervised and unsupervised machine learning", "feature engineering and model evaluation", "deep learning and neural networks", "Git, APIs and model deployment"]
        tasks = [
            ("Foundations", "Strengthen Python programming, functions, OOP, Git and the mathematics used in ML: vectors, matrices, probability, statistics and basic calculus. Practise with small datasets."),
            ("Core learning", "Use NumPy and Pandas for data handling; learn data cleaning, exploratory analysis, visualisation, SQL, feature engineering and train/validation/test splits."),
            ("Applied practice", "Study regression, classification, clustering, decision trees and ensemble methods. Practise cross-validation, metrics, overfitting, regularisation and data-leakage prevention."),
            ("Advanced practice and portfolio", "Learn neural-network fundamentals and an introductory deep-learning framework. Build an end-to-end project with a reproducible pipeline, model comparison and clear limitations; deploy a small demo if time allows."),
            ("Career preparation", "Prepare Python, SQL, statistics and ML-concept interviews. Explain model choices and evaluation results, publish documented projects and apply for suitable internships or graduate roles."),
        ]
    elif any(term in name for term in ["data analyst", "business analyst", "business intelligence", "analytics", "reporting analyst"]):
        family = "Data and business analytics"
        topics = ["Excel or spreadsheets", "SQL", "statistics", "Power BI or Tableau", "Python basics", "data storytelling", "business communication"]
        tasks = [
            ("Foundations", "Refresh spreadsheets, percentages, averages, charts and basic statistical reasoning."),
            ("Core learning", "Practise SQL queries, joins, grouping and data cleaning. Learn one dashboard tool such as Power BI or Tableau."),
            ("Applied practice", "Analyse a public dataset, define useful metrics and explain what the numbers do and do not show."),
            ("Portfolio", "Create a dashboard and a short business case study. Include your question, method, visuals and conclusions."),
            ("Career preparation", "Practise SQL, Excel, dashboard and business-case questions. Tailor your resume to entry-level analyst roles."),
        ]
    elif any(term in name for term in ["software", "developer", "programmer", "web engineer", "application engineer"]):
        family = "Software development"
        topics = ["one programming language", "problem solving", "data structures", "Git and GitHub", "APIs", "databases", "testing"]
        tasks = [
            ("Foundations", "Choose one main language and practise variables, functions, loops, collections and debugging."),
            ("Core learning", "Study data structures, algorithms, object-oriented basics, Git and SQL fundamentals."),
            ("Applied practice", "Build a small application with a clear user need. Add input validation, error handling and tests."),
            ("Portfolio", "Publish a second project or improve the first. Add a README, screenshots, setup steps and a clear account of your contribution."),
            ("Career preparation", "Practise coding problems, explain your projects and prepare basic software design and behavioural questions."),
        ]
    elif any(term in name for term in ["cyber", "security"]):
        family = "Cybersecurity"
        topics = ["networking", "Linux", "operating systems", "security fundamentals", "Python or scripting", "logs and incident response"]
        tasks = [
            ("Foundations", "Learn networking, operating-system basics, Linux commands and safe computing practices."),
            ("Core learning", "Study authentication, access control, common vulnerabilities, security monitoring and basic scripting."),
            ("Applied practice", "Use legal training labs and intentionally vulnerable practice environments; document defensive findings."),
            ("Portfolio", "Create a security checklist, lab write-up or home-lab project. Do not test systems without written permission."),
            ("Career preparation", "Review entry-level SOC and security analyst requirements, practise incident scenarios and prepare a concise lab portfolio."),
        ]
    elif any(term in name for term in ["cloud", "devops", "site reliability"]):
        family = "Cloud and DevOps"
        topics = ["Linux", "networking", "Git", "scripting", "cloud fundamentals", "containers", "CI/CD and monitoring"]
        tasks = [
            ("Foundations", "Build confidence with Linux, networking, command-line tools and Git."),
            ("Core learning", "Learn scripting, cloud concepts, identity and access management, and basic deployment workflows."),
            ("Applied practice", "Containerise a small application and practise a safe CI/CD workflow in a test environment."),
            ("Portfolio", "Deploy a documented demo, diagram the architecture and explain cost, access and security assumptions."),
            ("Career preparation", "Practise troubleshooting, Linux, networking and cloud fundamentals for junior roles."),
        ]
    elif any(term in name for term in ["finance", "account", "credit", "risk", "investment", "bank", "underwriter", "audit"]):
        family = "Finance and business"
        topics = ["accounting or finance fundamentals", "Excel", "financial analysis", "business writing", "SQL basics", "financial modelling"]
        tasks = [
            ("Foundations", "Review accounting, financial statements, percentages and the concepts most relevant to the target role."),
            ("Core learning", "Practise advanced spreadsheets, data checking, business writing and introductory financial analysis."),
            ("Applied practice", "Build a small analysis with clearly stated assumptions and check every calculation."),
            ("Portfolio", "Prepare a concise case study or financial model using public or fictional data, clearly labelled."),
            ("Career preparation", "Practise role-specific questions and verify any employer-specific eligibility or certification rules."),
        ]
    elif any(term in name for term in ["marketing", "sales", "content", "seo", "brand", "media", "social"]):
        family = "Marketing, sales and communication"
        topics = ["audience research", "writing and presentation", "digital analytics", "SEO basics", "campaign measurement", "CRM or spreadsheet skills"]
        tasks = [
            ("Foundations", "Learn audience research, customer journeys, clear writing and basic marketing or sales metrics."),
            ("Core learning", "Practise content planning, digital analytics, SEO fundamentals and spreadsheet reporting."),
            ("Applied practice", "Create a sample campaign, sales analysis or content plan with a defined audience and objective."),
            ("Portfolio", "Show your brief, sample work, reasoning and how you would measure performance. Label sample work honestly."),
            ("Career preparation", "Practise presenting ideas, explaining metrics and tailoring applications to entry-level roles."),
        ]
    elif any(term in name for term in ["design", "ui", "ux", "graphic", "visual"]):
        family = "Design and user experience"
        topics = ["design principles", "Figma or design tools", "user research", "wireframing", "prototyping", "accessibility", "case-study writing"]
        tasks = [
            ("Foundations", "Study layout, typography, colour, hierarchy and basic accessibility principles."),
            ("Core learning", "Practise one design tool and learn user research, wireframes and interactive prototypes."),
            ("Applied practice", "Redesign a small user flow and test it with a few people, recording feedback responsibly."),
            ("Portfolio", "Write a case study showing the problem, research, iterations, trade-offs and final design."),
            ("Career preparation", "Prepare a portfolio walkthrough and explain your decisions, collaboration and accessibility choices."),
        ]
    elif any(term in name for term in ["supply chain", "procurement", "logistics", "operations", "process"]):
        family = "Operations and supply chain"
        topics = ["Excel", "process mapping", "inventory or operations basics", "data analysis", "communication", "continuous improvement"]
        tasks = [
            ("Foundations", "Understand the main process, terms and metrics used in the target operations role."),
            ("Core learning", "Practise spreadsheets, process mapping, basic analysis and clear business communication."),
            ("Applied practice", "Map a sample process, identify a bottleneck and suggest a measurable improvement."),
            ("Portfolio", "Create a short process-improvement case with assumptions, a before/after flow and expected measures."),
            ("Career preparation", "Practise operational scenarios and prepare examples of teamwork, organisation and problem solving."),
        ]
    elif any(term in name for term in ["5g", "telecom", "telecommunication", "wireless", "radio access", "ran engineer"]):
        family = "Telecommunications and 5G engineering"
        topics = ["electrical and communication engineering fundamentals", "signals and systems", "digital communication", "RF and antenna fundamentals", "LTE and 5G NR architecture", "5G radio access network (RAN)", "IP networking", "Python for network automation"]
        tasks = [
            ("Foundations", "Refresh basic electrical and communication engineering, signals, frequency, bandwidth, modulation and the fundamentals of cellular networks. Use your existing programming skills for small calculations where useful."),
            ("Core learning", "Study LTE and 5G NR architecture, network elements, radio access networks, spectrum, numerology, frame structure, handover and the basics of 5G protocols. Learn IP addressing, routing and Linux fundamentals."),
            ("Applied practice", "Use a network simulator or guided lab to explore a small cellular or IP-network scenario. Practise reading simple network diagrams and analysing coverage, capacity and signal-quality concepts. Do not access or modify live telecom infrastructure."),
            ("Portfolio", "Create a documented 5G learning project: explain a use case such as enhanced mobile broadband or IoT, draw a high-level 5G architecture, describe the RAN/core components and include a small Python analysis or simulation with stated assumptions."),
            ("Career preparation", "Compare entry-level RF, RAN, telecom and network-engineering job descriptions. Prepare explanations of LTE versus 5G, 5G architecture, RF basics, IP networking and your project. Seek relevant labs, internships or supervised practical exposure."),
        ]
    elif any(term in name for term in ["engineer", "engineering", "technician", "maintenance", "production", "quality"]):
        family = "Engineering and technical practice"
        topics = ["engineering fundamentals", "technical drawing or domain tools", "measurement and quality", "Excel", "problem solving", "technical reporting"]
        tasks = [
            ("Foundations", "Refresh the core engineering subjects and safety principles connected to the target discipline."),
            ("Core learning", "Practise the tools, calculations, standards and documentation commonly used in that discipline."),
            ("Applied practice", "Complete a lab, simulation, design or process exercise that demonstrates safe practical reasoning."),
            ("Portfolio", "Document one technical project with the objective, method, tools, drawings or results you can verify."),
            ("Career preparation", "Prepare technical explanations, review role requirements and seek relevant supervised experience."),
        ]
    elif any(term in name for term in ["health", "clinical", "medical", "pharmac", "hospital", "research associate"]):
        family = "Healthcare and life sciences"
        topics = ["relevant life-science fundamentals", "documentation", "data accuracy", "research methods", "quality and safety", "professional communication"]
        tasks = [
            ("Foundations", "Refresh the scientific and domain fundamentals required by the target role."),
            ("Core learning", "Study documentation, research methods, quality systems and data accuracy relevant to the role."),
            ("Applied practice", "Complete a supervised or classroom-based case exercise; follow all safety and ethical rules."),
            ("Portfolio", "Prepare a non-confidential case summary or academic project report that demonstrates careful documentation."),
            ("Career preparation", "Check current qualification, registration and experience requirements with official bodies and employers."),
        ]
    elif any(term in name for term in ["hr", "human resource", "recruitment", "talent"]):
        family = "Human resources and people operations"
        topics = ["HR fundamentals", "communication", "Excel", "recruitment process", "employment basics", "data privacy"]
        tasks = [
            ("Foundations", "Learn the employee lifecycle, recruitment terminology and professional communication."),
            ("Core learning", "Practise spreadsheet tracking, interview coordination, documentation and responsible data handling."),
            ("Applied practice", "Design a sample onboarding checklist or structured interview scorecard."),
            ("Portfolio", "Document the sample process and explain fairness, privacy and consistency considerations."),
            ("Career preparation", "Practise HR scenarios and verify local employment-law topics with current official resources."),
        ]
    else:
        family = "Role-focused graduate preparation"
        topics = ["role-specific fundamentals", "Excel or data literacy", "communication", "digital tools used in the role", "practical project work"]
        tasks = [
            ("Foundations", "Break the target role into common tasks and learn its key terms and fundamentals."),
            ("Core learning", "Choose a beginner course and practise one important task connected to the role."),
            ("Applied practice", "Complete a small project, case study or practical exercise related to the target role."),
            ("Portfolio", "Document your process, tools, decisions and verified results in a clear portfolio entry."),
            ("Career preparation", "Review current job descriptions, practise interviews and apply to suitable graduate opportunities."),
        ]
    return family, topics, tasks

def build_duration_roadmap(milestones: list[tuple[str, str]], duration_months: int) -> list[tuple[str, str]]:
    """Spread role-specific stages across the student's chosen duration."""
    total_weeks = max(4, int(duration_months * 4.345))
    stage_names = ["Foundations", "Guided learning", "Practical skill-building", "Portfolio development", "Career preparation"]
    result = []
    boundaries = [round(i * total_weeks / len(milestones)) for i in range(len(milestones) + 1)]
    for index, (_, details) in enumerate(milestones):
        start = boundaries[index] + 1
        end = max(start, boundaries[index + 1])
        result.append((f"Weeks {start}-{end} · {stage_names[index]}", details))
    return result


ROLE_SKILL_GUIDES = {
    "ai/ml": ["Python", "Linear Algebra", "Probability and Statistics", "NumPy", "Pandas", "Scikit-learn", "Machine Learning", "Deep Learning", "Model Evaluation", "SQL", "Git"],
    "ai engineer": ["Python", "Linear Algebra", "Probability and Statistics", "NumPy", "Pandas", "Scikit-learn", "Machine Learning", "Deep Learning", "Model Evaluation", "SQL", "Git"],
    "ml engineer": ["Python", "Linear Algebra", "Probability and Statistics", "NumPy", "Pandas", "Scikit-learn", "Machine Learning", "Deep Learning", "Model Evaluation", "SQL", "Git"],
    "machine learning engineer": ["Python", "Linear Algebra", "Probability and Statistics", "NumPy", "Pandas", "Scikit-learn", "Machine Learning", "Deep Learning", "Model Evaluation", "SQL", "Git"],
    "5g": ["Communication Systems", "Signals and Systems", "Digital Communication", "RF Fundamentals", "Antenna Systems", "LTE", "5G NR", "RAN", "IP Networking", "Python"],
    "telecommunication": ["Communication Systems", "Signals and Systems", "Digital Communication", "RF Fundamentals", "Antenna Systems", "LTE", "5G NR", "RAN", "IP Networking", "Python"],
    "data scientist": ["Python", "SQL", "Statistics", "Pandas", "Machine Learning", "Data Analysis"],
    "machine learning": ["Python", "Statistics", "Pandas", "NumPy", "Machine Learning", "SQL"],
    "data analyst": ["SQL", "Excel", "Statistics", "Power BI", "Python", "Data Analysis"],
    "business analyst": ["Excel", "SQL", "Data Analysis", "Communication", "Project Management", "Power BI"],
    "software": ["Python or Java", "Data Structures", "Git", "APIs", "SQL", "Testing"],
    "developer": ["Python or JavaScript", "Data Structures", "Git", "APIs", "SQL", "Testing"],
    "cyber": ["Networking", "Linux", "Cybersecurity", "Python", "Git", "Communication"],
    "security": ["Networking", "Linux", "Cybersecurity", "Python", "Git", "Communication"],
    "cloud": ["Linux", "Networking", "AWS or Azure", "Docker", "Git", "Python"],
    "devops": ["Linux", "Networking", "Docker", "Git", "Python", "Testing"],
    "finance": ["Excel", "Financial Modeling", "Statistics", "SQL", "Communication", "Data Analysis"],
    "account": ["Excel", "Accounting fundamentals", "Financial Modeling", "Communication", "Data Analysis"],
    "marketing": ["Digital Marketing", "SEO", "Excel", "Communication", "Data Analysis", "Writing"],
    "sales": ["Communication", "Excel", "Data Analysis", "Writing", "CRM fundamentals"],
    "design": ["Figma", "Research", "Communication", "Project Management", "Writing"],
    "supply chain": ["Excel", "Data Analysis", "Project Management", "Communication", "SQL"],
    "operations": ["Excel", "Data Analysis", "Project Management", "Communication", "Statistics"],
    "human resource": ["Communication", "Excel", "Project Management", "Writing", "Data Analysis"],
    "hr": ["Communication", "Excel", "Project Management", "Writing", "Data Analysis"],
    "engineer": ["Technical fundamentals", "Excel", "Problem solving", "Research", "Communication", "Project Management"],
}


def recommended_role_skills(role: str) -> list[str]:
    folded = role.casefold()
    ordered = sorted(ROLE_SKILL_GUIDES.items(), key=lambda item: len(item[0]), reverse=True)
    for keyword, skills in ordered:
        if keyword in folded:
            return skills
    if any(term in folded for term in ["clinical", "medical", "health", "pharma"]):
        return ["Domain fundamentals", "Research", "Documentation", "Data Analysis", "Communication", "Quality and safety"]
    if any(term in folded for term in ["content", "writing", "editor"]):
        return ["Writing", "Research", "Communication", "SEO", "Digital Marketing", "Data Analysis"]
    return ["Role-specific fundamentals", "Communication", "Excel or data literacy", "Practical project work", "Research", "Interview preparation"]


def skill_gap_for_role(role: str, detected_skills: list[str], additional_skills: list[str] | None = None) -> list[str]:
    """Return role skill suggestions not represented in detected/confirmed skills."""
    known = {item.casefold() for item in (detected_skills + (additional_skills or []))}
    gaps = []
    for skill in recommended_role_skills(role):
        terms = [part.strip() for part in re.split(r"\bor\b", skill, flags=re.IGNORECASE)]
        if not any(term.casefold() in known or any(term.casefold() in item for item in known) or any(item in term.casefold() for item in known) for term in terms):
            gaps.append(skill)
    return gaps


def build_personalized_roadmap(
    role: str,
    duration_months: int,
    missing_skills: list[str],
    normalized_cgpa: float | None,
) -> list[tuple[str, str, str]]:
    """Build staged milestones from the role, resume gaps, CGPA band and chosen duration."""
    total_weeks = max(4, round(duration_months * 4.345))
    if normalized_cgpa is None:
        pace = "balanced"
        study_note = "Start with a balanced mix of fundamentals and practice, then adjust based on quiz and project results."
    elif normalized_cgpa < 60:
        pace = "foundation-first"
        study_note = "Use a foundation-first pace: short lessons, regular revision and guided exercises before advanced topics."
    elif normalized_cgpa < 80:
        pace = "balanced"
        study_note = "Use a balanced pace: combine core lessons with weekly practice and one applied project at a time."
    else:
        pace = "specialisation"
        study_note = "You may be ready to add a focused specialization after confirming the fundamentals through practical work."

    skill_text = ", ".join(missing_skills[:4]) if missing_skills else "advanced role-specific practice and stronger evidence for the skills already listed"
    if len(missing_skills) > 4:
        skill_text += f", plus {len(missing_skills) - 4} further area(s)"
    plan = [
        ("Set the baseline", "Review the target role and choose a weekly study routine. " + study_note,
         "A realistic weekly timetable and a checklist of current strengths and gaps."),
        ("Build the core skills", f"Prioritise {skill_text}. Study one topic at a time and practise it with short exercises. Use the course links below to find suitable beginner or intermediate material.",
         "Notes, completed exercises and evidence that you can use the priority tools or concepts."),
        ("Apply what you learn", f"Complete practical exercises connected to {role}. Use public, classroom or self-created data and explain your assumptions.",
         "At least one documented practical exercise or case study."),
        ("Create portfolio proof", "Build one substantial project and, where the chosen duration allows, a second smaller project. Explain the problem, your contribution, tools, decisions and limitations.",
         "A portfolio entry, project README or case study that can be reviewed by a mentor or recruiter."),
        ("Prepare for opportunities", "Update the resume with verified skills and project evidence. Practise role-specific questions, prepare an interview introduction and research internships or graduate openings.",
         "A tailored resume, interview practice notes and a shortlist of suitable opportunities."),
    ]
    stage_names = ["Goal and baseline", "Core learning", "Practical application", "Portfolio development", "Career readiness"]
    # A one-month plan has about four weeks, so combine the first two stages
    # rather than assigning two different milestones to the same week.
    if total_weeks < 5:
        plan = [
            ("Goal and core learning", plan[0][1] + " " + plan[1][1], plan[0][2] + " " + plan[1][2]),
            plan[2], plan[3], plan[4],
        ]
        stage_names = ["Goal and core learning", "Practical application", "Portfolio development", "Career readiness"]
    boundaries = [round(i * total_weeks / len(plan)) for i in range(len(plan) + 1)]
    result = []
    for i, (focus, actions, outcome) in enumerate(plan):
        start_week = boundaries[i] + 1
        end_week = max(start_week, boundaries[i + 1])
        result.append((f"Weeks {start_week}–{end_week} · {stage_names[i]}", actions, outcome))
    return result

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
        answer = f"For {role}, a useful first step is {topics[0]}. Open Course Roadmap to choose your own timeline and build a staged plan for {family.lower()}."
        links = [("SWAYAM course search", "https://swayam.gov.in/search_courses"), ("NCS career services", "https://www.ncs.gov.in/")]
    else:
        answer = "I can help with resumes, CGPA, course search, internships and role-based roadmaps. For other topics, search the exact question and verify details with the institution or employer."
        links = [("National Career Service", "https://www.ncs.gov.in/"), ("SWAYAM courses", "https://swayam.gov.in/search_courses")]
    return answer, links


def read_gemini_settings() -> tuple[str, str]:
    """Read the Gemini key and model from Streamlit secrets or environment variables."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
    try:
        settings = st.secrets.get("gemini", {})
        api_key = str(settings.get("api_key", api_key)).strip()
        model = str(settings.get("model", model)).strip()
    except Exception:
        pass
    return api_key, model or "gemini-2.5-flash"


def generate_ai_career_reply(
    question: str,
    history: list[dict],
    target_role: str,
    cgpa_text: str,
    recognized_skills: list[str],
    resume_loaded: bool,
) -> str:
    """Generate a contextual GradPath response using the Google Gemini API."""
    api_key, model = read_gemini_settings()
    if not api_key:
        raise RuntimeError("Gemini API key is not configured.")
    if genai is None:
        raise RuntimeError("The google-genai package is not installed. Run: python -m pip install google-genai")

    profile = [
        f"Target career role: {target_role or 'Not selected'}",
        f"CGPA detected or verified: {cgpa_text or 'Not available'}",
        f"Resume uploaded in this session: {'Yes' if resume_loaded else 'No'}",
        "Skills recognized by the app: " + (", ".join(recognized_skills[:30]) if recognized_skills else "None detected"),
    ]
    instructions = (
        "You are GradPath AI, a helpful career and study-planning assistant for undergraduate students, "
        "especially students studying in India. Give clear, practical, encouraging answers in plain language. "
        "Use the student's profile as context, but do not assume detected skills are expert-level. "
        "When giving a roadmap, break it into achievable stages with skills, practice, projects and next steps. "
        "Treat CGPA as one factor for choosing a learning pace, never as a universal measure of ability or eligibility. "
        "Never invent course availability, fees, hiring numbers, salary figures, employer rules or placement guarantees. "
        "Tell the student to verify current eligibility and course details with the institution or employer. "
        "Do not claim that you reviewed the full resume: the app shares only a short profile summary with you. "
        "Do not ask for passwords, API keys, identity documents or unnecessary personal information. "
        "If key details are missing, ask one focused follow-up question.\n\n"
        "Student profile:\n- " + "\n- ".join(profile)
    )

    contents = []
    for item in history[-12:]:
        speaker = item.get("role")
        content = item.get("content", "")
        if speaker in {"user", "assistant"} and isinstance(content, str) and content.strip():
            contents.append({
                "role": "model" if speaker == "assistant" else "user",
                "parts": [{"text": content[-5000:]}],
            })
    if not contents or contents[-1]["role"] != "user":
        contents.append({"role": "user", "parts": [{"text": question}]})

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config={"system_instruction": instructions, "max_output_tokens": 800},
    )
    answer = (getattr(response, "text", None) or "").strip()
    if not answer:
        raise RuntimeError("Gemini returned an empty response. Please try again.")
    return answer


def feed_setup_text() -> str:
    return (
        "Add an authorized normalized CSV feed in .streamlit/secrets.toml under [jobs] as csv_url = "
        '"https://your-approved-feed.csv". If needed, add api_token = "YOUR_TOKEN" there. '
        "The CSV must include Year, Sector, Job_Role, Hiring_Count and Location."
    )


st.sidebar.markdown("## GradPath")
st.sidebar.caption("Undergraduate resume, course and career planning")
if st.sidebar.button("Refresh trend data now", width="stretch", key="refresh_market"):
    fetch_daily_feed.clear()
    fetch_hopin_report.clear()
    st.rerun()

try:
    hopin_report = fetch_hopin_report()
    save_hopin_snapshot(hopin_report)
    hopin_error = None
except Exception as error:
    hopin_report = None
    hopin_error = str(error)

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

if hopin_report:
    st.sidebar.success("India fresher-market data connected")
    st.sidebar.caption("Hopin report date: " + str(hopin_report.get("updatedAt", "Not supplied")))
    st.sidebar.caption("Publisher refreshes the report daily; GradPath checks it when opened.")
else:
    st.sidebar.warning("Live market source unavailable; historical sample data remains available.")
    st.sidebar.caption(str(hopin_error))

years = sorted(market["Year"].dropna().astype(int).unique().tolist())
sectors = sorted(market["Sector"].dropna().astype(str).unique().tolist())
roles = sorted(market["Job_Role"].dropna().astype(str).unique().tolist())
sources = sorted(market["Source"].dropna().astype(str).unique().tolist()) if "Source" in market else []

market_tab, resume_tab, roadmap_tab, chat_tab, about_tab = st.tabs(
    ["📈 Market trends", "📄 Resume Coach", "🎓 Course Roadmap", "💬 Career Help Chat", "⚙️ Data & privacy"]
)

with market_tab:
    st.subheader("India fresher & entry-level market — live snapshot")
    if hopin_report:
        totals = hopin_report["totals"]
        try:
            published = datetime.fromisoformat(str(hopin_report["updatedAt"]).replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - published.astimezone(timezone.utc)).total_seconds() / 3600
            published_label = published.astimezone().strftime("%d %b %Y, %I:%M %p %Z")
        except Exception:
            age_hours = None
            published_label = str(hopin_report["updatedAt"])
        live_cols = st.columns(5)
        live_cols[0].metric("Live listings", f"{int(totals['liveListings']):,}")
        live_cols[1].metric("New in last 7 days", f"{int(totals['newLast7Days']):,}")
        live_cols[2].metric("Internship share", f"{float(totals['internshipSharePct']):.1f}%")
        live_cols[3].metric("Remote share", f"{float(totals['remoteSharePct']):.1f}%")
        live_cols[4].metric("Median posting age", f"{float(totals['medianPostingAgeDays']):.1f} days")
        st.caption(f"Publisher's data date: {published_label} · Retrieved automatically when the app opens; refresh cache: up to 6 hours.")
        if age_hours is not None and age_hours > 48:
            st.warning("The source report is more than 48 hours old. The figures are shown with their publisher date and may not represent today's market.")
        st.caption("Source: [Hopin India Fresher Hiring Report](https://hopinjobs.com/reports/fresher-hiring-india) · CC BY 4.0. These are job-posting counts, not confirmed hires.")
        live_left, live_right = st.columns(2)
        role_rows = hopin_report.get("topRoles", [])
        if role_rows:
            role_frame = pd.DataFrame(role_rows)
            if {"label", "count"}.issubset(role_frame.columns):
                role_frame["count"] = pd.to_numeric(role_frame["count"], errors="coerce")
                role_frame = role_frame.dropna(subset=["count"]).nlargest(10, "count").sort_values("count")
                fig = px.bar(role_frame, x="count", y="label", orientation="h", text_auto=True,
                             labels={"count": "Current listings", "label": "Role"}, color="count",
                             color_continuous_scale=["#CDE6FF", BLUE])
                fig.update_layout(template="plotly_white", height=390, coloraxis_showscale=False, margin=dict(l=10, r=10, t=20, b=10))
                live_left.plotly_chart(fig, width="stretch", config={"displaylogo": False})
                live_left.caption("Roles with the most currently tracked fresher listings.")
        city_rows = hopin_report.get("topCities", [])
        if city_rows:
            city_frame = pd.DataFrame(city_rows)
            if {"label", "count"}.issubset(city_frame.columns):
                city_frame["count"] = pd.to_numeric(city_frame["count"], errors="coerce")
                city_frame = city_frame.dropna(subset=["count"]).nlargest(10, "count").sort_values("count")
                fig = px.bar(city_frame, x="count", y="label", orientation="h", text_auto=True,
                             labels={"count": "Current listings", "label": "City / work mode"}, color="count",
                             color_continuous_scale=["#B7F0E8", TEAL])
                fig.update_layout(template="plotly_white", height=390, coloraxis_showscale=False, margin=dict(l=10, r=10, t=20, b=10))
                live_right.plotly_chart(fig, width="stretch", config={"displaylogo": False})
                live_right.caption("Cities and work modes with the most currently tracked listings.")
        snapshots = load_hopin_snapshots()
        st.markdown("#### Daily market history and ML trend estimate")
        st.caption("GradPath saves one local snapshot for each distinct report publication date. The history grows as the dashboard is opened on new report days.")
        if len(snapshots) >= 7 and LinearRegression is not None:
            snapshots["day_number"] = (snapshots["published_at"] - snapshots["published_at"].min()).dt.total_seconds() / 86400
            model = LinearRegression().fit(snapshots[["day_number"]], snapshots["live_listings"])
            future_day = float(snapshots["day_number"].max() + 7)
            estimate = max(0, float(model.predict(pd.DataFrame({"day_number": [future_day]}))[0]))
            st.metric("Experimental 7-day listing estimate", f"{estimate:,.0f}", help="A simple linear-regression estimate from saved daily snapshots, not a hiring guarantee.")
            chart_data = snapshots.melt(id_vars=["snapshot_date"], value_vars=["live_listings", "new_last_7_days"],
                                        var_name="Measure", value_name="Listings")
            chart_data["Measure"] = chart_data["Measure"].map({"live_listings": "Live listings", "new_last_7_days": "New in last 7 days"})
            fig = px.line(chart_data, x="snapshot_date", y="Listings", color="Measure", markers=True,
                          labels={"snapshot_date": "Report date", "Listings": "Listing count"}, color_discrete_sequence=COLORS)
            fig.update_layout(template="plotly_white", height=330, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
            st.caption(f"Model trained on {len(snapshots)} distinct daily snapshots. The estimate is directional only and may be affected by changes in the source's collection coverage.")
        else:
            st.info(f"ML trend estimates will activate after 7 distinct daily source snapshots. Currently saved: {len(snapshots)}. Keep the app open or revisit it on later days so GradPath can collect the next published snapshot.")
    else:
        st.warning("The live Hopin report could not be reached. The historical sample data below remains available.")
        st.caption("Live data error: " + str(hopin_error))

    st.divider()
    st.subheader("Historical sample-data explorer")
    st.warning("This section is the original historical sample dataset (2020–2023). It is separate from the live Hopin fresher-listing snapshot above and should not be read as today's hiring totals.")
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
    st.write("Upload a resume to review its structure, recognised skills and CGPA. Choose a career goal to get study recommendations, a skill-gap summary and a complete roadmap in the Course Roadmap tab. The upload is processed in this session; this app code does not write it to disk.")
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
            goal_options = roles + ["Custom career goal"]
            current_goal = st.session_state.get("roadmap_target_role", default_role)
            default_goal_choice = current_goal if current_goal in roles else ("Custom career goal" if current_goal not in roles else default_role)
            target_choice = st.selectbox(
                "Career goal you want to work towards", goal_options,
                index=goal_options.index(default_goal_choice) if default_goal_choice in goal_options else 0,
                key="resume_target_role",
            )
            if target_choice == "Custom career goal":
                target_role = st.text_input(
                    "Describe your target career", value=st.session_state.get("resume_custom_goal", ""),
                    placeholder="e.g. Product Manager, UX Researcher, Government Data Officer",
                    key="resume_custom_goal",
                ).strip() or "Custom career goal"
            else:
                target_role = target_choice
            st.session_state["roadmap_target_role"] = target_role
            # Synchronise the course-roadmap selector only when the Resume Coach goal changes.
            if st.session_state.get("_last_resume_goal") != target_role:
                st.session_state["roadmap_role_choice"] = target_choice
                if target_choice == "Custom career goal":
                    st.session_state["roadmap_custom_target"] = target_role if target_role != "Custom career goal" else ""
                st.session_state["_last_resume_goal"] = target_role
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
            gaps = skill_gap_for_role(target_role, skills)
            st.markdown("#### Personalised study recommendations")
            st.write(f"**Career path:** {family}")
            st.write("**Priority topics:** " + ", ".join(topics))
            st.write("**Suggested skill gaps to work on:** " + (", ".join(gaps) if gaps else "Your resume contains the main detected keywords. Focus next on project depth and practical proof."))
            st.write("Strengthen project bullets with your actual task, tools you used, and results you can support with evidence.")
            st.info("Open the Course Roadmap tab to choose your own timeline and generate a complete staged plan using this career goal, your resume skills and your CGPA.")
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
    st.subheader("Your personalised career roadmap")
    st.write("Choose a career goal and timeline. GradPath compares the goal with skills detected in your resume and uses CGPA only to suggest a sensible learning pace.")

    current_role = st.session_state.get("roadmap_target_role", roles[0] if roles else "Graduate role")
    roadmap_options = roles + ["Custom career goal"]
    default_roadmap_choice = current_role if current_role in roles else "Custom career goal"
    if st.session_state.get("roadmap_role_choice") not in roadmap_options:
        st.session_state["roadmap_role_choice"] = default_roadmap_choice
    role_choice = st.selectbox("Career goal", roadmap_options, key="roadmap_role_choice")
    if role_choice == "Custom career goal":
        target = st.text_input(
            "Describe your target career", value=st.session_state.get("roadmap_custom_target", current_role if current_role not in roles else ""),
            placeholder="e.g. Product Manager, UX Researcher, Government Data Officer",
            key="roadmap_custom_target",
        ).strip()
        if not target:
            target = "Custom career goal"
    else:
        target = role_choice
    st.session_state["roadmap_target_role"] = target

    duration_choice = st.selectbox(
        "How long do you want to work towards this goal?",
        ["1 month", "3 months", "6 months", "9 months", "12 months", "Custom"],
        index=2, key="roadmap_duration_choice",
    )
    if duration_choice == "Custom":
        duration_months = int(st.number_input("Enter your duration (months)", min_value=1, max_value=36, value=6, step=1, key="roadmap_custom_duration"))
    else:
        duration_months = int(duration_choice.split()[0])

    resume_text = st.session_state.get("resume_text", "")
    detected_skills = detect_skills(resume_text) if resume_text else []
    st.markdown("### Your starting point")
    if resume_text:
        st.write("**Resume analysed:** " + st.session_state.get("resume_name", "Uploaded resume"))
        st.write("**Skills recognised in resume:** " + (", ".join(detected_skills) if detected_skills else "No built-in skill keywords found; review the resume manually."))
    else:
        st.info("No resume is uploaded in this session. You can still build a goal-based roadmap and add skills you already know below.")
    skill_options = sorted(set(SKILL_TERMS + detected_skills))
    known_skills = st.multiselect(
        "Skills you can already use (edit this list)", skill_options,
        default=detected_skills, key="roadmap_known_skills",
        help="Choose only skills you can explain or demonstrate. This helps GradPath avoid recommending topics you already know.",
    )
    missing_skills = skill_gap_for_role(target, detected_skills, known_skills)
    cgpa_detected, cgpa_scale = detect_cgpa(resume_text) if resume_text else (None, None)
    profile_mark = st.session_state.get("verified_cgpa", cgpa_detected)
    profile_scale = st.session_state.get("verified_cgpa_scale", cgpa_scale)
    if profile_mark is None:
        with st.expander("Add CGPA or marks (optional)"):
            manual_scale_labels = {10.0: "CGPA / 10", 4.0: "GPA / 4", 100.0: "Percentage / 100"}
            manual_scale = st.selectbox("Marks format", [10.0, 4.0, 100.0], format_func=lambda value: manual_scale_labels[value], key="roadmap_manual_scale")
            manual_mark = st.number_input("Your current overall marks", min_value=0.0, max_value=float(manual_scale), value=0.0, step=0.1, key="roadmap_manual_mark")
            use_manual = st.checkbox("Use these marks for my study plan", key="roadmap_use_manual_marks")
            if use_manual:
                profile_mark, profile_scale = manual_mark, manual_scale
    normalized_mark = 100 * float(profile_mark) / float(profile_scale) if profile_mark is not None and profile_scale else None

    family, topics, _ = role_learning_plan(target)
    st.markdown(f"### Recommended learning path: {family}")
    st.write(f"**Your goal:** {target}  ·  **Your timeline:** {duration_months} month(s)")
    st.write("**Core topics:** " + ", ".join(topics))
    st.markdown("#### Resume-to-goal skill gap")
    if missing_skills:
        st.write("Prioritise these areas: " + ", ".join(missing_skills))
    else:
        st.write("No major gaps were detected using the built-in keyword list. Check the list manually and focus on deeper project evidence and practice.")

    if normalized_mark is not None:
        if normalized_mark < 60:
            pace_label = "Foundation-first study pace"
            pace_text = "Spend extra time on core concepts, revision and guided exercises. Start with beginner-level material before advanced certificates."
        elif normalized_mark < 80:
            pace_label = "Balanced learning and practice pace"
            pace_text = "Combine core lessons with regular practice. Use short assessments and applied work to find topics that need more revision."
        else:
            pace_label = "Specialisation-ready learning pace"
            pace_text = "After confirming the fundamentals, add a focused specialization and a more substantial project."
        st.info(f"CGPA / marks: {float(profile_mark):g}/{float(profile_scale):g} ({normalized_mark:.1f}%). **{pace_label}.** {pace_text}")
        st.caption("CGPA is used only to suggest a learning pace. It does not measure potential, prove practical skill or determine course/job eligibility.")
    else:
        st.info("No CGPA was supplied. The roadmap uses a balanced starting pace. Add CGPA in Resume Coach or the optional field above to tailor the study approach.")

    roadmap = build_personalized_roadmap(target, duration_months, missing_skills, normalized_mark)
    st.markdown("#### Step-by-step roadmap")
    for milestone, actions, outcome in roadmap:
        with st.expander(milestone, expanded=True):
            st.write(actions)
            st.markdown("**Milestone / evidence:** " + outcome)

    st.markdown("#### Course and practice resources")
    search_terms = quote_plus(" ".join(topics))
    c1, c2 = st.columns(2)
    c1.link_button("Search these topics on SWAYAM", "https://swayam.gov.in/search_courses?searchText=" + search_terms, width="stretch")
    c2.link_button("Explore NPTEL courses", "https://nptel.ac.in/courses", width="stretch")
    st.caption("These are course-search links, not endorsements of a specific course. Check the provider for current dates, fees, prerequisites and certificate conditions.")

    export_lines = [
        "GRADPATH PERSONAL CAREER ROADMAP",
        f"Career goal: {target}",
        f"Duration: {duration_months} month(s)",
        f"Learning path: {family}",
        f"CGPA/marks band: {normalized_mark:.1f}%" if normalized_mark is not None else "CGPA/marks band: Not supplied",
        "Recognised/confirmed skills: " + (", ".join(known_skills) if known_skills else "Not supplied"),
        "Suggested skill gaps: " + (", ".join(missing_skills) if missing_skills else "Review manually; no major keyword gaps detected"),
        "",
    ]
    for milestone, actions, outcome in roadmap:
        export_lines.extend([milestone, actions, "Milestone: " + outcome, ""])
    export_lines.extend([
        "Course search: " + "https://swayam.gov.in/search_courses?searchText=" + search_terms,
        "NPTEL: https://nptel.ac.in/courses",
        "",
        "Note: This is an educational planning guide, not a hiring, admission or certification guarantee. Verify current eligibility with the course provider or employer.",
    ])
    st.download_button(
        "Download my complete career roadmap (.txt)",
        data="\n".join(export_lines).encode("utf-8"),
        file_name="GradPath_personal_career_roadmap.txt",
        mime="text/plain",
        width="stretch",
    )

with chat_tab:
    st.subheader("Career Help Chat")
    st.write(
        "Ask GradPath about careers, resumes, CGPA, courses, internships and preparation plans. "
        "When a Gemini API key is configured, responses are generated by AI and use a short summary "
        "of your selected role and detected profile details."
    )

    current_resume = st.session_state.get("resume_text", "")
    detected, maximum = detect_cgpa(current_resume) if current_resume else (None, None)
    cgpa_context = f"{detected:g}/{maximum:g}" if detected is not None else ""
    verified_mark = st.session_state.get("verified_cgpa")
    verified_scale = st.session_state.get("verified_cgpa_scale")
    if verified_mark is not None and verified_scale:
        cgpa_context = f"{float(verified_mark):g}/{float(verified_scale):g}"

    recognized_skills = detect_skills(current_resume) if current_resume else []
    selected_role = st.session_state.get("roadmap_target_role", roles[0] if roles else "graduate role")
    api_key, _ = read_gemini_settings()
    if api_key and genai is not None:
        st.success("Gemini AI chat is connected. Your API key is read securely from secrets.")
    elif not api_key:
        st.info(
            "AI chat is ready but not connected yet. Add your Gemini API key in "
            "`.streamlit/secrets.toml` under `[gemini]` to enable AI responses. Until then, the built-in career guide remains available."
        )
    else:
        st.warning("Install the google-genai package to enable AI responses: python -m pip install google-genai")

    if "career_chat_history" not in st.session_state:
        st.session_state["career_chat_history"] = []

    for message in st.session_state["career_chat_history"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            for label, url in message.get("links", []):
                st.markdown(f"[{label}]({url})")

    question = st.chat_input("Ask a career or resume question")
    if question and question.strip():
        user_message = {"role": "user", "content": question.strip()}
        st.session_state["career_chat_history"].append(user_message)
        with st.chat_message("user"):
            st.markdown(question.strip())

        with st.chat_message("assistant"):
            if api_key and genai is not None:
                try:
                    with st.spinner("GradPath AI is thinking..."):
                        answer = generate_ai_career_reply(
                            question=question.strip(),
                            history=st.session_state["career_chat_history"],
                            target_role=selected_role,
                            cgpa_text=cgpa_context,
                            recognized_skills=recognized_skills,
                            resume_loaded=bool(current_resume),
                        )
                    st.markdown(answer)
                    st.session_state["career_chat_history"].append(
                        {"role": "assistant", "content": answer, "links": []}
                    )
                except Exception as exc:
                    st.error(
                        "GradPath couldn't reach the AI service. Check that your Gemini API key is valid, "
                        "your free-tier quota is available, and your internet connection is working. "
                        f"Technical detail: {exc}"
                    )
            else:
                answer, links = career_bot_answer(
                    question.strip(), selected_role, cgpa_context, bool(current_resume)
                )
                st.markdown(answer)
                for label, url in links:
                    st.markdown(f"[{label}]({url})")
                st.session_state["career_chat_history"].append(
                    {"role": "assistant", "content": answer, "links": links}
                )

    st.markdown("**Helpful places to search**")
    st.markdown("- [National Career Service - jobs, internships and career services](https://www.ncs.gov.in/)")
    st.markdown("- [SWAYAM - search courses](https://swayam.gov.in/search_courses)")
    st.markdown("- [NPTEL courses](https://nptel.ac.in/courses)")
    topic = st.text_input("Need another search? Enter a topic", key="career_search")
    if topic.strip():
        st.link_button("Search the web for this topic", "https://www.google.com/search?q=" + quote_plus(topic.strip()))

with about_tab:
    st.subheader("Data freshness and privacy")
    st.markdown(f"**Historical data source:** {market_source}  \n**Historical feed retrieval:** {fetched_at}")
    st.markdown("**Live entry-level source:** [Hopin India Fresher Hiring Report](https://hopinjobs.com/reports/fresher-hiring-india)")
    if hopin_report:
        st.write(f"Publisher report date: {hopin_report.get('updatedAt', 'Not supplied')}. GradPath checks the public report when the app opens and caches it for up to 6 hours. The publisher says the report is rebuilt daily.")
    else:
        st.warning("The live report is currently unavailable; the historical sample-data explorer remains available.")
        st.write("GradPath does not scrape job websites directly. Live listing figures are supplied by Hopin and are attributed under its CC BY 4.0 licence.")
    st.write("Daily snapshots are stored in a local SQLite database beside the app, with one observation per publisher report date. On a local computer, the app must be opened on later days to collect new snapshots; it cannot fetch while the computer/app is off. A hosted deployment needs persistent storage and a scheduled job for unattended daily collection.")
    st.write("Live listing counts represent published job postings, not confirmed hires, placements or guaranteed vacancies.")
    if feed_error:
        st.error("Historical CSV feed error: " + feed_error)
    st.markdown("#### Resume handling")
    st.write("Resume text is extracted in the app process for this session. The app code does not save the uploaded file or extracted text to disk. Clearing the upload or ending the session removes the session data. For a public deployment, tell students where the app is hosted and review its privacy setup before accepting resumes.")
    st.markdown("#### AI chat and external processing")
    st.write("When Gemini AI chat is enabled, GradPath sends your current question, up to 12 recent chat messages, and a short profile summary (selected role, CGPA and detected skill keywords) to Google's Gemini API to generate a response. It does not send the uploaded resume file or the full extracted resume text. Avoid entering sensitive personal information in the chat. Google's Gemini API free tier may use submitted content to improve its products; review Google's current API terms before using real student data.")
    st.markdown("#### Project data limits")
    st.write("The historical file includes hiring figures, job roles, sectors, locations, sources, salary values and placement values. It does not include verified skill requirements, qualification rules or individual student outcomes. Resume checks and course roadmaps are explainable guidance, not ML predictions of hiring success.")

st.divider()
st.caption("GradPath · Undergraduate resume and career planning · Verify course rules and job details with their original provider.")
