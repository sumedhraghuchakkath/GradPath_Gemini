"""Student-friendly employment and course exploration dashboard."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from sklearn.linear_model import LinearRegression
except ImportError:
    LinearRegression = None


st.set_page_config(
    page_title="Future Pathways | Hiring & Placement Explorer",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

COLORS = ["#2563EB", "#0F9D8A", "#8B5CF6", "#F59E0B", "#E85D75", "#0891B2"]
BLUE = "#2563EB"
TEAL = "#0F9D8A"

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .stApp { background: #F4F7FC; }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] { background: #12213C; }
    [data-testid="stSidebar"] * { color: #EDF3FC; }
    [data-testid="stSidebar"] [data-baseweb="tag"] { background: #24436D; }
    .hero { padding: 1.55rem 1.8rem; border-radius: 20px; color: white;
      background: linear-gradient(115deg, #12213C 0%, #1C4774 60%, #11877F 100%);
      margin: .2rem 0 1.1rem; box-shadow: 0 12px 28px rgba(18,33,60,.14); }
    .hero h1 { font-family: 'Manrope', sans-serif; font-size: 2rem; margin: 0 0 .3rem; }
    .hero p { color: #DCEBFA; font-size: 1rem; margin: 0; }
    .eyebrow { text-transform: uppercase; letter-spacing: .13em; font-size: .72rem;
      color: #98F0DF; font-weight: 700; margin-bottom: .45rem; }
    div[data-testid="stMetric"] { background: white; border: 1px solid #E4EAF3;
      padding: .9rem 1rem; border-radius: 15px; box-shadow: 0 4px 14px rgba(18,33,60,.04); }
    div[data-testid="stMetricLabel"] { color: #58677E; }
    div[data-testid="stMetricValue"] { color: #12213C; font-family: 'Manrope', sans-serif; }
    h2, h3 { font-family: 'Manrope', sans-serif !important; color: #12213C; }
    .hint { color: #58677E; margin-top: -.55rem; margin-bottom: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data(csv_path: str) -> pd.DataFrame:
    data = pd.read_csv(csv_path)
    data.columns = data.columns.str.strip()
    data = data.loc[:, ~data.columns.str.lower().str.startswith("unnamed")]
    numeric_cols = [
        "Year", "Hiring_Count", "Hiring_Growth_%", "Placement_Count",
        "Average_Salary", "Source_Page",
    ]
    for col in numeric_cols:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")
    for col in data.select_dtypes(include="object").columns:
        data[col] = data[col].fillna("Unknown").astype(str).str.strip()
    return data


DATA_PATH = Path(__file__).resolve().with_name("hiring_data.csv")
if not DATA_PATH.exists():
    st.error("I can't find `hiring_data.csv` beside this dashboard.")
    st.info("Keep the CSV and `app.py` in the same folder.")
    st.stop()

df = load_data(str(DATA_PATH))
needed = {"Year", "Sector", "Job_Role", "Hiring_Count", "Location"}
missing = sorted(needed.difference(df.columns))
if missing:
    st.error("The data file is missing: " + ", ".join(missing))
    st.stop()

for col in ["Hiring_Growth_%", "Placement_Count", "Average_Salary"]:
    if col not in df.columns:
        df[col] = pd.NA
for col in ["Demand_Trend", "Month", "Source", "Company"]:
    if col not in df.columns:
        df[col] = "Unknown"


def choices(column: str) -> list:
    return sorted(df[column].dropna().unique().tolist(), key=str)


st.sidebar.markdown("## 🔎 Explore job information")
st.sidebar.caption("Filters update the charts together. Start with everything selected.")
filter_keys = ["years_filter", "sectors_filter", "locations_filter", "sources_filter"]
if st.sidebar.button("Reset all filters", width="stretch"):
    for key in filter_keys:
        st.session_state.pop(key, None)
    st.rerun()

all_years = sorted(df["Year"].dropna().astype(int).unique().tolist())
all_sectors = choices("Sector")
all_locations = choices("Location")
all_sources = choices("Source")
years_selected = st.sidebar.multiselect("Years", all_years, default=all_years, key=filter_keys[0])
sectors_selected = st.sidebar.multiselect("Work areas (sectors)", all_sectors, default=all_sectors, key=filter_keys[1])
locations_selected = st.sidebar.multiselect("Cities", all_locations, default=all_locations, key=filter_keys[2])
sources_selected = st.sidebar.multiselect("Data sources", all_sources, default=all_sources, key=filter_keys[3])

view = df[
    df["Year"].isin(years_selected)
    & df["Sector"].isin(sectors_selected)
    & df["Location"].isin(locations_selected)
    & df["Source"].isin(sources_selected)
].copy()
st.sidebar.divider()
st.sidebar.caption(f"Showing **{len(view):,}** of {len(df):,} records")

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">A guide for exploring what comes next</div>
      <h1>Future Pathways</h1>
      <p>See what jobs appear in the data, explore work areas, and discover courses that match what you enjoy.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption("Use this as a conversation starter with a teacher, family member or career counsellor. A chart cannot decide your future for you.")
if view.empty:
    st.warning("No records match those filters. Select more years, work areas, cities or sources.")
    st.stop()

top_work_area = view.groupby("Sector")["Hiring_Count"].mean().idxmax()
top_work_area_value = view.groupby("Sector")["Hiring_Count"].mean().max()
mean_growth = view["Hiring_Growth_%"].mean()
typical_pay = view["Average_Salary"].median()
placement_total = view["Placement_Count"].sum()
record_count = len(view)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Records in view", f"{record_count:,}", help="Rows in the selected part of the data file")
m2.metric("Placements shown", f"{placement_total:,.0f}", help="Sum of placement values in the selected records")
m3.metric("Top work area", str(top_work_area), help=f"Highest average reported hiring figure per record: {top_work_area_value:,.0f}")
m4.metric("Avg. reported growth", f"{mean_growth:+.1f}%" if pd.notna(mean_growth) else "—")
m5.metric("Typical salary value", f"{typical_pay:,.1f}" if pd.notna(typical_pay) else "—", help="The CSV does not state a salary unit; check the original source before comparing values.")

st.caption("Hiring values are the figures reported in the source records; rows may represent different snapshots. Salary units are not specified in this CSV.")
snapshot_tab, jobs_tab, forecast_tab, pathway_tab, data_tab = st.tabs(
    ["🌍 Big picture", "💼 Explore jobs", "🔮 Future trends", "🧭 My course ideas", "📚 Data & project"]
)

chart_config = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}

with snapshot_tab:
    st.subheader("What does the job picture look like?")
    st.markdown('<p class="hint">Each chart has a short explanation. Hover over a point or bar for its exact value.</p>', unsafe_allow_html=True)
    left, right = st.columns([1.4, 1])
    by_year = view.groupby(["Year", "Sector"], as_index=False).agg(Reported_Hiring=("Hiring_Count", "mean"))
    chosen_for_line = (view.groupby("Sector")["Hiring_Count"].mean().nlargest(6).index.tolist())
    line_data = by_year[by_year["Sector"].isin(chosen_for_line)]
    fig = px.line(line_data, x="Year", y="Reported_Hiring", color="Sector", markers=True,
                  color_discrete_sequence=COLORS, labels={"Year": "Year", "Reported_Hiring": "Average hiring figure in records"})
    fig.update_layout(template="plotly_white", height=390, hovermode="x unified", margin=dict(l=10, r=10, t=15, b=10), legend_title_text="Work area")
    left.plotly_chart(fig, width="stretch", config=chart_config)
    left.caption("This compares the average hiring figure in records for the six busiest work areas. It is not a count of every job in India.")

    placement_by_year = view.groupby("Year", as_index=False).agg(Placements=("Placement_Count", "sum"))
    if not placement_by_year.empty:
        fig = px.bar(placement_by_year, x="Year", y="Placements", text_auto=".3s",
                     color_discrete_sequence=[TEAL],
                     labels={"Year": "Year", "Placements": "Placement values in records"},
                     title="Placement values recorded by year")
        fig.update_layout(template="plotly_white", height=330, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch", config=chart_config)
        st.caption("These are placement values from the dataset, not a student's chance of being placed.")

    sector_data = view.groupby("Sector", as_index=False).agg(Reported_Hiring=("Hiring_Count", "mean"))
    sector_data = sector_data.nlargest(10, "Reported_Hiring").sort_values("Reported_Hiring")
    fig = px.bar(sector_data, x="Reported_Hiring", y="Sector", orientation="h", text_auto=".3s",
                 color="Reported_Hiring", color_continuous_scale=["#B7D8FF", BLUE],
                 labels={"Reported_Hiring": "Average hiring figure in records", "Sector": "Work area"})
    fig.update_layout(template="plotly_white", height=390, margin=dict(l=10, r=10, t=15, b=10), coloraxis_showscale=False)
    right.plotly_chart(fig, width="stretch", config=chart_config)
    right.caption("Longer bars mean a larger average hiring figure in this selected data. They do not guarantee a job.")

    st.subheader("Are reported trends going up or down?")
    trend = view.groupby("Demand_Trend", as_index=False).size().rename(columns={"size": "Number of records"})
    fig = px.bar(trend, x="Demand_Trend", y="Number of records", color="Demand_Trend",
                 color_discrete_sequence=COLORS, labels={"Demand_Trend": "Trend label in source", "Number of records": "Number of records"})
    fig.update_layout(template="plotly_white", height=320, showlegend=False, margin=dict(l=10, r=10, t=15, b=10))
    st.plotly_chart(fig, width="stretch", config=chart_config)
    st.caption("This counts source records labelled increasing, stable or decreasing. It is not a prediction of your personal future.")

    observed_years = sorted(view["Year"].dropna().unique().tolist())
    if len(observed_years) >= 2:
        latest_year, previous_year = observed_years[-1], observed_years[-2]
        yearly_sector = view.groupby(["Year", "Sector"], as_index=False).agg(
            Average_Hiring=("Hiring_Count", "mean"), Records=("Hiring_Count", "size")
        )
        recent = yearly_sector[yearly_sector["Year"] == latest_year][["Sector", "Average_Hiring", "Records"]].rename(
            columns={"Average_Hiring": "Latest", "Records": "Latest records"}
        )
        prior = yearly_sector[yearly_sector["Year"] == previous_year][["Sector", "Average_Hiring", "Records"]].rename(
            columns={"Average_Hiring": "Previous", "Records": "Previous records"}
        )
        change = recent.merge(prior, on="Sector").dropna()
        if not change.empty:
            change["Difference"] = change["Latest"] - change["Previous"]
            change = change.nlargest(8, "Difference").sort_values("Difference")
            st.subheader("Work areas with a recent rise in the data")
            fig = px.bar(change, x="Difference", y="Sector", orientation="h", text_auto="+.3s",
                         color="Difference", color_continuous_scale=["#F4A7B5", "#E8EDF5", TEAL],
                         labels={"Difference": "Change in average hiring figure", "Sector": "Work area"})
            fig.add_vline(x=0, line_dash="dot", line_color="#667085")
            fig.update_layout(template="plotly_white", height=350, coloraxis_showscale=False, margin=dict(l=10, r=10, t=15, b=10))
            st.plotly_chart(fig, width="stretch", config=chart_config)
            st.caption(f"This compares {previous_year} with {latest_year}, the latest two years in your current filters. Record months and sources can differ, so treat it as a clue to explore, not proof of a long-term change.")

with jobs_tab:
    st.subheader("Jobs and pay in the selected records")
    st.markdown('<p class="hint">Compare work areas, roles, places and pay values. Pay is shown in the source file’s unit.</p>', unsafe_allow_html=True)
    left, right = st.columns(2)
    role_data = view.groupby("Job_Role", as_index=False).agg(Reported_Hiring=("Hiring_Count", "mean"))
    role_data = role_data.nlargest(10, "Reported_Hiring").sort_values("Reported_Hiring")
    fig = px.bar(role_data, x="Reported_Hiring", y="Job_Role", orientation="h", text_auto=".3s",
                 color="Reported_Hiring", color_continuous_scale=["#B7D8FF", BLUE],
                 labels={"Reported_Hiring": "Average hiring figure in records", "Job_Role": "Job"}, title="Jobs with higher reported hiring figures")
    fig.update_layout(template="plotly_white", height=430, coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10))
    left.plotly_chart(fig, width="stretch", config=chart_config)
    left.caption("These are job titles found in the data, sorted by average reported hiring figure.")

    salary_data = view.groupby("Sector", as_index=False).agg(Typical_Salary=("Average_Salary", "median"))
    salary_data = salary_data.dropna().nlargest(10, "Typical_Salary").sort_values("Typical_Salary")
    fig = px.bar(salary_data, x="Typical_Salary", y="Sector", orientation="h", text_auto=".2f",
                 color="Typical_Salary", color_continuous_scale=["#B7F0E8", TEAL],
                 labels={"Typical_Salary": "Median salary value in source", "Sector": "Work area"}, title="Typical salary values by work area")
    fig.update_layout(template="plotly_white", height=430, coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10))
    right.plotly_chart(fig, width="stretch", config=chart_config)
    right.caption("This is a median of the salary values recorded, not a promise of what a new worker will earn.")

    salary_years = view.groupby(["Year", "Sector"], as_index=False).agg(Typical_Salary=("Average_Salary", "median"))
    pay_sectors = view.groupby("Sector")["Average_Salary"].median().nlargest(5).index.tolist()
    salary_years = salary_years[salary_years["Sector"].isin(pay_sectors)].dropna(subset=["Typical_Salary"])
    if not salary_years.empty:
        fig = px.line(salary_years, x="Year", y="Typical_Salary", color="Sector", markers=True,
                      color_discrete_sequence=COLORS,
                      labels={"Year": "Year", "Typical_Salary": "Median salary value in source", "Sector": "Work area"},
                      title="How recorded salary values changed over time")
        fig.update_layout(template="plotly_white", height=370, hovermode="x unified", margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch", config=chart_config)
        st.caption("Only the five work areas with the highest median salary values are shown. Source salary units are not included in this file.")

    loc_data = view.groupby("Location", as_index=False).agg(Reported_Hiring=("Hiring_Count", "mean"))
    loc_data = loc_data.nlargest(8, "Reported_Hiring").sort_values("Reported_Hiring")
    fig = px.bar(loc_data, x="Reported_Hiring", y="Location", orientation="h", text_auto=".3s",
                 color="Reported_Hiring", color_continuous_scale=["#C9D8F7", "#6653C7"],
                 labels={"Reported_Hiring": "Average hiring figure in records", "Location": "City"}, title="Cities shown in this data")
    fig.update_layout(template="plotly_white", height=390, coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, width="stretch", config=chart_config)

with forecast_tab:
    st.subheader("A small, experimental look ahead")
    st.write("The model fits a straight trend to past average hiring figures for each work area and extends it a few years. This helps explore a possible direction; it is not a promise or an official forecast.")
    if LinearRegression is None:
        st.error("The forecasting library is missing. Install scikit-learn in the Python environment used to run Streamlit.")
    else:
        horizon = st.slider("How many years ahead should we sketch?", min_value=1, max_value=3, value=2)
        top_forecast_sectors = view.groupby("Sector")["Hiring_Count"].mean().nlargest(5).index.tolist()
        sector_pick = st.multiselect("Choose work areas to compare", choices("Sector"), default=top_forecast_sectors, key="forecast_sectors")
        hist = view[view["Sector"].isin(sector_pick)].groupby(["Year", "Sector"], as_index=False).agg(Reported_Hiring=("Hiring_Count", "mean"))
        forecast_rows = []
        skipped = []
        for sector in sector_pick:
            sdata = hist[hist["Sector"] == sector].dropna(subset=["Year", "Reported_Hiring"]).sort_values("Year")
            if sdata["Year"].nunique() < 3:
                skipped.append(sector)
                continue
            model = LinearRegression().fit(sdata[["Year"]], sdata["Reported_Hiring"])
            future_years = list(range(int(sdata["Year"].max()) + 1, int(sdata["Year"].max()) + horizon + 1))
            future_values = model.predict(pd.DataFrame({"Year": future_years}))
            forecast_rows.extend({"Year": y, "Sector": sector, "Reported_Hiring": max(0, float(value)), "Line": "Model estimate"} for y, value in zip(future_years, future_values))
            hist.loc[hist["Sector"] == sector, "Line"] = "Recorded data"
        if not hist.empty:
            hist["Line"] = hist["Line"].fillna("Recorded data")
            combined = pd.concat([hist, pd.DataFrame(forecast_rows)], ignore_index=True)
            fig = px.line(combined, x="Year", y="Reported_Hiring", color="Sector", line_dash="Line", markers=True,
                          color_discrete_sequence=COLORS,
                          labels={"Year": "Year", "Reported_Hiring": "Average hiring figure in records", "Line": "Recorded or estimated"})
            fig.update_layout(template="plotly_white", height=440, hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, width="stretch", config=chart_config)
            if skipped:
                st.info("Need at least three different years to draw a trend for: " + ", ".join(skipped))
            st.warning("The file has only 400 records from 2020–2026, with uneven months and sources. These model estimates are a classroom demonstration, not reliable job-market promises. More consistent yearly data and model accuracy checks are needed.")
        else:
            st.info("Choose work areas with records across at least three different years.")

with pathway_tab:
    st.subheader("Find course ideas that fit what you enjoy")
    st.write("Choose a few subjects and activities. The page will show work areas and job examples that connect to your interests.")
    grade = st.radio("Which class are you in?", ["Class 9", "Class 10"], horizontal=True)
    subjects = ["Mathematics", "Science", "Biology", "Computers / technology", "Business / money", "English / languages", "Art / design", "Social science"]
    activities = ["Solving puzzles", "Building or fixing things", "Doing experiments", "Helping people", "Planning or organising", "Drawing or designing", "Writing or speaking", "Working with nature"]
    skills = ["Problem solving", "Creativity", "Explaining ideas", "Teamwork", "Careful observation", "Hands-on making", "Organising", "Using computers"]
    p1, p2 = st.columns(2)
    liked_subjects = p1.multiselect("Subjects you enjoy", subjects)
    liked_activities = p2.multiselect("Activities that sound fun", activities)
    strengths = st.multiselect("Things you like practising", skills)

    pathways = [
        {"name": "Technology & engineering", "subjects": ["Mathematics", "Science", "Computers / technology"], "activities": ["Solving puzzles", "Building or fixing things", "Doing experiments"], "skills": ["Problem solving", "Hands-on making", "Using computers"], "sectors": ["IT/Technology", "Engineering", "Automotive", "Telecom", "Consumer Electronics", "Manufacturing", "Energy", "Construction"], "course": "After Class 10, explore Science with Mathematics or a technical / polytechnic course. Later options can include computing, engineering, electronics or energy.", "why": "These routes use maths, science, design and problem-solving."},
        {"name": "Health & life science", "subjects": ["Science", "Biology"], "activities": ["Doing experiments", "Helping people", "Working with nature"], "skills": ["Careful observation", "Explaining ideas", "Teamwork"], "sectors": ["Healthcare", "Pharma"], "course": "Explore Science with Biology after Class 10. Later options may include healthcare, pharmacy, laboratory science or life sciences.", "why": "These routes connect science with helping people and understanding living things."},
        {"name": "Business, money & markets", "subjects": ["Mathematics", "Business / money", "Social science"], "activities": ["Planning or organising", "Solving puzzles", "Writing or speaking"], "skills": ["Problem solving", "Organising", "Explaining ideas"], "sectors": ["BFSI", "Finance", "Retail & Consumer", "Sales", "Marketing", "Consumer Goods", "Real Estate"], "course": "Explore Commerce after Class 10, with or without Mathematics depending on your interests and school options. Later options may include finance, business, economics or marketing.", "why": "These routes use numbers, planning, communication and understanding customers."},
        {"name": "Creative work & communication", "subjects": ["English / languages", "Art / design", "Social science"], "activities": ["Drawing or designing", "Writing or speaking", "Planning or organising"], "skills": ["Creativity", "Explaining ideas", "Teamwork"], "sectors": ["Creative", "Media & Entertainment", "Education", "Marketing", "NGO/Social Services"], "course": "Explore Humanities / Arts after Class 10, while building a portfolio through writing, design, video or school projects. Later options may include media, design, education or communication.", "why": "These routes reward communication, ideas and creative problem-solving."},
        {"name": "Practical systems & operations", "subjects": ["Mathematics", "Science", "Social science"], "activities": ["Building or fixing things", "Planning or organising", "Working with nature"], "skills": ["Hands-on making", "Careful observation", "Organising"], "sectors": ["Manufacturing", "Logistics", "Shipping/Marine", "Construction", "Automotive", "Engineering", "Energy"], "course": "Compare Science, vocational subjects and diploma / polytechnic routes after Class 10. Later options may include manufacturing, transport, construction or operations.", "why": "These routes help design, make, move or maintain real-world products and services."},
    ]

    def pathway_score(item: dict) -> int:
        return (2 * len(set(liked_subjects) & set(item["subjects"]))
                + len(set(liked_activities) & set(item["activities"]))
                + len(set(strengths) & set(item["skills"])))

    ranked = sorted(pathways, key=pathway_score, reverse=True)
    if not liked_subjects and not liked_activities and not strengths:
        st.info("Pick a subject or activity above to see some starting ideas. It is fine if you are still exploring.")
    else:
        st.success(f"Your strongest interest match right now: **{ranked[0]['name']}**")
        st.caption(f"You are in {grade}. These are ideas to explore, not a test result. Your answers are not saved.")
        for item in ranked[:3]:
            score = pathway_score(item)
            if score == 0:
                continue
            st.markdown(f"### {item['name']}")
            st.write(f"**Why it matched:** {item['why']}")
            st.write(f"**Course ideas:** {item['course']}")
            evidence = df[df["Sector"].isin(item["sectors"])]
            if not evidence.empty:
                role_evidence = evidence.groupby("Job_Role")["Hiring_Count"].mean().sort_values(ascending=False).head(3)
                st.write("**Job examples in your data:** " + ", ".join(role_evidence.index.tolist()))
                st.caption(f"These examples appear in {len(evidence)} records from {evidence['Source'].nunique()} source(s). This shows what the file contains, not how likely you are to get one of these jobs.")
            st.divider()

    st.info("This interest match uses clear subject-and-activity rules. It is not a machine-learning aptitude test: the project data has no student marks, skills, qualifications or past student placement outcomes to train that kind of model.")
    st.markdown("**Good next steps**: choose one school subject to explore more, try a small project or club activity, and discuss course options with a teacher or counsellor.")

with data_tab:
    st.subheader("What this project can and cannot show")
    st.write("The dashboard uses a small historical file. Here is the information it contains and the information we still need to add to answer every project question fully.")
    coverage = pd.DataFrame([
        ["Multi-sector, multi-source job trends", "Available", "Naukri and Foundit records; sectors, roles, years and cities."],
        ["Hiring and salary patterns", "Available with limits", "Hiring and salary figures exist, but salary units and consistent yearly sampling are not documented."],
        ["Future work-area trend", "Experimental", "A simple linear model sketches a direction from the available years; it is not validated as a reliable forecast."],
        ["Future salary estimate", "Not in this file", "Historical salary values can be compared, but a reliable salary forecast needs consistent salary observations over time."],
        ["Skills employers request", "Not in this file", "Add a Skills field from job postings before showing skill-demand rankings."],
        ["Qualifications employers request", "Not in this file", "Add education / qualification requirements linked to each job record."],
        ["Student placement chance, offers or time to job", "Not in this file", "Needs anonymised student profiles and outcomes (for example marks, skills, projects, internships, placed/not placed, offers, salary and time to placement)."],
        ["Course ideas for Class 9–10", "Interest guide included", "Suggestions are transparent subject-and-interest matches, not a trained student prediction model."],
        ["Automation and macroeconomic effects", "Not in this file", "Needs automation / skill information and economic indicators over time."],
    ], columns=["Project feature", "Status", "What the data supports"])
    st.dataframe(coverage, width="stretch", hide_index=True)

    st.subheader("Where these records came from")
    source_counts = df.groupby("Source", as_index=False).size().rename(columns={"size": "Records"})
    st.dataframe(source_counts, width="stretch", hide_index=True)
    st.caption(f"The file has {len(df):,} rows, {df['Sector'].nunique()} work areas, {df['Job_Role'].nunique()} job titles, and years {int(df['Year'].min())}–{int(df['Year'].max())}. It is a sample, not the complete Indian job market.")

    with st.expander("Browse or download the selected records"):
        query = st.text_input("Search jobs, companies, cities or work areas", key="data_search")
        table = view.copy()
        if query.strip():
            match = table.astype(str).apply(lambda col: col.str.contains(query.strip(), case=False, na=False)).any(axis=1)
            table = table[match]
        st.download_button("Download selected rows as CSV", table.to_csv(index=False).encode("utf-8-sig"),
                           file_name="selected_hiring_records.csv", mime="text/csv")
        st.dataframe(table, width="stretch", hide_index=True, height=420)

st.divider()
st.caption("Future Pathways · Historical employment exploration for students and career conversations")

