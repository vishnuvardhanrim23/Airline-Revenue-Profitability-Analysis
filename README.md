# Airline Revenue & Profitability Analysis System

This is a complete Streamlit + SQLite project for analyzing airline revenue, cost structure, route profitability, operating profit, load factor, RASK, CASK, and profit margins.

## Files

- `app.py` - Main Streamlit dashboard
- `database.py` - SQLite database creation, sample data generation, insert/reset functions
- `airline_analysis.db` - SQLite database file, created automatically when the app runs
- `requirements.txt` - Python packages needed

## How to Run on Windows CMD

Open CMD inside this folder and run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

If `streamlit` is not recognized, run:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Database Design

### 1. airports
Stores airport master data.

Columns:
- airport_code
- airport_name
- city
- country

### 2. routes
Stores route-level information.

Columns:
- route_id
- origin_code
- destination_code
- distance_km
- route_type

### 3. flight_financials
Stores each flight's revenue and cost information.

Columns:
- flight_id
- flight_date
- airline
- route_id
- aircraft_type
- seat_capacity
- passengers
- avg_fare
- ancillary_revenue
- cargo_revenue
- fuel_cost
- crew_cost
- maintenance_cost
- airport_fees
- leasing_cost
- other_cost
- delay_minutes
- cancelled

## Main Formulas

```text
Passenger Revenue = Passengers × Average Fare
Total Revenue = Passenger Revenue + Ancillary Revenue + Cargo Revenue
Total Cost = Fuel + Crew + Maintenance + Airport Fees + Leasing + Other Costs
Operating Profit = Total Revenue - Total Cost
Profit Margin (%) = Operating Profit ÷ Total Revenue × 100
Load Factor (%) = Passengers ÷ Seat Capacity × 100
ASK = Seat Capacity × Distance
RPK = Passengers × Distance
RASK = Total Revenue ÷ ASK
CASK = Total Cost ÷ ASK
Yield per RPK = Passenger Revenue ÷ RPK
```

## Dashboard Pages

1. Executive Dashboard
2. Revenue Analysis
3. Profitability Analysis
4. Route & Flight Performance
5. Database Manager

The Database Manager page lets you add new flight records and download filtered data as CSV.
