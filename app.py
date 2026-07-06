"""
Airline Revenue & Profitability Analysis System
Run with: streamlit run app.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from database import DB_PATH, AIRLINES, AIRCRAFT, init_db, get_connection, insert_flight, reset_database

st.set_page_config(
    page_title="Airline Revenue & Profitability Analysis",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #666;
        font-size: 1.05rem;
        margin-bottom: 1.1rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.75rem;
    }
    .note-box {
        background: #f7f7f9;
        border: 1px solid #e8e8ef;
        border-radius: 12px;
        padding: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Database + data functions
# -----------------------------
init_db(seed_if_empty=True)


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    query = """
        SELECT
            f.flight_id,
            f.flight_date,
            f.airline,
            f.route_id,
            r.origin_code,
            r.destination_code,
            r.origin_code || '-' || r.destination_code AS route,
            r.distance_km,
            r.route_type,
            f.aircraft_type,
            f.seat_capacity,
            f.passengers,
            f.avg_fare,
            f.ancillary_revenue,
            f.cargo_revenue,
            f.fuel_cost,
            f.crew_cost,
            f.maintenance_cost,
            f.airport_fees,
            f.leasing_cost,
            f.other_cost,
            f.delay_minutes,
            f.cancelled,
            f.created_at
        FROM flight_financials f
        JOIN routes r ON f.route_id = r.route_id
        ORDER BY f.flight_date;
    """
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn)
    if df.empty:
        return df
    df["flight_date"] = pd.to_datetime(df["flight_date"])
    df["month"] = df["flight_date"].dt.to_period("M").astype(str)
    df["year"] = df["flight_date"].dt.year
    return add_calculated_columns(df)


@st.cache_data(show_spinner=False)
def load_routes() -> pd.DataFrame:
    with get_connection() as conn:
        routes = pd.read_sql_query(
            "SELECT route_id, origin_code || '-' || destination_code AS route, distance_km, route_type FROM routes ORDER BY route;",
            conn,
        )
    return routes


def safe_divide(numerator, denominator):
    return np.where(np.asarray(denominator) == 0, 0, np.asarray(numerator) / np.asarray(denominator))


def add_calculated_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["passenger_revenue"] = df["passengers"] * df["avg_fare"]
    df["total_revenue"] = df["passenger_revenue"] + df["ancillary_revenue"] + df["cargo_revenue"]

    cost_cols = ["fuel_cost", "crew_cost", "maintenance_cost", "airport_fees", "leasing_cost", "other_cost"]
    df["total_cost"] = df[cost_cols].sum(axis=1)
    df["operating_profit"] = df["total_revenue"] - df["total_cost"]
    df["profit_margin_pct"] = safe_divide(df["operating_profit"], df["total_revenue"]) * 100

    df["load_factor_pct"] = safe_divide(df["passengers"], df["seat_capacity"]) * 100
    df["available_seat_km"] = df["seat_capacity"] * df["distance_km"]
    df["revenue_passenger_km"] = df["passengers"] * df["distance_km"]

    df["rask"] = safe_divide(df["total_revenue"], df["available_seat_km"])
    df["cask"] = safe_divide(df["total_cost"], df["available_seat_km"])
    df["yield_per_rpk"] = safe_divide(df["passenger_revenue"], df["revenue_passenger_km"])

    revenue_per_seat_at_full_capacity = df["avg_fare"] + safe_divide(df["ancillary_revenue"], df["seat_capacity"])
    df["break_even_load_factor_pct"] = safe_divide(df["total_cost"] - df["cargo_revenue"], df["seat_capacity"] * revenue_per_seat_at_full_capacity) * 100
    df["break_even_load_factor_pct"] = df["break_even_load_factor_pct"].clip(lower=0, upper=200)

    df["profit_status"] = np.where(df["operating_profit"] >= 0, "Profitable", "Loss-making")
    return df


def money(value: float) -> str:
    value = float(value)
    abs_value = abs(value)
    sign = "-" if value < 0 else ""
    if abs_value >= 10_000_000:
        return f"{sign}₹{abs_value / 10_000_000:.2f} Cr"
    if abs_value >= 100_000:
        return f"{sign}₹{abs_value / 100_000:.2f} L"
    return f"{sign}₹{abs_value:,.0f}"


def number(value: float) -> str:
    return f"{value:,.0f}"


def percent(value: float) -> str:
    return f"{value:.2f}%"


def filter_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")

    min_date = df["flight_date"].min().date()
    max_date = df["flight_date"].max().date()
    date_range = st.sidebar.date_input(
        "Flight date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = min_date, max_date

    airlines = st.sidebar.multiselect("Airline", sorted(df["airline"].unique()), default=sorted(df["airline"].unique()))
    route_types = st.sidebar.multiselect("Route type", sorted(df["route_type"].unique()), default=sorted(df["route_type"].unique()))
    routes = st.sidebar.multiselect("Route", sorted(df["route"].unique()), default=sorted(df["route"].unique()))
    aircraft = st.sidebar.multiselect("Aircraft", sorted(df["aircraft_type"].unique()), default=sorted(df["aircraft_type"].unique()))
    include_cancelled = st.sidebar.checkbox("Include cancelled flights", value=True)

    mask = (
        (df["flight_date"].dt.date >= start_date)
        & (df["flight_date"].dt.date <= end_date)
        & (df["airline"].isin(airlines))
        & (df["route_type"].isin(route_types))
        & (df["route"].isin(routes))
        & (df["aircraft_type"].isin(aircraft))
    )
    if not include_cancelled:
        mask &= df["cancelled"] == 0
    return df.loc[mask].copy()


def kpi_row(df: pd.DataFrame) -> None:
    total_revenue = df["total_revenue"].sum()
    total_cost = df["total_cost"].sum()
    profit = df["operating_profit"].sum()
    margin = (profit / total_revenue * 100) if total_revenue else 0
    load_factor = df["passengers"].sum() / df["seat_capacity"].sum() * 100 if df["seat_capacity"].sum() else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Revenue", money(total_revenue))
    c2.metric("Total Cost", money(total_cost))
    c3.metric("Operating Profit", money(profit), delta=money(profit))
    c4.metric("Profit Margin", percent(margin))
    c5.metric("Avg Load Factor", percent(load_factor))


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("month", as_index=False)
        .agg(
            total_revenue=("total_revenue", "sum"),
            passenger_revenue=("passenger_revenue", "sum"),
            ancillary_revenue=("ancillary_revenue", "sum"),
            cargo_revenue=("cargo_revenue", "sum"),
            total_cost=("total_cost", "sum"),
            operating_profit=("operating_profit", "sum"),
            passengers=("passengers", "sum"),
            seat_capacity=("seat_capacity", "sum"),
            avg_delay=("delay_minutes", "mean"),
        )
        .assign(
            profit_margin_pct=lambda x: safe_divide(x["operating_profit"], x["total_revenue"]) * 100,
            load_factor_pct=lambda x: safe_divide(x["passengers"], x["seat_capacity"]) * 100,
        )
    )


def route_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["route", "route_type", "distance_km"], as_index=False)
        .agg(
            flights=("flight_id", "count"),
            total_revenue=("total_revenue", "sum"),
            total_cost=("total_cost", "sum"),
            operating_profit=("operating_profit", "sum"),
            passengers=("passengers", "sum"),
            seat_capacity=("seat_capacity", "sum"),
            avg_fare=("avg_fare", "mean"),
            avg_delay=("delay_minutes", "mean"),
        )
        .assign(
            profit_margin_pct=lambda x: safe_divide(x["operating_profit"], x["total_revenue"]) * 100,
            load_factor_pct=lambda x: safe_divide(x["passengers"], x["seat_capacity"]) * 100,
            revenue_per_flight=lambda x: safe_divide(x["total_revenue"], x["flights"]),
            profit_per_flight=lambda x: safe_divide(x["operating_profit"], x["flights"]),
        )
    )


# -----------------------------
# App layout
# -----------------------------
df_all = load_data()

if df_all.empty:
    st.error("No records found in the database. Use the Database Manager page to reset sample data.")
    st.stop()

st.sidebar.title("✈️ Airline Analytics")
page = st.sidebar.radio(
    "Dashboard page",
    [
        "Executive Dashboard",
        "Revenue Analysis",
        "Profitability Analysis",
        "Route & Flight Performance",
        "Database Manager",
    ],
)

filtered = filter_dataframe(df_all)

st.markdown('<div class="main-header">Airline Revenue & Profitability Analysis</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Analyze airline revenue streams, cost structure, route profitability, load factor, RASK, CASK, and operating margin from an SQLite database.</div>',
    unsafe_allow_html=True,
)

if filtered.empty:
    st.warning("No data matches the selected filters. Change the filters in the sidebar.")
    st.stop()

# -----------------------------
# Page 1: Executive Dashboard
# -----------------------------
if page == "Executive Dashboard":
    kpi_row(filtered)
    st.divider()

    monthly = monthly_summary(filtered)
    routes = route_summary(filtered)

    c1, c2 = st.columns((1.6, 1))
    with c1:
        chart_df = monthly.melt(
            id_vars="month",
            value_vars=["total_revenue", "total_cost", "operating_profit"],
            var_name="metric",
            value_name="amount",
        )
        fig = px.line(chart_df, x="month", y="amount", color="metric", markers=True, title="Monthly Revenue, Cost and Profit")
        fig.update_layout(yaxis_title="Amount (₹)", xaxis_title="Month")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        mix = pd.DataFrame(
            {
                "Revenue Source": ["Passenger Revenue", "Ancillary Revenue", "Cargo Revenue"],
                "Amount": [
                    filtered["passenger_revenue"].sum(),
                    filtered["ancillary_revenue"].sum(),
                    filtered["cargo_revenue"].sum(),
                ],
            }
        )
        fig = px.pie(mix, names="Revenue Source", values="Amount", title="Revenue Mix")
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        top_routes = routes.sort_values("operating_profit", ascending=False).head(10)
        fig = px.bar(top_routes, x="route", y="operating_profit", title="Top 10 Routes by Operating Profit")
        fig.update_layout(yaxis_title="Operating Profit (₹)", xaxis_title="Route")
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        airline_summary = (
            filtered.groupby("airline", as_index=False)
            .agg(total_revenue=("total_revenue", "sum"), operating_profit=("operating_profit", "sum"), passengers=("passengers", "sum"))
            .assign(profit_margin_pct=lambda x: safe_divide(x["operating_profit"], x["total_revenue"]) * 100)
        )
        fig = px.scatter(
            airline_summary,
            x="total_revenue",
            y="profit_margin_pct",
            size="passengers",
            hover_name="airline",
            title="Airline Revenue vs Profit Margin",
        )
        fig.update_layout(xaxis_title="Total Revenue (₹)", yaxis_title="Profit Margin (%)")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Key Insights")
    best_route = routes.sort_values("operating_profit", ascending=False).iloc[0]
    worst_route = routes.sort_values("operating_profit", ascending=True).iloc[0]
    best_month = monthly.sort_values("operating_profit", ascending=False).iloc[0]
    st.markdown(
        f"""
        <div class="note-box">
        <b>Most profitable route:</b> {best_route['route']} with {money(best_route['operating_profit'])} operating profit.<br>
        <b>Weakest route:</b> {worst_route['route']} with {money(worst_route['operating_profit'])} operating profit.<br>
        <b>Best month:</b> {best_month['month']} with {money(best_month['operating_profit'])} operating profit.<br>
        <b>Main interpretation:</b> profit improves when load factor, average fare, and ancillary revenue rise faster than fuel, airport, leasing, and maintenance costs.
        </div>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------
# Page 2: Revenue Analysis
# -----------------------------
elif page == "Revenue Analysis":
    kpi_row(filtered)
    st.divider()
    monthly = monthly_summary(filtered)

    revenue_long = monthly.melt(
        id_vars="month",
        value_vars=["passenger_revenue", "ancillary_revenue", "cargo_revenue"],
        var_name="revenue_source",
        value_name="amount",
    )
    fig = px.bar(revenue_long, x="month", y="amount", color="revenue_source", title="Monthly Revenue by Source")
    fig.update_layout(xaxis_title="Month", yaxis_title="Revenue (₹)")
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        fare_df = filtered.groupby(["airline", "route_type"], as_index=False).agg(avg_fare=("avg_fare", "mean"))
        fig = px.bar(fare_df, x="airline", y="avg_fare", color="route_type", barmode="group", title="Average Fare by Airline")
        fig.update_layout(yaxis_title="Average Fare (₹)")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig = px.scatter(
            filtered,
            x="load_factor_pct",
            y="total_revenue",
            color="route_type",
            size="distance_km",
            hover_data=["airline", "route", "aircraft_type", "avg_fare"],
            title="Load Factor vs Total Revenue",
        )
        fig.update_layout(xaxis_title="Load Factor (%)", yaxis_title="Revenue (₹)")
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        ancillary = (
            filtered.groupby("route", as_index=False)
            .agg(ancillary_revenue=("ancillary_revenue", "sum"), passengers=("passengers", "sum"))
            .assign(ancillary_per_passenger=lambda x: safe_divide(x["ancillary_revenue"], x["passengers"]))
            .sort_values("ancillary_per_passenger", ascending=False)
            .head(10)
        )
        fig = px.bar(ancillary, x="route", y="ancillary_per_passenger", title="Top Routes by Ancillary Revenue per Passenger")
        fig.update_layout(yaxis_title="Ancillary Revenue per Passenger (₹)")
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        cargo = filtered.groupby("route", as_index=False).agg(cargo_revenue=("cargo_revenue", "sum")).sort_values("cargo_revenue", ascending=False).head(10)
        fig = px.bar(cargo, x="route", y="cargo_revenue", title="Top Routes by Cargo Revenue")
        fig.update_layout(yaxis_title="Cargo Revenue (₹)")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Revenue Formula Used")
    st.code(
        "Passenger Revenue = Passengers × Average Fare\n"
        "Total Revenue = Passenger Revenue + Ancillary Revenue + Cargo Revenue\n"
        "Load Factor (%) = Passengers ÷ Seat Capacity × 100"
    )

# -----------------------------
# Page 3: Profitability Analysis
# -----------------------------
elif page == "Profitability Analysis":
    kpi_row(filtered)
    st.divider()

    cost_cols = ["fuel_cost", "crew_cost", "maintenance_cost", "airport_fees", "leasing_cost", "other_cost"]
    cost_breakdown = pd.DataFrame({"Cost Type": cost_cols, "Amount": [filtered[c].sum() for c in cost_cols]})
    cost_breakdown["Cost Type"] = cost_breakdown["Cost Type"].str.replace("_", " ").str.title()

    c1, c2 = st.columns((1, 1.4))
    with c1:
        fig = px.pie(cost_breakdown, names="Cost Type", values="Amount", title="Cost Breakdown")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        aircraft_profit = (
            filtered.groupby("aircraft_type", as_index=False)
            .agg(total_revenue=("total_revenue", "sum"), total_cost=("total_cost", "sum"), operating_profit=("operating_profit", "sum"), ask=("available_seat_km", "sum"))
            .assign(rask=lambda x: safe_divide(x["total_revenue"], x["ask"]), cask=lambda x: safe_divide(x["total_cost"], x["ask"]))
        )
        aircraft_long = aircraft_profit.melt(id_vars="aircraft_type", value_vars=["rask", "cask"], var_name="metric", value_name="value")
        fig = px.bar(aircraft_long, x="aircraft_type", y="value", color="metric", barmode="group", title="RASK vs CASK by Aircraft")
        fig.update_layout(yaxis_title="₹ per Available Seat-Km", xaxis_title="Aircraft")
        st.plotly_chart(fig, use_container_width=True)

    routes = route_summary(filtered)
    c3, c4 = st.columns(2)
    with c3:
        top_margin = routes.sort_values("profit_margin_pct", ascending=False).head(10)
        fig = px.bar(top_margin, x="route", y="profit_margin_pct", title="Top Routes by Profit Margin")
        fig.update_layout(yaxis_title="Profit Margin (%)")
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        bottom_margin = routes.sort_values("profit_margin_pct", ascending=True).head(10)
        fig = px.bar(bottom_margin, x="route", y="profit_margin_pct", title="Lowest Routes by Profit Margin")
        fig.update_layout(yaxis_title="Profit Margin (%)")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Profitability Table")
    display_cols = [
        "route", "route_type", "flights", "total_revenue", "total_cost", "operating_profit",
        "profit_margin_pct", "load_factor_pct", "avg_fare", "avg_delay"
    ]
    st.dataframe(
        routes[display_cols].sort_values("operating_profit", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Profitability Formula Used")
    st.code(
        "Total Cost = Fuel + Crew + Maintenance + Airport Fees + Leasing + Other Costs\n"
        "Operating Profit = Total Revenue - Total Cost\n"
        "Profit Margin (%) = Operating Profit ÷ Total Revenue × 100\n"
        "RASK = Total Revenue ÷ Available Seat Kilometres\n"
        "CASK = Total Cost ÷ Available Seat Kilometres"
    )

# -----------------------------
# Page 4: Route & Flight Performance
# -----------------------------
elif page == "Route & Flight Performance":
    kpi_row(filtered)
    st.divider()

    routes = route_summary(filtered)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.scatter(
            routes,
            x="distance_km",
            y="profit_margin_pct",
            size="total_revenue",
            color="route_type",
            hover_name="route",
            title="Route Distance vs Profit Margin",
        )
        fig.update_layout(xaxis_title="Distance (km)", yaxis_title="Profit Margin (%)")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        delay_df = (
            filtered.assign(delay_bucket=pd.cut(filtered["delay_minutes"], bins=[-1, 0, 15, 30, 60, 500], labels=["0", "1-15", "16-30", "31-60", "60+"]))
            .groupby("delay_bucket", observed=False, as_index=False)
            .agg(avg_profit=("operating_profit", "mean"), flights=("flight_id", "count"))
        )
        fig = px.bar(delay_df, x="delay_bucket", y="avg_profit", title="Average Profit by Delay Bucket")
        fig.update_layout(xaxis_title="Delay Minutes", yaxis_title="Average Profit per Flight (₹)")
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        lf_df = filtered.groupby("route", as_index=False).agg(load_factor_pct=("load_factor_pct", "mean"), flights=("flight_id", "count")).sort_values("load_factor_pct", ascending=False).head(10)
        fig = px.bar(lf_df, x="route", y="load_factor_pct", title="Top Routes by Average Load Factor")
        fig.update_layout(yaxis_title="Load Factor (%)")
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        aircraft_df = (
            filtered.groupby("aircraft_type", as_index=False)
            .agg(flights=("flight_id", "count"), passengers=("passengers", "sum"), revenue=("total_revenue", "sum"), profit=("operating_profit", "sum"), load_factor_pct=("load_factor_pct", "mean"))
            .sort_values("profit", ascending=False)
        )
        fig = px.bar(aircraft_df, x="aircraft_type", y="profit", title="Aircraft Type by Operating Profit")
        fig.update_layout(yaxis_title="Operating Profit (₹)")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Filtered Flight Records")
    show_cols = [
        "flight_id", "flight_date", "airline", "route", "route_type", "aircraft_type",
        "seat_capacity", "passengers", "load_factor_pct", "avg_fare", "total_revenue",
        "total_cost", "operating_profit", "profit_margin_pct", "delay_minutes", "cancelled"
    ]
    st.dataframe(filtered[show_cols].sort_values("flight_date", ascending=False), use_container_width=True, hide_index=True)

# -----------------------------
# Page 5: Database Manager
# -----------------------------
elif page == "Database Manager":
    st.subheader("Database Details")
    c1, c2, c3 = st.columns(3)
    c1.metric("Database File", DB_PATH.name)
    c2.metric("Total Records", number(len(df_all)))
    c3.metric("Filtered Records", number(len(filtered)))

    with st.expander("View database schema"):
        st.code(
            """
Tables:
1. airports
   - airport_code, airport_name, city, country

2. routes
   - route_id, origin_code, destination_code, distance_km, route_type

3. flight_financials
   - flight_id, flight_date, airline, route_id, aircraft_type, seat_capacity,
     passengers, avg_fare, ancillary_revenue, cargo_revenue,
     fuel_cost, crew_cost, maintenance_cost, airport_fees,
     leasing_cost, other_cost, delay_minutes, cancelled
            """
        )

    st.divider()
    st.subheader("Add a New Flight Record")
    routes_lookup = load_routes()

    with st.form("add_flight_form"):
        c1, c2, c3 = st.columns(3)
        flight_date = c1.date_input("Flight date", value=date.today())
        airline = c2.selectbox("Airline", AIRLINES)
        route_label = c3.selectbox("Route", routes_lookup["route"].tolist())
        route_id = int(routes_lookup.loc[routes_lookup["route"] == route_label, "route_id"].iloc[0])

        c4, c5, c6 = st.columns(3)
        aircraft_type = c4.selectbox("Aircraft type", list(AIRCRAFT.keys()))
        default_capacity = AIRCRAFT[aircraft_type]
        seat_capacity = c5.number_input("Seat capacity", min_value=50, max_value=450, value=int(default_capacity), step=1)
        passengers = c6.number_input("Passengers", min_value=0, max_value=int(seat_capacity), value=int(seat_capacity * 0.78), step=1)

        c7, c8, c9 = st.columns(3)
        avg_fare = c7.number_input("Average fare per passenger (₹)", min_value=0.0, value=6500.0, step=100.0)
        ancillary_revenue = c8.number_input("Ancillary revenue (₹)", min_value=0.0, value=85000.0, step=5000.0)
        cargo_revenue = c9.number_input("Cargo revenue (₹)", min_value=0.0, value=60000.0, step=5000.0)

        c10, c11, c12 = st.columns(3)
        fuel_cost = c10.number_input("Fuel cost (₹)", min_value=0.0, value=320000.0, step=10000.0)
        crew_cost = c11.number_input("Crew cost (₹)", min_value=0.0, value=85000.0, step=5000.0)
        maintenance_cost = c12.number_input("Maintenance cost (₹)", min_value=0.0, value=70000.0, step=5000.0)

        c13, c14, c15 = st.columns(3)
        airport_fees = c13.number_input("Airport fees (₹)", min_value=0.0, value=120000.0, step=5000.0)
        leasing_cost = c14.number_input("Leasing cost (₹)", min_value=0.0, value=130000.0, step=5000.0)
        other_cost = c15.number_input("Other cost (₹)", min_value=0.0, value=45000.0, step=5000.0)

        c16, c17 = st.columns(2)
        delay_minutes = c16.number_input("Delay minutes", min_value=0, max_value=500, value=0, step=1)
        cancelled = c17.checkbox("Cancelled flight")

        submitted = st.form_submit_button("Save record to database")

    if submitted:
        record = {
            "flight_date": flight_date.isoformat(),
            "airline": airline,
            "route_id": route_id,
            "aircraft_type": aircraft_type,
            "seat_capacity": int(seat_capacity),
            "passengers": int(passengers),
            "avg_fare": float(avg_fare),
            "ancillary_revenue": float(ancillary_revenue),
            "cargo_revenue": float(cargo_revenue),
            "fuel_cost": float(fuel_cost),
            "crew_cost": float(crew_cost),
            "maintenance_cost": float(maintenance_cost),
            "airport_fees": float(airport_fees),
            "leasing_cost": float(leasing_cost),
            "other_cost": float(other_cost),
            "delay_minutes": int(delay_minutes),
            "cancelled": 1 if cancelled else 0,
        }
        insert_flight(record)
        st.cache_data.clear()
        st.success("Record saved successfully. Refreshing data...")
        st.rerun()

    st.divider()
    st.subheader("Download / Reset Data")
    c18, c19 = st.columns(2)
    csv = filtered.to_csv(index=False).encode("utf-8")
    c18.download_button(
        "Download filtered data as CSV",
        data=csv,
        file_name="airline_revenue_profitability_filtered.csv",
        mime="text/csv",
    )

    with c19:
        if st.button("Reset sample database", type="secondary"):
            reset_database()
            st.cache_data.clear()
            st.success("Sample database has been reset.")
            st.rerun()

    st.subheader("Latest Records")
    latest_cols = [
        "flight_id", "flight_date", "airline", "route", "aircraft_type", "passengers",
        "avg_fare", "total_revenue", "total_cost", "operating_profit", "profit_margin_pct"
    ]
    st.dataframe(df_all[latest_cols].sort_values("flight_id", ascending=False).head(20), use_container_width=True, hide_index=True)
