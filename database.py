"""
Database layer for Airline Revenue & Profitability Analysis System.
Uses SQLite so the project runs locally without MySQL/PostgreSQL setup.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import date, timedelta
import random
from typing import Iterable

DB_PATH = Path(__file__).resolve().parent / "airline_analysis.db"

AIRLINES = ["IndiGo", "Air India", "Vistara", "Akasa Air", "SpiceJet"]
AIRCRAFT = {
    "Airbus A320neo": 186,
    "Airbus A321neo": 232,
    "Boeing 737 MAX": 189,
    "Airbus A350": 316,
    "Boeing 787-8": 256,
}

AIRPORTS = [
    ("BLR", "Kempegowda International Airport", "Bengaluru", "India"),
    ("DEL", "Indira Gandhi International Airport", "Delhi", "India"),
    ("BOM", "Chhatrapati Shivaji Maharaj International Airport", "Mumbai", "India"),
    ("MAA", "Chennai International Airport", "Chennai", "India"),
    ("HYD", "Rajiv Gandhi International Airport", "Hyderabad", "India"),
    ("CCU", "Netaji Subhas Chandra Bose International Airport", "Kolkata", "India"),
    ("GOI", "Goa International Airport", "Goa", "India"),
    ("DXB", "Dubai International Airport", "Dubai", "UAE"),
    ("SIN", "Singapore Changi Airport", "Singapore", "Singapore"),
    ("LHR", "Heathrow Airport", "London", "United Kingdom"),
]

ROUTES = [
    ("BLR", "DEL", 1740, "Domestic"),
    ("BLR", "BOM", 840, "Domestic"),
    ("BLR", "MAA", 290, "Domestic"),
    ("DEL", "BOM", 1140, "Domestic"),
    ("DEL", "CCU", 1310, "Domestic"),
    ("BOM", "GOI", 425, "Domestic"),
    ("HYD", "DEL", 1260, "Domestic"),
    ("BLR", "DXB", 2700, "International"),
    ("DEL", "DXB", 2190, "International"),
    ("BLR", "SIN", 3180, "International"),
    ("DEL", "LHR", 6700, "International"),
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def execute_many(sql: str, rows: Iterable[tuple]) -> None:
    with get_connection() as conn:
        conn.executemany(sql, rows)
        conn.commit()


def init_db(seed_if_empty: bool = True) -> None:
    """Create database tables and optionally insert sample records."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS airports (
                airport_code TEXT PRIMARY KEY,
                airport_name TEXT NOT NULL,
                city TEXT NOT NULL,
                country TEXT NOT NULL
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS routes (
                route_id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin_code TEXT NOT NULL,
                destination_code TEXT NOT NULL,
                distance_km INTEGER NOT NULL,
                route_type TEXT NOT NULL CHECK(route_type IN ('Domestic', 'International')),
                UNIQUE(origin_code, destination_code),
                FOREIGN KEY(origin_code) REFERENCES airports(airport_code),
                FOREIGN KEY(destination_code) REFERENCES airports(airport_code)
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS flight_financials (
                flight_id INTEGER PRIMARY KEY AUTOINCREMENT,
                flight_date TEXT NOT NULL,
                airline TEXT NOT NULL,
                route_id INTEGER NOT NULL,
                aircraft_type TEXT NOT NULL,
                seat_capacity INTEGER NOT NULL,
                passengers INTEGER NOT NULL,
                avg_fare REAL NOT NULL,
                ancillary_revenue REAL NOT NULL,
                cargo_revenue REAL NOT NULL,
                fuel_cost REAL NOT NULL,
                crew_cost REAL NOT NULL,
                maintenance_cost REAL NOT NULL,
                airport_fees REAL NOT NULL,
                leasing_cost REAL NOT NULL,
                other_cost REAL NOT NULL,
                delay_minutes INTEGER DEFAULT 0,
                cancelled INTEGER DEFAULT 0 CHECK(cancelled IN (0, 1)),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(route_id) REFERENCES routes(route_id)
            );
            """
        )

        conn.commit()

        cur.execute("SELECT COUNT(*) AS n FROM airports;")
        if cur.fetchone()["n"] == 0:
            cur.executemany(
                "INSERT INTO airports (airport_code, airport_name, city, country) VALUES (?, ?, ?, ?);",
                AIRPORTS,
            )

        cur.execute("SELECT COUNT(*) AS n FROM routes;")
        if cur.fetchone()["n"] == 0:
            cur.executemany(
                "INSERT INTO routes (origin_code, destination_code, distance_km, route_type) VALUES (?, ?, ?, ?);",
                ROUTES,
            )

        conn.commit()

        if seed_if_empty:
            cur.execute("SELECT COUNT(*) AS n FROM flight_financials;")
            if cur.fetchone()["n"] == 0:
                seed_sample_data(conn)


def seed_sample_data(conn: sqlite3.Connection, rows_per_route: int = 85) -> None:
    """Insert realistic sample airline financial data for dashboard demo."""
    random.seed(42)
    cur = conn.cursor()
    cur.execute("SELECT route_id, origin_code, destination_code, distance_km, route_type FROM routes;")
    routes = cur.fetchall()

    start = date.today() - timedelta(days=540)
    rows = []

    for route in routes:
        for i in range(rows_per_route):
            flight_date = start + timedelta(days=random.randint(0, 540))
            airline = random.choice(AIRLINES)
            aircraft_type, seat_capacity = random.choice(list(AIRCRAFT.items()))

            if route["distance_km"] > 5000:
                aircraft_type = random.choice(["Airbus A350", "Boeing 787-8"])
                seat_capacity = AIRCRAFT[aircraft_type]

            # Seasonal and weekend demand effects
            weekend_factor = 1.07 if flight_date.weekday() in (4, 5, 6) else 1.00
            peak_month_factor = 1.12 if flight_date.month in (4, 5, 10, 11, 12) else 1.00
            route_factor = 1.18 if route["route_type"] == "International" else 1.00

            load_factor = max(0.45, min(0.98, random.gauss(0.78, 0.10) * weekend_factor * peak_month_factor / 1.08))
            passengers = int(seat_capacity * load_factor)

            base_fare = 3300 + route["distance_km"] * random.uniform(2.2, 3.4)
            if route["route_type"] == "International":
                base_fare *= random.uniform(1.55, 2.25)
            avg_fare = round(base_fare * peak_month_factor * random.uniform(0.85, 1.22), 2)

            ancillary_per_pax = random.uniform(250, 850) * route_factor
            ancillary_revenue = round(passengers * ancillary_per_pax, 2)
            cargo_revenue = round(route["distance_km"] * random.uniform(40, 170) * route_factor, 2)

            fuel_cost = round((route["distance_km"] * seat_capacity * random.uniform(0.95, 1.45)) + random.uniform(60000, 180000), 2)
            crew_cost = round(55000 + route["distance_km"] * random.uniform(16, 38) * route_factor, 2)
            maintenance_cost = round(42000 + route["distance_km"] * random.uniform(18, 50), 2)
            airport_fees = round(35000 + passengers * random.uniform(320, 850) * route_factor, 2)
            leasing_cost = round(65000 + seat_capacity * random.uniform(450, 1000), 2)
            other_cost = round(random.uniform(28000, 135000) * route_factor, 2)

            delay_minutes = max(0, int(random.gauss(18, 22)))
            cancelled = 1 if random.random() < 0.015 else 0
            if cancelled:
                passengers = 0
                avg_fare = 0
                ancillary_revenue = 0
                cargo_revenue = 0
                other_cost += random.uniform(150000, 400000)

            rows.append(
                (
                    flight_date.isoformat(), airline, route["route_id"], aircraft_type, seat_capacity,
                    passengers, avg_fare, ancillary_revenue, cargo_revenue, fuel_cost, crew_cost,
                    maintenance_cost, airport_fees, leasing_cost, other_cost, delay_minutes, cancelled
                )
            )

    cur.executemany(
        """
        INSERT INTO flight_financials (
            flight_date, airline, route_id, aircraft_type, seat_capacity, passengers,
            avg_fare, ancillary_revenue, cargo_revenue, fuel_cost, crew_cost,
            maintenance_cost, airport_fees, leasing_cost, other_cost, delay_minutes, cancelled
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        rows,
    )
    conn.commit()


def reset_database() -> None:
    """Delete all flight records and reseed sample data."""
    with get_connection() as conn:
        conn.execute("DELETE FROM flight_financials;")
        conn.commit()
        seed_sample_data(conn)


def insert_flight(record: dict) -> None:
    """Insert one flight financial record from the Streamlit form."""
    sql = """
        INSERT INTO flight_financials (
            flight_date, airline, route_id, aircraft_type, seat_capacity, passengers,
            avg_fare, ancillary_revenue, cargo_revenue, fuel_cost, crew_cost,
            maintenance_cost, airport_fees, leasing_cost, other_cost, delay_minutes, cancelled
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    values = (
        record["flight_date"], record["airline"], record["route_id"], record["aircraft_type"],
        record["seat_capacity"], record["passengers"], record["avg_fare"], record["ancillary_revenue"],
        record["cargo_revenue"], record["fuel_cost"], record["crew_cost"], record["maintenance_cost"],
        record["airport_fees"], record["leasing_cost"], record["other_cost"], record["delay_minutes"],
        record["cancelled"],
    )
    with get_connection() as conn:
        conn.execute(sql, values)
        conn.commit()
