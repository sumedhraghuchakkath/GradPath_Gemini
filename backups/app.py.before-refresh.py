# ============================================================
# HISTORICAL PLACEMENT & HIRING DASHBOARD
# STREAMLIT WEB APPLICATION
# ============================================================

import os
import pandas as pd
import streamlit as st
import plotly.express as px


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Historical Placement & Hiring",
    page_icon="📊",
    layout="wide"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 42px;
        font-weight: 800;
        margin-bottom: 5px;
    }

    .subtitle {
        font-size: 18px;
        color: #666;
        margin-bottom: 30px;
    }

    .metric-card {
        padding: 20px;
        border-radius: 15px;
        background-color: #f7f9fc;
        border: 1px solid #e5e7eb;
        text-align: center;
    }

    .metric-title {
        font-size: 15px;
        color: #666;
    }

    .metric-value {
        font-size: 30px;
        font-weight: 700;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# STEP 1: FIND DATASET
# ============================================================

# Get the folder where this app.py file is located.

APP_FOLDER = os.path.dirname(
    os.path.abspath(__file__)
)

CSV_FILE = os.path.join(
    APP_FOLDER,
    "hiring_data.csv"
)


# ============================================================
# STEP 2: LOAD DATASET
# ============================================================

@st.cache_data
def load_data():

    if not os.path.exists(CSV_FILE):

        return None

    data = pd.read_csv(
        CSV_FILE
    )

    # Clean column names
    data.columns = (
        data.columns
        .str.strip()
    )

    # Remove unnecessary index column
    if "index" in data.columns:

        data = data.drop(
            columns=["index"]
        )

    # Convert numeric columns
    numeric_columns = [
        "Year",
        "Hiring_Count",
        "Hiring_Growth_%",
        "Placement_Count",
        "Average_Salary",
        "Source_Page"
    ]

    for column in numeric_columns:

        if column in data.columns:

            data[column] = pd.to_numeric(
                data[column],
                errors="coerce"
            )

    # Clean text columns
    text_columns = [
        "Month",
        "Sector",
        "Job_Role",
        "Company",
        "Location",
        "Demand_Trend",
        "Source"
    ]

    for column in text_columns:

        if column in data.columns:

            data[column] = (
                data[column]
                .astype(str)
                .str.strip()
            )

    return data


df = load_data()


# ============================================================
# STEP 3: CHECK DATASET
# ============================================================

if df is None:

    st.error(
        "❌ hiring_data.csv was not found."
    )

    st.info(
        f"""
        Put **hiring_data.csv** in the same folder as app.py.

        Current folder:

        `{APP_FOLDER}`
        """
    )

    st.stop()


# ============================================================
# CHECK REQUIRED COLUMNS
# ============================================================

required_columns = [
    "Year",
    "Sector",
    "Job_Role",
    "Hiring_Count",
    "Average_Salary",
    "Location",
    "Demand_Trend"
]

missing_columns = [
    column
    for column in required_columns
    if column not in df.columns
]

if missing_columns:

    st.error(
        "The following required columns are missing:"
    )

    st.write(
        missing_columns
    )

    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title(
    "🎛️ Dashboard Filters"
)

st.sidebar.markdown(
    "Use the filters below to explore the hiring data."
)


# ------------------------------------------------------------
# YEAR FILTER
# ------------------------------------------------------------

years = sorted(
    df["Year"]
    .dropna()
    .unique()
)

selected_years = st.sidebar.multiselect(

    "📅 Select Year",

    options=years,

    default=years
)


# ------------------------------------------------------------
# SECTOR FILTER
# ------------------------------------------------------------

sectors = sorted(
    df["Sector"]
    .dropna()
    .unique()
)

selected_sectors = st.sidebar.multiselect(

    "🏢 Select Sector",

    options=sectors,

    default=sectors
)


# ------------------------------------------------------------
# LOCATION FILTER
# ------------------------------------------------------------

locations = sorted(
    df["Location"]
    .dropna()
    .unique()
)

selected_locations = st.sidebar.multiselect(

    "📍 Select Location",

    options=locations,

    default=locations
)


# ============================================================
# APPLY FILTERS
# ============================================================

filtered_df = df[
    df["Year"].isin(selected_years)
    &
    df["Sector"].isin(selected_sectors)
    &
    df["Location"].isin(selected_locations)
].copy()


# ============================================================
# MAIN TITLE
# ============================================================

st.markdown(
    '<div class="main-title">'
    '📊 Historical Placement & Hiring Dashboard'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Explore historical hiring patterns, demand trends, '
    'job roles, salaries and career opportunities.'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# CHECK FILTER RESULTS
# ============================================================

if filtered_df.empty:

    st.warning(
        "⚠️ No records match the selected filters."
    )

    st.stop()


# ============================================================
# KPI CALCULATIONS
# ============================================================

total_hiring = filtered_df[
    "Hiring_Count"
].sum()


top_sector = (
    filtered_df
    .groupby("Sector")["Hiring_Count"]
    .sum()
    .idxmax()
)


average_growth = filtered_df[
    "Hiring_Growth_%"
].mean()


total_placements = filtered_df[
    "Placement_Count"
].sum()


# ============================================================
# KPI CARDS
# ============================================================

col1, col2, col3, col4 = st.columns(4)


with col1:

    st.metric(
        "👥 Total Hiring",
        f"{total_hiring:,.0f}"
    )


with col2:

    st.metric(
        "🏆 Top Sector",
        top_sector
    )


with col3:

    st.metric(
        "📈 Average Growth",
        f"{average_growth:.2f}%"
    )


with col4:

    st.metric(
        "🎓 Total Placements",
        f"{total_placements:,.0f}"
    )


st.divider()


# ============================================================
# TABS
# ============================================================

dashboard_tab, career_tab = st.tabs(
    [
        "📊 Hiring Dashboard",
        "🎓 Student Career Calculator"
    ]
)


# ============================================================
# DASHBOARD TAB
# ============================================================

with dashboard_tab:

    # ========================================================
    # YEARLY HIRING TREND
    # ========================================================

    st.subheader(
        "📈 Year-over-Year Hiring Trend by Sector"
    )

    yearly_sector = (
        filtered_df
        .groupby(
            ["Year", "Sector"],
            as_index=False
        )["Hiring_Count"]
        .sum()
    )


    fig_year = px.line(

        yearly_sector,

        x="Year",

        y="Hiring_Count",

        color="Sector",

        markers=True,

        title="Hiring Trend Across Sectors",

        labels={
            "Hiring_Count": "Total Hiring",
            "Year": "Year"
        }
    )


    fig_year.update_layout(
        hovermode="x unified",
        height=500
    )


    st.plotly_chart(
        fig_year,
        use_container_width=True
    )


    # ========================================================
    # JOB ROLE + SALARY
    # ========================================================

    col1, col2 = st.columns(2)


    with col1:

        st.subheader(
            "💼 Top 10 Job Roles by Hiring"
        )


        top_roles = (
            filtered_df
            .groupby(
                "Job_Role",
                as_index=False
            )["Hiring_Count"]
            .sum()
            .sort_values(
                "Hiring_Count",
                ascending=False
            )
            .head(10)
        )


        fig_roles = px.bar(

            top_roles,

            x="Hiring_Count",

            y="Job_Role",

            orientation="h",

            title="Top 10 Job Roles",

            text="Hiring_Count",

            labels={
                "Hiring_Count": "Hiring Count",
                "Job_Role": "Job Role"
            }
        )


        fig_roles.update_layout(
            height=500,
            yaxis={
                "categoryorder": "total ascending"
            }
        )


        st.plotly_chart(
            fig_roles,
            use_container_width=True
        )


    # ========================================================
    # SALARY BY JOB ROLE
    # ========================================================

    with col2:

        st.subheader(
            "💰 Average Salary by Top Job Roles"
        )


        salary_roles = (
            filtered_df
            .groupby(
                "Job_Role",
                as_index=False
            )["Average_Salary"]
            .mean()
            .sort_values(
                "Average_Salary",
                ascending=False
            )
            .head(10)
        )


        fig_salary = px.bar(

            salary_roles,

            x="Average_Salary",

            y="Job_Role",

            orientation="h",

            title="Highest Average Salary",

            text="Average_Salary",

            labels={
                "Average_Salary":
                    "Average Salary",
                "Job_Role":
                    "Job Role"
            }
        )


        fig_salary.update_layout(
            height=500,
            yaxis={
                "categoryorder": "total ascending"
            }
        )


        st.plotly_chart(
            fig_salary,
            use_container_width=True
        )


    # ========================================================
    # LOCATION DISTRIBUTION
    # ========================================================

    st.subheader(
        "📍 Hiring Distribution by Location"
    )


    location_data = (
        filtered_df
        .groupby(
            "Location",
            as_index=False
        )["Hiring_Count"]
        .sum()
        .sort_values(
            "Hiring_Count",
            ascending=False
        )
    )


    fig_location = px.pie(

        location_data,

        names="Location",

        values="Hiring_Count",

        hole=0.35,

        title="Hiring Share by Location"
    )


    fig_location.update_traces(
        textposition="inside",
        textinfo="percent+label"
    )


    st.plotly_chart(
        fig_location,
        use_container_width=True
    )


    # ========================================================
    # DEMAND TREND
    # ========================================================

    st.subheader(
        "📊 Demand Trend Distribution"
    )


    trend_data = (
        filtered_df
        .groupby(
            "Demand_Trend",
            as_index=False
        )
        .size()
        .rename(
            columns={
                "size": "Records"
            }
        )
    )


    fig_trend = px.bar(

        trend_data,

        x="Demand_Trend",

        y="Records",

        color="Demand_Trend",

        title="Increasing vs Decreasing vs Stable"
    )


    fig_trend.update_layout(
        height=400
    )


    st.plotly_chart(
        fig_trend,
        use_container_width=True
    )


    # ========================================================
    # HIRING GROWTH
    # ========================================================

    st.subheader(
        "📈 Hiring Growth Percentage"
    )


    growth_data = (
        filtered_df
        .groupby(
            "Year",
            as_index=False
        )["Hiring_Growth_%"]
        .mean()
    )


    fig_growth = px.line(

        growth_data,

        x="Year",

        y="Hiring_Growth_%",

        markers=True,

        title="Average Hiring Growth by Year",

        labels={
            "Hiring_Growth_%":
                "Hiring Growth (%)"
        }
    )


    fig_growth.add_hline(
        y=0,
        line_dash="dash"
    )


    st.plotly_chart(
        fig_growth,
        use_container_width=True
    )


    # ========================================================
    # DATA TABLE
    # ========================================================

    with st.expander(
        "🔎 View Filtered Dataset"
    ):

        st.dataframe(
            filtered_df,
            use_container_width=True
        )


# ============================================================
# STUDENT CAREER CALCULATOR
# ============================================================

with career_tab:

    st.title(
        "🎓 Student Career Calculator"
    )

    st.write(
        """
        Select a job role and location to estimate its
        position in the historical hiring market.

        The score is based on hiring volume, salary,
        placement activity and demand trend in the dataset.
        """
    )


    # ========================================================
    # JOB ROLE INPUT
    # ========================================================

    available_roles = sorted(
        df["Job_Role"]
        .dropna()
        .unique()
    )


    selected_role = st.selectbox(

        "💼 Select your target Job Role",

        available_roles
    )


    # ========================================================
    # LOCATION INPUT
    # ========================================================

    available_locations = sorted(
        df["Location"]
        .dropna()
        .unique()
    )


    selected_location = st.selectbox(

        "📍 Preferred Location",

        available_locations
    )


    # ========================================================
    # FIND ROLE DATA
    # ========================================================

    role_data = df[
        df["Job_Role"] == selected_role
    ]


    location_role_data = df[
        (df["Job_Role"] == selected_role)
        &
        (df["Location"] == selected_location)
    ]


    # If there are no records for that exact role/location,
    # use role-level data.

    if not location_role_data.empty:

        career_data = location_role_data

    else:

        career_data = role_data


    # ========================================================
    # CALCULATE CAREER SCORE
    # ========================================================

    hiring_score = (
        career_data["Hiring_Count"]
        .mean()
    )


    salary_score = (
        career_data["Average_Salary"]
        .mean()
    )


    placement_score = (
        career_data["Placement_Count"]
        .mean()
    )


    # Normalize hiring

    max_hiring = df[
        "Hiring_Count"
    ].max()


    hiring_component = (
        hiring_score /
        max_hiring
    ) * 50


    # Normalize salary

    max_salary = df[
        "Average_Salary"
    ].max()


    salary_component = (
        salary_score /
        max_salary
    ) * 25


    # Normalize placements

    max_placements = df[
        "Placement_Count"
    ].max()


    placement_component = (
        placement_score /
        max_placements
    ) * 25


    career_score = (
        hiring_component
        +
        salary_component
        +
        placement_component
    )


    career_score = min(
        100,
        max(
            0,
            career_score
        )
    )


    # ========================================================
    # DISPLAY SCORE
    # ========================================================

    st.subheader(
        "📊 Your Job Market Score"
    )


    score_col1, score_col2 = st.columns(2)


    with score_col1:

        st.metric(
            "Career Demand Score",
            f"{career_score:.1f}/100"
        )


    with score_col2:

        latest_trend = (
            career_data
            ["Demand_Trend"]
            .mode()
        )


        if len(latest_trend) > 0:

            trend_result = latest_trend.iloc[0]

        else:

            trend_result = "Unknown"


        st.metric(
            "Market Trend",
            trend_result
        )


    # Progress bar

    st.progress(
        int(career_score)
    )


    # ========================================================
    # CAREER INTERPRETATION
    # ========================================================

    if career_score >= 75:

        st.success(
            "🔥 Excellent market opportunity! "
            "This role has strong historical demand."
        )

    elif career_score >= 50:

        st.info(
            "👍 Good market opportunity. "
            "Continue developing relevant skills."
        )

    elif career_score >= 25:

        st.warning(
            "⚠️ Moderate market opportunity. "
            "Consider strengthening your profile."
        )

    else:

        st.error(
            "📉 Low historical demand. "
            "Consider exploring related roles."
        )


    # ========================================================
    # ROLE STATISTICS
    # ========================================================

    st.subheader(
        "📌 Role Statistics"
    )


    stat1, stat2, stat3 = st.columns(3)


    with stat1:

        st.metric(
            "Average Hiring",
            f"{hiring_score:,.0f}"
        )


    with stat2:

        st.metric(
            "Average Salary",
            f"{salary_score:.1f}"
        )


    with stat3:

        st.metric(
            "Average Placements",
            f"{placement_score:,.0f}"
        )


    # ========================================================
    # ROLE HIRING HISTORY
    # ========================================================

    role_history = (
        role_data
        .groupby(
            "Year",
            as_index=False
        )["Hiring_Count"]
        .sum()
    )


    fig_role_history = px.line(

        role_history,

        x="Year",

        y="Hiring_Count",

        markers=True,

        title=f"Hiring History: {selected_role}"
    )


    st.plotly_chart(
        fig_role_history,
        use_container_width=True
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Historical Placement & Hiring Analysis | "
    "Python + Pandas + Plotly + Streamlit"
)