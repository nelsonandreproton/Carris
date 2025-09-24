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
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
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
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Carris Bus Tracker</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .container {{ display: flex; gap: 20px; }}
            .map-container {{ flex: 1; }}
            .info-container {{ flex: 1; min-width: 400px; }}
            #map {{ height: 600px; width: 100%; border: 1px solid #ccc; border-radius: 8px; }}
            .bus-item {{
                transition: all 0.3s ease;
                border: 1px solid #ccc;
                margin: 10px 0;
                padding: 15px;
                border-radius: 8px;
            }}
            .bus-item:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            .heading-towards {{ background: #e8f5e8; }}
            .not-heading {{ background: #f5f5f5; }}
            #last-update {{ color: #666; font-size: 0.9em; margin-top: 20px; }}
            h1 {{ color: #333; }}
            .legend {{
                background: white;
                padding: 10px;
                border-radius: 5px;
                border: 1px solid #ccc;
                margin-bottom: 10px;
            }}
            .legend-item {{ margin: 5px 0; }}
            .legend-color {{
                display: inline-block;
                width: 20px;
                height: 20px;
                margin-right: 10px;
                border-radius: 50%;
                vertical-align: middle;
            }}
        </style>
    </head>
    <body>
        <h1>Carris Bus Tracker - Lines 1603, 1636, 1637</h1>
        <p>Tracking buses heading to stop {sanitize_string(TARGET_STOP['name'])} - ID {sanitize_string(str(TARGET_STOP['id']))} (Lat: {TARGET_STOP['lat']}, Lon: {TARGET_STOP['lon']})</p>
        <p>Additional point: {sanitize_string(ADDITIONAL_POINT['name'])} - ID {sanitize_string(str(ADDITIONAL_POINT['id']))} (Lat: {ADDITIONAL_POINT['lat']}, Lon: {ADDITIONAL_POINT['lon']})</p>
        <p>Filters: Lines 1603, 1636, 1637 - Routes 1603_0, 1636_0, 1636_1, 1637_0</p>

        <div class="container">
            <div class="map-container">
                <div id="map"></div>
            </div>
            <div class="info-container">
                <div class="legend">
                    <div class="legend-item">
                        <span class="legend-color" style="background-color: #ff4444;"></span>
                        {TARGET_STOP['name']} (110004)
                    </div>
                    <div class="legend-item">
                        <span class="legend-color" style="background-color: #4444ff;"></span>
                        R Principal 146 (171577)
                    </div>
                    <div class="legend-item">
                        <span class="legend-color" style="background-color: #ff8800;"></span>
                        Bus heading to stop 110004
                    </div>
                    <div class="legend-item">
                        <span class="legend-color" style="background-color: #B8860B;"></span>
                        Bus between stops 110004-171577
                    </div>
                </div>
                <div id="buses-container"></div>
                <p id="last-update"></p>
            </div>
        </div>

        <script>
            let map;
            let busMarkers = {{}};
            let targetMarker;
            let additionalMarker;

            // Initialize map
            async function initMap() {{
                // Center map between both points
                const centerLat = ({TARGET_STOP['lat']} + {ADDITIONAL_POINT['lat']}) / 2;
                const centerLon = ({TARGET_STOP['lon']} + {ADDITIONAL_POINT['lon']}) / 2;
                map = L.map('map').setView([centerLat, centerLon], 13);

                // Add tile layer
                L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    attribution: '© OpenStreetMap contributors'
                }}).addTo(map);


                // Add target stop marker (higher layer)
                targetMarker = L.marker([{TARGET_STOP['lat']}, {TARGET_STOP['lon']}], {{
                    icon: L.divIcon({{
                        className: 'target-marker',
                        html: '<div style="background-color: #ff4444; width: 20px; height: 20px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 5px rgba(0,0,0,0.3); z-index: 1000;"></div>',
                        iconSize: [26, 26],
                        iconAnchor: [13, 13]
                    }}),
                    zIndexOffset: 1000
                }}).addTo(map);

                targetMarker.bindPopup(`<b>{TARGET_STOP['name']}</b><br>ID: {TARGET_STOP['id']}<br>Lat: {TARGET_STOP['lat']}<br>Lon: {TARGET_STOP['lon']}`);

                // Add additional point marker (higher layer)
                additionalMarker = L.marker([{ADDITIONAL_POINT['lat']}, {ADDITIONAL_POINT['lon']}], {{
                    icon: L.divIcon({{
                        className: 'additional-marker',
                        html: '<div style="background-color: #4444ff; width: 20px; height: 20px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 5px rgba(0,0,0,0.3); z-index: 1000;"></div>',
                        iconSize: [26, 26],
                        iconAnchor: [13, 13]
                    }}),
                    zIndexOffset: 1000
                }}).addTo(map);

                additionalMarker.bindPopup(`<b>{ADDITIONAL_POINT['name']}</b><br>ID: {ADDITIONAL_POINT['id']}<br>Lat: {ADDITIONAL_POINT['lat']}<br>Lon: {ADDITIONAL_POINT['lon']}`);
            }}



            async function updateBuses() {{
                try {{
                    const response = await fetch('/api/buses');
                    const buses = await response.json();

                    // Update info panel
                    const container = document.getElementById('buses-container');
                    container.innerHTML = '';

                    // Clear existing bus markers
                    Object.values(busMarkers).forEach(marker => map.removeLayer(marker));
                    busMarkers = {{}};

                    if (buses.length === 0) {{
                        container.innerHTML = '<p>No buses found matching criteria</p>';
                        return;
                    }}

                    // Calculate map bounds to fit all buses
                    let busLatitudes = [];
                    let busLongitudes = [];

                    buses.forEach(bus => {{
                        busLatitudes.push(bus.lat);
                        busLongitudes.push(bus.lon);
                    }});

                    // Center map on buses if there are any
                    if (busLatitudes.length > 0) {{
                        const centerLat = busLatitudes.reduce((a, b) => a + b) / busLatitudes.length;
                        const centerLon = busLongitudes.reduce((a, b) => a + b) / busLongitudes.length;

                        // Create bounds that include all buses
                        const minLat = Math.min(...busLatitudes);
                        const maxLat = Math.max(...busLatitudes);
                        const minLon = Math.min(...busLongitudes);
                        const maxLon = Math.max(...busLongitudes);

                        // Add padding to the bounds
                        const latPadding = (maxLat - minLat) * 0.2 || 0.01;
                        const lonPadding = (maxLon - minLon) * 0.2 || 0.01;

                        const bounds = [
                            [minLat - latPadding, minLon - lonPadding],
                            [maxLat + latPadding, maxLon + lonPadding]
                        ];

                        map.fitBounds(bounds);
                    }}

                    buses.forEach(bus => {{
                        // Update info panel
                        const busDiv = document.createElement('div');
                        busDiv.className = `bus-item ${{bus.status === 'heading_to_target' ? 'heading-towards' : 'between-stops'}}`;

                        const etaText = bus.eta_minutes ?
                            `<strong>ETA: ${{bus.eta_minutes}} minutes</strong>` :
                            'Not heading to target or no speed data';

                        busDiv.innerHTML = `
                            <h3>Bus ${{bus.id}}</h3>
                            <p><strong>Location:</strong> ${{bus.lat.toFixed(6)}}, ${{bus.lon.toFixed(6)}}</p>
                            <p><strong>Speed:</strong> ${{bus.speed.toFixed(1)}} km/h</p>
                            <p><strong>Bearing:</strong> ${{bus.bearing}}°</p>
                            <p><strong>Distance to target:</strong> ${{bus.distance_to_target}} km</p>
                            <p><strong>Status:</strong> ${{bus.status === 'heading_to_target' ? 'Heading to stop 110004' : 'Between stops 110004-171577'}}</p>
                            <p><strong>Current Stop Sequence:</strong> ${{bus.current_stop_sequence || 'N/A'}}</p>
                            <p><strong>Target Stop Sequence:</strong> ${{bus.target_stop_sequence || 'N/A'}}</p>
                            <p>${{etaText}}</p>
                            <p><strong>Status:</strong> ${{bus.current_status || 'Unknown'}}</p>
                        `;
                        container.appendChild(busDiv);

                        // Add bus marker to map
                        const markerColor = bus.color || '#000000';
                        const marker = L.marker([bus.lat, bus.lon], {{
                            icon: L.divIcon({{
                                className: 'bus-marker',
                                html: `
                                    <div style="
                                        background-color: ${{markerColor}};
                                        width: 32px;
                                        height: 32px;
                                        border-radius: 50%;
                                        border: 4px solid white;
                                        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
                                        position: relative;
                                        z-index: 2000;
                                    ">
                                        <div style="
                                            position: absolute;
                                            top: -16px;
                                            left: 50%;
                                            transform: translateX(-50%) rotate(${{bus.bearing}}deg);
                                            width: 0;
                                            height: 0;
                                            border-left: 8px solid transparent;
                                            border-right: 8px solid transparent;
                                            border-bottom: 24px solid ${{markerColor}};
                                        "></div>
                                    </div>
                                `,
                                iconSize: [40, 40],
                                iconAnchor: [20, 20]
                            }}),
                            zIndexOffset: 2000
                        }}).addTo(map);

                        const popupContent = `
                            <b>Bus ${{bus.id}}</b><br>
                            Speed: ${{bus.speed.toFixed(1)}} km/h<br>
                            Bearing: ${{bus.bearing}}°<br>
                            Distance: ${{bus.distance_to_target}} km<br>
                            ${{bus.eta_minutes ? `ETA: ${{bus.eta_minutes}} min` : 'No ETA available'}}
                        `;
                        marker.bindPopup(popupContent);

                        busMarkers[bus.id] = marker;
                    }});

                    document.getElementById('last-update').textContent =
                        `Last updated: ${{new Date().toLocaleTimeString()}}`;

                }} catch (error) {{
                    console.error('Error updating buses:', error);
                    document.getElementById('buses-container').innerHTML =
                        '<p style="color: red;">Error loading bus data</p>';
                }}
            }}

            // Initialize everything when page loads
            document.addEventListener('DOMContentLoaded', async function() {{
                await initMap();
                updateBuses();
                setInterval(updateBuses, 30000);
            }});
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    print("Starting Carris Bus Tracker on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)