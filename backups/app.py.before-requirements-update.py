"""Refreshed Streamlit dashboard for historical placement and hiring data."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Hiring & Placement Insights",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAVY = "#14213D"
BLUE = "#3B82F6"
TEAL = "#14B8A6"
PALETTE = ["#3B82F6", "#14B8A6", "#8B5CF6", "#F59E0B", "#EF476F", "#06B6D4"]

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .stApp { background: #F5F7FB; }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] { background: #111C33; }
    [data-testid="stSidebar"] * { color: #E7ECF5; }
    [data-testid="stSidebar"] [data-baseweb="tag"] { background: #264267; }
    .hero { padding: 1.65rem 1.9rem; border-radius: 20px; color: white;
      background: linear-gradient(115deg, #14213D 0%, #1D3B67 58%, #167C80 100%);
      margin: .2rem 0 1.25rem; box-shadow: 0 12px 28px rgba(20,33,61,.15); }
    .hero h1 { font-family: 'Manrope', sans-serif; font-size: 2rem; margin: 0 0 .35rem; }
    .hero p { color: #D8E5F5; font-size: 1rem; margin: 0; }
    .eyebrow { text-transform: uppercase; letter-spacing: .13em; font-size: .72rem;
      color: #8FE6DC; font-weight: 700; margin-bottom: .45rem; }
    div[data-testid="stMetric"] { background: white; border: 1px solid #E6EAF1;
      padding: 1rem 1.15rem; border-radius: 16px; box-shadow: 0 4px 14px rgba(20,33,61,.04); }
    div[data-testid="stMetricLabel"] { color: #667085; }
    div[data-testid="stMetricValue"] { color: #14213D; font-family: 'Manrope', sans-serif; }
    h2, h3 { font-family: 'Manrope', sans-serif !important; color: #14213D; }
    .section-note { color: #667085; margin-top: -.65rem; margin-bottom: 1rem; }
    .stDownloadButton button { border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data(file_path: str) -> pd.DataFrame:
    data = pd.read_csv(file_path)
    data.columns = data.columns.str.strip()
    data = data.loc[:, ~data.columns.str.lower().str.startswith("unnamed")]
    numeric = [
        "Year", "Hiring_Count", "Hiring_Growth_%", "Placement_Count",
        "Average_Salary", "Source_Page",
    ]
    for column in numeric:
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    for column in data.select_dtypes(include="object"):
        data[column] = data[column].fillna("Unknown").astype(str).str.strip()
    return data


DATA_FILE = Path(__file__).resolve().with_name("hiring_data.csv")
if not DATA_FILE.exists():
    st.error(f"Could not find `{DATA_FILE.name}` beside this app.")
    st.info("Keep `hiring_data.csv` in the same folder as `app.py`.")
    st.stop()

df = load_data(str(DATA_FILE))
required = {"Year", "Sector", "Job_Role", "Hiring_Count", "Location"}
missing = sorted(required.difference(df.columns))
if missing:
    st.error("The data file is missing required columns: " + ", ".join(missing))
    st.stop()

for column in ["Hiring_Growth_%", "Placement_Count", "Average_Salary"]:
    if column not in df:
        df[column] = 0.0
if "Demand_Trend" not in df:
    df["Demand_Trend"] = "Unknown"
if "Month" not in df:
    df["Month"] = "Unknown"


def options_for(column: str) -> list:
    return sorted(df[column].dropna().unique().tolist(), key=str)


st.sidebar.markdown("## 🎛️ Explore the data")
st.sidebar.caption("Choose one or more values. Charts and insights update together.")
years = sorted(df["Year"].dropna().unique().tolist())
selected_years = st.sidebar.multiselect("Year", years, default=years)
selected_sectors = st.sidebar.multiselect("Sector", options_for("Sector"), default=options_for("Sector"))
selected_locations = st.sidebar.multiselect("Location", options_for("Location"), default=options_for("Location"))
selected_roles = st.sidebar.multiselect("Job role", options_for("Job_Role"), default=options_for("Job_Role"))

filtered = df[
    df["Year"].isin(selected_years)
    & df["Sector"].isin(selected_sectors)
    & df["Location"].isin(selected_locations)
    & df["Job_Role"].isin(selected_roles)
].copy()

st.sidebar.divider()
st.sidebar.caption(f"Showing **{len(filtered):,}** of {len(df):,} records")
if st.sidebar.button("Reset filters", use_container_width=True):
    st.rerun()

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Workforce intelligence · India</div>
      <h1>Hiring & Placement Insights</h1>
      <p>Explore demand, compensation and placement patterns across years, sectors and roles.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if filtered.empty:
    st.warning("No records match these filters. Broaden your selections in the sidebar.")
    st.stop()

total_hiring = filtered["Hiring_Count"].sum()
total_placements = filtered["Placement_Count"].sum()
mean_growth = filtered["Hiring_Growth_%"].mean()
median_salary = filtered["Average_Salary"].median()
top_sector = filtered.groupby("Sector")["Hiring_Count"].sum().idxmax()
top_sector_hiring = filtered.groupby("Sector")["Hiring_Count"].sum().max()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Hiring represented", f"{total_hiring:,.0f}", help="Sum of Hiring_Count in the selected records")
k2.metric("Placements", f"{total_placements:,.0f}")
k3.metric("Avg. growth", f"{mean_growth:+.1f}%" if pd.notna(mean_growth) else "—")
k4.metric("Median salary", f"{median_salary:,.1f}" if pd.notna(median_salary) else "—", help="Salary unit follows the source data")
k5.metric("Leading sector", str(top_sector), help=f"{top_sector_hiring:,.0f} hiring represented")

st.caption("Metrics reflect the selected records; salary units and hiring definitions follow the source dataset.")
overview_tab, roles_tab, career_tab, data_tab = st.tabs(
    ["📊 Overview", "💼 Roles & pay", "🎓 Career planner", "🧾 Data explorer"]
)

plot_config = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}

with overview_tab:
    st.subheader("Demand at a glance")
    st.markdown('<p class="section-note">Hover, zoom or use the legend to focus on a series.</p>', unsafe_allow_html=True)
    left, right = st.columns([1.55, 1])
    by_year_sector = filtered.groupby(["Year", "Sector"], as_index=False)["Hiring_Count"].sum()
    fig = px.line(by_year_sector, x="Year", y="Hiring_Count", color="Sector", markers=True,
                  color_discrete_sequence=PALETTE, labels={"Hiring_Count": "Hiring represented", "Year": "Year"})
    fig.update_layout(template="plotly_white", height=390, margin=dict(l=10, r=10, t=15, b=10),
                      hovermode="x unified", legend_title_text="Sector")
    left.plotly_chart(fig, use_container_width=True, config=plot_config)

    sector_mix = filtered.groupby("Sector", as_index=False)["Hiring_Count"].sum().sort_values("Hiring_Count", ascending=False)
    fig = px.pie(sector_mix, names="Sector", values="Hiring_Count", hole=.62,
                 color_discrete_sequence=PALETTE, title="Hiring mix by sector")
    fig.update_traces(textposition="outside", textinfo="percent+label", pull=[.04] + [0] * max(0, len(sector_mix) - 1))
    fig.update_layout(template="plotly_white", height=390, margin=dict(l=10, r=10, t=55, b=10), showlegend=False)
    right.plotly_chart(fig, use_container_width=True, config=plot_config)

    left, right = st.columns(2)
    growth = filtered.groupby("Year", as_index=False)["Hiring_Growth_%"].mean()
    fig = px.bar(growth, x="Year", y="Hiring_Growth_%", color="Hiring_Growth_%",
                 color_continuous_scale=["#EF476F", "#E8EDF5", "#14B8A6"],
                 labels={"Hiring_Growth_%": "Average growth (%)"}, title="Average hiring growth")
    fig.add_hline(y=0, line_dash="dot", line_color="#667085")
    fig.update_layout(template="plotly_white", height=340, margin=dict(l=10, r=10, t=50, b=10), coloraxis_showscale=False)
    left.plotly_chart(fig, use_container_width=True, config=plot_config)

    trend = filtered.groupby("Demand_Trend", as_index=False).size().rename(columns={"size": "Records"})
    fig = px.bar(trend, x="Demand_Trend", y="Records", color="Demand_Trend",
                 color_discrete_sequence=PALETTE, title="Records by demand trend")
    fig.update_layout(template="plotly_white", height=340, margin=dict(l=10, r=10, t=50, b=10), showlegend=False)
    right.plotly_chart(fig, use_container_width=True, config=plot_config)

with roles_tab:
    st.subheader("Which roles stand out?")
    left, right = st.columns(2)
    role_summary = filtered.groupby("Job_Role", as_index=False).agg(
        Hiring_Count=("Hiring_Count", "sum"), Average_Salary=("Average_Salary", "mean"),
        Placement_Count=("Placement_Count", "sum"),
    )
    role_order = role_summary.nlargest(12, "Hiring_Count").sort_values("Hiring_Count")
    fig = px.bar(role_order, x="Hiring_Count", y="Job_Role", orientation="h", text_auto=".3s",
                 color="Hiring_Count", color_continuous_scale=["#A9D4FF", BLUE], title="Top roles by hiring")
    fig.update_layout(template="plotly_white", height=440, margin=dict(l=10, r=10, t=50, b=10), coloraxis_showscale=False)
    left.plotly_chart(fig, use_container_width=True, config=plot_config)

    pay = role_summary.nlargest(12, "Average_Salary").sort_values("Average_Salary")
    fig = px.bar(pay, x="Average_Salary", y="Job_Role", orientation="h", text_auto=".3s",
                 color="Average_Salary", color_continuous_scale=["#B7F0E8", TEAL], title="Highest average salary by role")
    fig.update_layout(template="plotly_white", height=440, margin=dict(l=10, r=10, t=50, b=10), coloraxis_showscale=False)
    right.plotly_chart(fig, use_container_width=True, config=plot_config)

    scatter_data = filtered.dropna(subset=["Average_Salary", "Hiring_Count"])
    fig = px.scatter(scatter_data, x="Average_Salary", y="Hiring_Count", color="Sector", size="Placement_Count",
                     hover_name="Job_Role", hover_data=["Year", "Location", "Company"],
                     color_discrete_sequence=PALETTE, title="Pay and hiring relationship",
                     labels={"Average_Salary": "Average salary (source unit)", "Hiring_Count": "Hiring represented"})
    fig.update_layout(template="plotly_white", height=420, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True, config=plot_config)

with career_tab:
    st.subheader("Explore a career path")
    st.markdown('<p class="section-note">Compare a role and location using the historical data in this dashboard.</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    all_roles = options_for("Job_Role")
    all_locations = options_for("Location")
    role_choice = c1.selectbox("Choose a job role", all_roles, key="career_role")
    location_choice = c2.selectbox("Preferred location", all_locations, key="career_location")
    role_df = df[df["Job_Role"] == role_choice]
    matched = role_df[role_df["Location"] == location_choice]
    career_df = matched if not matched.empty else role_df
    used_fallback = matched.empty
    hiring_avg = career_df["Hiring_Count"].mean()
    salary_avg = career_df["Average_Salary"].mean()
    placement_avg = career_df["Placement_Count"].mean()
    # A relative indicator across roles, not a probability or a guarantee of employment.
    def relative_score(value: float, population: pd.Series) -> float:
        max_value = population.max()
        return 0.0 if pd.isna(value) or pd.isna(max_value) or max_value <= 0 else min(1.0, value / max_value)
    score = 100 * (
        .45 * relative_score(hiring_avg, df.groupby("Job_Role")["Hiring_Count"].mean())
        + .30 * relative_score(salary_avg, df.groupby("Job_Role")["Average_Salary"].mean())
        + .25 * relative_score(placement_avg, df.groupby("Job_Role")["Placement_Count"].mean())
    )
    if used_fallback:
        st.info(f"No records for **{role_choice}** in **{location_choice}**; showing role-wide history.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Historical market indicator", f"{score:.0f}/100")
    m2.metric("Average hiring", f"{hiring_avg:,.0f}" if pd.notna(hiring_avg) else "—")
    m3.metric("Average salary", f"{salary_avg:,.1f}" if pd.notna(salary_avg) else "—")
    m4.metric("Placements represented", f"{placement_avg:,.0f}" if pd.notna(placement_avg) else "—")
    st.progress(int(score))
    st.caption("Relative score compares this role’s historical hiring, salary and placements with roles in the full dataset. It is an exploratory indicator, not a job-outcome prediction.")
    history = role_df.groupby("Year", as_index=False).agg(Hiring_Count=("Hiring_Count", "sum"), Hiring_Growth=("Hiring_Growth_%", "mean"))
    fig = px.line(history, x="Year", y="Hiring_Count", markers=True, color_discrete_sequence=[BLUE],
                  labels={"Hiring_Count": "Hiring represented"}, title=f"Hiring history · {role_choice}")
    fig.update_layout(template="plotly_white", height=360, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True, config=plot_config)

with data_tab:
    st.subheader("Filtered records")
    st.markdown('<p class="section-note">Inspect and download the exact rows behind the charts.</p>', unsafe_allow_html=True)
    search = st.text_input("Search visible rows", placeholder="Search company, role, sector, location…")
    view = filtered.copy()
    if search.strip():
        mask = view.astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, na=False)).any(axis=1)
        view = view[mask]
    st.download_button(
        "⬇️ Download filtered data (CSV)",
        data=view.to_csv(index=False).encode("utf-8-sig"),
        file_name="filtered_hiring_placement_data.csv",
        mime="text/csv",
        use_container_width=False,
    )
    st.dataframe(view, use_container_width=True, hide_index=True, height=520)
    with st.expander("About this dataset"):
        st.write(f"**Rows:** {len(df):,} · **Years:** {int(df['Year'].min())}–{int(df['Year'].max())} · **Fields:** {len(df.columns)}")
        st.caption("Values summarize the supplied hiring_data.csv. Check the source and source page fields before treating a figure as a verified count or forecast.")

st.divider()
st.caption("Historical Placement & Hiring · Interactive analysis powered by Streamlit and Plotly")
