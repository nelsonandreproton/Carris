from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import httpx
import math
import uvicorn
import logging
import asyncio
from html import escape
from typing import List, Dict, Optional
import time
from collections import defaultdict

app = FastAPI(title="Carris Bus Tracker", version="1.0.0")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add security middleware
import os
allowed_hosts = ["localhost", "127.0.0.1"]
# Add specific production domains when deployed
if os.getenv("RENDER"):
    render_service_name = os.getenv("RENDER_SERVICE_NAME", "carris-tracker")
    allowed_hosts.extend([
        f"{render_service_name}.onrender.com",
        # Add any custom domains here
        # "your-custom-domain.com"
    ])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
cors_origins = ["http://localhost:8000", "http://127.0.0.1:8000"]
# Add specific production domains when deployed
if os.getenv("RENDER"):
    # Replace with your actual Render domain
    render_service_name = os.getenv("RENDER_SERVICE_NAME", "carris-tracker")
    cors_origins.extend([
        f"https://{render_service_name}.onrender.com",
        # Add any custom domains here
        # "https://your-custom-domain.com"
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.carrismetropolitana.pt https://unpkg.com"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Simple rate limiting
rate_limit_store = defaultdict(list)
RATE_LIMIT_REQUESTS = 30  # requests per minute
RATE_LIMIT_WINDOW = 60    # seconds

def check_rate_limit(client_ip: str) -> bool:
    """Simple in-memory rate limiting"""
    current_time = time.time()

    # Clean old entries
    rate_limit_store[client_ip] = [
        req_time for req_time in rate_limit_store[client_ip]
        if current_time - req_time < RATE_LIMIT_WINDOW
    ]

    # Check if limit exceeded
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
        return False

    # Add current request
    rate_limit_store[client_ip].append(current_time)
    return True

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

async def fetch_stop_names_from_patterns():
    """Fetch stop names from all monitored patterns"""
    stop_names = {
        "110004": "ESCOLA",  # Keep our custom names
        "171577": "DONA MARIA",
    }

    # Get all unique pattern IDs from both directions
    all_patterns = set(FILTER_CRITERIA_ESCOLA["pattern_ids"] + FILTER_CRITERIA_DONA_MARIA["pattern_ids"])

    async with httpx.AsyncClient(timeout=10.0) as client:
        for pattern_id in all_patterns:
            try:
                response = await client.get(f"https://api.carrismetropolitana.pt/patterns/{pattern_id}")
                if response.status_code == 200:
                    pattern_data = response.json()
                    stops = pattern_data.get("path", [])
                    for stop_info in stops:
                        stop = stop_info.get("stop", {})
                        stop_id = stop.get("id")
                        stop_name = stop.get("name")
                        if stop_id and stop_name:
                            # Don't overwrite our custom names
                            if stop_id not in stop_names:
                                stop_names[stop_id] = stop_name
                else:
                    logger.warning(f"Failed to fetch pattern {pattern_id}: {response.status_code}")
            except Exception as e:
                logger.error(f"Error fetching pattern {pattern_id}: {e}")
                continue

    logger.info(f"Loaded {len(stop_names)} stop names from patterns")
    return stop_names

# Initialize with basic mapping - will be updated dynamically
STOP_NAMES = {
    "110004": "ESCOLA",
    "171577": "DONA MARIA",
}

# Filter criteria for both directions
FILTER_CRITERIA_ESCOLA = {
    "pattern_ids": ["1637_0_1", "1636_0_1", "1636_1_1", "1603_0_2"],
    "route_ids": ["1603_0", "1636_0", "1636_1", "1637_0"],
    "line_ids": ["1603", "1636", "1637"]
}

FILTER_CRITERIA_DONA_MARIA = {
    "pattern_ids": ["1603_0_1", "1636_0_2", "1636_1_2", "1637_0_2"],
    "route_ids": ["1603_0", "1636_0", "1636_1", "1637_0"],
    "line_ids": ["1603", "1636", "1637"]
}

# Schedule data for ESCOLA stop (buses going to ESCOLA first, then to DONA MARIA)
SCHEDULES_ESCOLA = {
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

# Schedule data for DONA MARIA stop (buses going to DONA MARIA first, then to ESCOLA)
SCHEDULES_DONA_MARIA = {
    "1603_0_1": {
        "line": "1603",
        "times": ["7:19", "8:06", "8:52", "9:37", "10:59", "12:24", "13:49", "15:09", "16:32", "17:21", "18:06", "18:56", "19:37", "20:19", "20:54"]
    },
    "1636_0_2": {
        "line": "1636",
        "times": ["7:21", "8:21", "10:26", "12:32", "14:26", "16:26", "18:36", "19:56"]
    },
    "1636_1_2": {
        "line": "1636",
        "times": ["6:31", "6:51", "7:51", "8:53", "11:01", "13:01", "15:01", "17:01", "17:31", "18:06", "19:11", "20:26"]
    },
    "1637_0_2": {
        "line": "1637",
        "times": ["6:56", "7:43", "8:38", "9:48", "12:43", "13:56", "15:55", "17:45", "18:46"]
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
    """Fetch pattern stop sequence and details from Carris API"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"https://api.carrismetropolitana.pt/patterns/{pattern_id}", timeout=10)
            response.raise_for_status()
            data = response.json()

            # Build stop sequence mapping and detailed stop info
            stop_sequence = {}
            stop_details = {}  # stop_id -> {lat, lon, name, sequence}
            path = data.get("path", [])

            for item in path:
                stop_data = item.get("stop", {})
                if stop_data and "id" in stop_data:
                    stop_id = stop_data["id"]
                    sequence = item.get("stop_sequence", 0)
                    stop_sequence[stop_id] = sequence
                    stop_details[stop_id] = {
                        "lat": stop_data.get("lat"),
                        "lon": stop_data.get("lon"),
                        "name": stop_data.get("name"),
                        "sequence": sequence
                    }

            return {"sequences": stop_sequence, "details": stop_details}
        except httpx.RequestError as e:
            logger.error(f"Failed to fetch pattern stops for {pattern_id}: {type(e).__name__}")
            logger.debug(f"Pattern fetch error details: {e}")
            return {}

async def fetch_bus_data(direction: str = "escola") -> List[Dict]:
    """Fetch bus data from Carris API and filter based on stop sequence logic"""

    # Select filter criteria based on direction
    if direction == "dona_maria":
        filter_criteria = FILTER_CRITERIA_DONA_MARIA
        target_stop_id = "171577"  # DONA MARIA is first stop
        additional_stop_id = "110004"  # ESCOLA is second stop
    else:  # escola
        filter_criteria = FILTER_CRITERIA_ESCOLA
        target_stop_id = "110004"  # ESCOLA is first stop
        additional_stop_id = "171577"  # DONA MARIA is second stop

    # First fetch all pattern stop sequences
    pattern_data = {}
    for pattern_id in filter_criteria["pattern_ids"]:
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
                if (pattern_id in filter_criteria["pattern_ids"] and
                    bus.get("route_id") in filter_criteria["route_ids"] and
                    bus.get("line_id") in filter_criteria["line_ids"] and
                    pattern_id in pattern_data and
                    stop_id):

                    pattern_info = pattern_data[pattern_id]
                    stop_sequences = pattern_info.get("sequences", {})
                    stop_details = pattern_info.get("details", {})

                    # Get stop sequences for target stops (dynamic based on direction)
                    target_sequence = stop_sequences.get(target_stop_id)  # First stop
                    additional_sequence = stop_sequences.get(additional_stop_id)  # Second stop
                    current_sequence = stop_sequences.get(stop_id)

                    # Calculate previous and next stops
                    previous_stop = None
                    next_stop = None

                    # Find stops with sequence numbers adjacent to current stop
                    for stop_id_check, details in stop_details.items():
                        if details["sequence"] == current_sequence - 1:
                            # Don't show marker if it's ESCOLA or DONA MARIA
                            if stop_id_check not in ["110004", "171577"]:
                                previous_stop = {
                                    "id": stop_id_check,
                                    "lat": details["lat"],
                                    "lon": details["lon"],
                                    "name": details["name"]
                                }
                        elif details["sequence"] == current_sequence + 1:
                            # Don't show marker if it's ESCOLA or DONA MARIA
                            if stop_id_check not in ["110004", "171577"]:
                                next_stop = {
                                    "id": stop_id_check,
                                    "lat": details["lat"],
                                    "lon": details["lon"],
                                    "name": details["name"]
                                }

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

                            # Calculate distance to the target stop based on direction
                            if direction == "dona_maria":
                                target_coords = ADDITIONAL_POINT  # DONA MARIA coordinates
                            else:
                                target_coords = TARGET_STOP  # ESCOLA coordinates

                            distance = calculate_distance(
                                bus_lat, bus_lon,
                                target_coords["lat"], target_coords["lon"]
                            )

                            # Calculate ETA if bus has valid speed
                            eta_minutes = None
                            speed_kmh = validate_speed(bus.get("speed"))
                            if speed_kmh and speed_kmh > 0:
                                eta_hours = distance / speed_kmh
                                eta_minutes = eta_hours * 60

                        # Check if bus is exactly at target stop (just arrived)
                        elif current_sequence == target_sequence:
                            bus_status = "heading_to_target"  # Still orange, just arrived
                            color = "#ff8800"  # orange

                            bus_lat = validate_coordinate(bus.get("lat"), "lat")
                            bus_lon = validate_coordinate(bus.get("lon"), "lon")

                            if bus_lat is None or bus_lon is None:
                                continue  # Skip buses with invalid coordinates

                            # Calculate distance to the target stop based on direction
                            if direction == "dona_maria":
                                target_coords = ADDITIONAL_POINT  # DONA MARIA coordinates
                            else:
                                target_coords = TARGET_STOP  # ESCOLA coordinates

                            distance = calculate_distance(
                                bus_lat, bus_lon,
                                target_coords["lat"], target_coords["lon"]
                            )
                            eta_minutes = 0  # Already arrived

                        # Check if bus is between target (110004) and additional point (171577)
                        elif (additional_sequence is not None and
                              target_sequence < current_sequence < additional_sequence):
                            bus_status = "between_stops"
                            color = "#FFD700"  # regular yellow

                            bus_lat = validate_coordinate(bus.get("lat"), "lat")
                            bus_lon = validate_coordinate(bus.get("lon"), "lon")

                            if bus_lat is None or bus_lon is None:
                                continue  # Skip buses with invalid coordinates

                            # Calculate distance to the target stop based on direction
                            if direction == "dona_maria":
                                target_coords = ADDITIONAL_POINT  # DONA MARIA coordinates
                            else:
                                target_coords = TARGET_STOP  # ESCOLA coordinates

                            distance = calculate_distance(
                                bus_lat, bus_lon,
                                target_coords["lat"], target_coords["lon"]
                            )
                            eta_minutes = None

                        # Check if bus has passed the additional point (171577)
                        elif (additional_sequence is not None and
                              current_sequence >= additional_sequence):
                            bus_status = "passed_stops"
                            color = "#000000"  # black

                            bus_lat = validate_coordinate(bus.get("lat"), "lat")
                            bus_lon = validate_coordinate(bus.get("lon"), "lon")

                            if bus_lat is None or bus_lon is None:
                                continue  # Skip buses with invalid coordinates

                            # Calculate distance to the target stop based on direction
                            if direction == "dona_maria":
                                target_coords = ADDITIONAL_POINT  # DONA MARIA coordinates
                            else:
                                target_coords = TARGET_STOP  # ESCOLA coordinates

                            distance = calculate_distance(
                                bus_lat, bus_lon,
                                target_coords["lat"], target_coords["lon"]
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
                                "target_stop_sequence": target_sequence,
                                "previous_stop": previous_stop,
                                "next_stop": next_stop
                            }
                            filtered_buses.append(bus_data)

            return filtered_buses

        except httpx.RequestError as e:
            logger.error(f"Failed to fetch vehicle data: {type(e).__name__}")
            logger.debug(f"Vehicle fetch error details: {e}")
            return []

@app.get("/api/buses")
async def get_buses(request: Request, direction: str = "escola"):
    """API endpoint to get filtered bus data with error handling and rate limiting"""
    # Get client IP
    client_ip = request.client.host

    # Check rate limit
    if not check_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": "60"}
        )

    # Validate direction parameter
    if direction not in ["escola", "dona_maria"]:
        raise HTTPException(status_code=400, detail="Invalid direction. Must be 'escola' or 'dona_maria'")

    try:
        return await fetch_bus_data(direction)
    except httpx.RequestError as e:
        logger.error(f"External API error: {type(e).__name__}")
        raise HTTPException(status_code=503, detail="External service unavailable")
    except Exception as e:
        logger.error(f"Internal error: {type(e).__name__}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")



@app.get("/", response_class=HTMLResponse)
async def index():
    """Main page with bus tracking interface"""
    global STOP_NAMES

    # Fetch updated stop names from patterns
    try:
        STOP_NAMES = await fetch_stop_names_from_patterns()
    except Exception as e:
        logger.error(f"Failed to fetch stop names: {e}")
        # Continue with basic mapping if fetch fails

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
        '{{SCHEDULES_ESCOLA_JSON}}', json.dumps(SCHEDULES_ESCOLA)
    ).replace(
        '{{SCHEDULES_DONA_MARIA_JSON}}', json.dumps(SCHEDULES_DONA_MARIA)
    ).replace(
        '{{TARGET_STOP_JSON}}', json.dumps(TARGET_STOP)
    ).replace(
        '{{ADDITIONAL_POINT_JSON}}', json.dumps(ADDITIONAL_POINT)
    ).replace(
        '{{STOP_NAMES_JSON}}', json.dumps(STOP_NAMES)
    )

    return html_content

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"
    print(f"Starting Carris Bus Tracker on http://localhost:{port}")
    uvicorn.run(app, host=host, port=port)