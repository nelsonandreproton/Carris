from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import httpx
import math
import uvicorn
import logging
import asyncio
from html import escape
from typing import List, Dict, Optional

app = FastAPI(title="Carris Bus Tracker", version="1.0.0")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add security middleware
import os
allowed_hosts = ["localhost", "127.0.0.1"]
# Add Render domain if deployed
if os.getenv("RENDER"):
    allowed_hosts.append("*")  # Allow all hosts on Render
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
cors_origins = ["http://localhost:8000", "http://127.0.0.1:8000"]
# Allow all origins on Render for simplicity
if os.getenv("RENDER"):
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Target stop coordinates
TARGET_STOP = {
    "id": "110004",
    "lat": 38.810309,
    "lon": -9.234355,
    "name": "R M Rosa Bastos (P Combust)"
}

# Additional point of interest
ADDITIONAL_POINT = {
    "id": "171577",
    "lat": 38.813377,
    "lon": -9.251942,
    "name": "R Principal 146"
}

# Filter criteria
FILTER_CRITERIA = {
    "pattern_ids": ["1637_0_1", "1636_0_1", "1636_1_1", "1603_0_2"],
    "route_ids": ["1603_0", "1636_0", "1636_1", "1637_0"],
    "line_ids": ["1603", "1636", "1637"]
}

# Schedule data for ESCOLA stop
SCHEDULES = {
    "1603_0_2": {
        "line": "1603",
        "times": ["6:12", "6:52", "7:32", "8:22", "9:07", "9:52", "11:12", "12:37", "14:02", "15:22", "16:47", "17:37", "18:22", "19:12", "19:52"]
    },
    "1636_0_1": {
        "line": "1636",
        "times": ["7:40", "8:40", "10:50", "12:50", "14:50", "16:50", "19:00", "20:15"]
    },
    "1636_1_1": {
        "line": "1636",
        "times": ["6:32", "7:07", "8:07", "10:12", "12:18", "14:17", "16:17", "17:17", "18:22", "19:42"]
    },
    "1637_0_1": {
        "line": "1637",
        "times": ["7:13", "8:04", "9:14", "12:04", "13:21", "15:21", "17:04", "18:04", "19:14"]
    }
}

def validate_coordinate(value, coord_type: str = "coordinate") -> Optional[float]:
    """Validate and sanitize coordinate values"""
    try:
        coord = float(value)
        if coord_type == "lat" and not (-90 <= coord <= 90):
            logger.warning(f"Invalid latitude: {coord}")
            return None
        elif coord_type == "lon" and not (-180 <= coord <= 180):
            logger.warning(f"Invalid longitude: {coord}")
            return None
        return coord
    except (ValueError, TypeError):
        logger.warning(f"Invalid coordinate format: {value}")
        return None

def validate_speed(value) -> Optional[float]:
    """Validate speed values"""
    try:
        speed = float(value)
        if speed < 0 or speed > 200:  # Reasonable bus speed limits in km/h
            return None
        return speed
    except (ValueError, TypeError):
        return None

def sanitize_string(value: str, max_length: int = 100) -> str:
    """Sanitize string values for safe HTML output"""
    if not isinstance(value, str):
        value = str(value)
    return escape(value[:max_length])

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points using Haversine formula (in kilometers)"""
    R = 6371  # Earth's radius in kilometers

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate bearing from point 1 to point 2"""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)

    y = math.sin(delta_lon) * math.cos(lat2_rad)
    x = (math.cos(lat1_rad) * math.sin(lat2_rad) -
         math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon))

    bearing = math.atan2(y, x)
    bearing_degrees = math.degrees(bearing)

    return (bearing_degrees + 360) % 360

def is_heading_towards_target(bus_bearing: float, target_bearing: float, tolerance: float = 45) -> bool:
    """Check if bus is heading towards target within tolerance"""
    diff = abs(bus_bearing - target_bearing)
    return min(diff, 360 - diff) <= tolerance


async def fetch_pattern_stops(pattern_id: str) -> Dict:
    """Fetch pattern stop sequence from Carris API"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"https://api.carrismetropolitana.pt/patterns/{pattern_id}", timeout=10)
            response.raise_for_status()
            data = response.json()

            # Build stop sequence mapping
            stop_sequence = {}
            path = data.get("path", [])
            for item in path:
                stop_data = item.get("stop", {})
                if stop_data and "id" in stop_data:
                    stop_sequence[stop_data["id"]] = item.get("stop_sequence", 0)

            return stop_sequence
        except httpx.RequestError as e:
            logger.error(f"Failed to fetch pattern stops for {pattern_id}: {type(e).__name__}")
            logger.debug(f"Pattern fetch error details: {e}")
            return {}

async def fetch_bus_data() -> List[Dict]:
    """Fetch bus data from Carris API and filter based on stop sequence logic"""

    # First fetch all pattern stop sequences
    pattern_data = {}
    for pattern_id in FILTER_CRITERIA["pattern_ids"]:
        pattern_data[pattern_id] = await fetch_pattern_stops(pattern_id)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("https://api.carrismetropolitana.pt/vehicles", timeout=10)
            response.raise_for_status()
            data = response.json()

            # Filter buses based on stop sequence criteria
            filtered_buses = []
            for bus in data:
                pattern_id = bus.get("pattern_id")
                stop_id = bus.get("stop_id")

                # Check if bus matches our pattern criteria
                if (pattern_id in FILTER_CRITERIA["pattern_ids"] and
                    bus.get("route_id") in FILTER_CRITERIA["route_ids"] and
                    bus.get("line_id") in FILTER_CRITERIA["line_ids"] and
                    pattern_id in pattern_data and
                    stop_id):

                    stop_sequences = pattern_data[pattern_id]

                    # Get stop sequences for target stops
                    target_sequence = stop_sequences.get("110004")  # TARGET_STOP
                    additional_sequence = stop_sequences.get("171577")  # ADDITIONAL_POINT
                    current_sequence = stop_sequences.get(stop_id)

                    if target_sequence is not None and current_sequence is not None:
                        bus_status = None
                        color = "#000000"  # default black

                        # Check if bus is heading to target stop (110004)
                        if current_sequence < target_sequence:
                            bus_status = "heading_to_target"
                            color = "#ff8800"  # orange

                            # Calculate distance and ETA to target with validation
                            bus_lat = validate_coordinate(bus.get("lat"), "lat")
                            bus_lon = validate_coordinate(bus.get("lon"), "lon")

                            if bus_lat is None or bus_lon is None:
                                continue  # Skip buses with invalid coordinates

                            distance = calculate_distance(
                                bus_lat, bus_lon,
                                TARGET_STOP["lat"], TARGET_STOP["lon"]
                            )

                            # Calculate ETA if bus has valid speed
                            eta_minutes = None
                            speed_kmh = validate_speed(bus.get("speed"))
                            if speed_kmh and speed_kmh > 0:
                                eta_hours = distance / speed_kmh
                                eta_minutes = eta_hours * 60

                        # Check if bus is between target (110004) and additional point (171577)
                        elif (additional_sequence is not None and
                              target_sequence <= current_sequence < additional_sequence):
                            bus_status = "between_stops"
                            color = "#B8860B"  # dark yellow

                            bus_lat = validate_coordinate(bus.get("lat"), "lat")
                            bus_lon = validate_coordinate(bus.get("lon"), "lon")

                            if bus_lat is None or bus_lon is None:
                                continue  # Skip buses with invalid coordinates

                            distance = calculate_distance(
                                bus_lat, bus_lon,
                                TARGET_STOP["lat"], TARGET_STOP["lon"]
                            )
                            eta_minutes = None

                        # Only add buses that meet our criteria
                        if bus_status:
                            bus_data = {
                                **bus,
                                "status": bus_status,
                                "color": color,
                                "distance_to_target": round(distance, 2) if 'distance' in locals() else None,
                                "eta_minutes": round(eta_minutes, 1) if eta_minutes else None,
                                "current_stop_sequence": current_sequence,
                                "target_stop_sequence": target_sequence
                            }
                            filtered_buses.append(bus_data)

            return filtered_buses

        except httpx.RequestError as e:
            logger.error(f"Failed to fetch vehicle data: {type(e).__name__}")
            logger.debug(f"Vehicle fetch error details: {e}")
            return []

@app.get("/api/buses")
async def get_buses():
    """API endpoint to get filtered bus data with error handling"""
    try:
        return await fetch_bus_data()
    except Exception as e:
        logger.error(f"Failed to fetch bus data: {type(e).__name__}")
        logger.debug(f"Bus data fetch error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")



@app.get("/", response_class=HTMLResponse)
async def index():
    """Main page with bus tracking interface"""
    # Read HTML template
    with open('index_template.html', 'r', encoding='utf-8') as f:
        template = f.read()

    # Replace placeholders with sanitized data
    import json
    html_content = template.replace(
        '{{TARGET_STOP_NAME}}', sanitize_string(TARGET_STOP['name'])
    ).replace(
        '{{TARGET_STOP_ID}}', sanitize_string(str(TARGET_STOP['id']))
    ).replace(
        '{{SCHEDULES_JSON}}', json.dumps(SCHEDULES)
    ).replace(
        '{{TARGET_STOP_JSON}}', json.dumps(TARGET_STOP)
    ).replace(
        '{{ADDITIONAL_POINT_JSON}}', json.dumps(ADDITIONAL_POINT)
    )

    return html_content

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"
    print(f"Starting Carris Bus Tracker on http://localhost:{port}")
    uvicorn.run(app, host=host, port=port)