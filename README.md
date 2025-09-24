# Carris Bus Tracker

A secure, real-time bus tracking application for Carris Metropolitana buses with intelligent stop sequence filtering.

## Features

### 🚌 Smart Bus Filtering
- Tracks buses with patterns: 1637_0_1, 1636_0_1, 1636_1_1, 1603_0_2
- Uses stop sequence logic to show only relevant buses:
  - **Orange markers**: Buses heading to target stop (ID: 110004)
  - **Dark yellow markers**: Buses between stops 110004 and 171577
- Calculates distance and ETA based on current position and speed
- Auto-refreshes every 30 seconds

### 🗺️ Interactive Map
- Real-time bus positions with Leaflet.js integration
- Target and additional stop markers with detailed info
- Dynamic map centering on bus positions
- Color-coded legend for easy identification

### 🔒 Security Features
- Input validation for all external API data
- HTML output sanitization to prevent XSS attacks
- Proper error handling and logging
- CORS and trusted host middleware
- Rate limiting and error handling on API endpoints

## Setup

### 1. Install Dependencies
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Run the Application
```bash
python main.py
```

### 3. Access the Application
Open your browser and go to: http://localhost:8000

## API Endpoints

- `GET /` - Main web interface with interactive map
- `GET /api/buses` - JSON API for filtered bus data

## How It Works

### Stop Sequence Logic
The application uses the Carris API pattern endpoints to:
1. Fetch stop sequences for each bus pattern
2. Compare each bus's current `stop_id` with target stop sequences
3. Filter buses based on their position in the route:
   - Show buses heading to stop 110004 (orange)
   - Show buses between stops 110004-171577 (dark yellow)

### Data Sources
- **Vehicle positions**: `https://api.carrismetropolitana.pt/vehicles`
- **Route patterns**: `https://api.carrismetropolitana.pt/patterns/{pattern_id}`

### Key Target Stops
- **Target Stop (110004)**: R M Rosa Bastos (P Combust)
- **Additional Point (171577)**: R Principal 146

## Security Considerations

### Input Validation
- All coordinates validated against reasonable ranges
- Speed values checked for sanity
- String inputs sanitized and length-limited

### Error Handling
- Structured logging with appropriate levels
- No sensitive data exposed in error messages
- Graceful handling of API failures

### Network Security
- CORS configured for specific origins
- Trusted host middleware enabled
- HTTP client timeouts and proper exception handling

## Configuration

Key configuration is stored in constants at the top of `main.py`:
```python
TARGET_STOP = {
    "id": "110004",
    "lat": 38.810309,
    "lon": -9.234355,
    "name": "R M Rosa Bastos (P Combust)"
}

FILTER_CRITERIA = {
    "pattern_ids": ["1637_0_1", "1636_0_1", "1636_1_1", "1603_0_2"],
    "route_ids": ["1603_0", "1636_0", "1636_1", "1637_0"],
    "line_ids": ["1603", "1636", "1637"]
}
```

## Development

### Code Structure
- **Input validation**: `validate_coordinate()`, `validate_speed()`, `sanitize_string()`
- **Data fetching**: `fetch_pattern_stops()`, `fetch_bus_data()`
- **Distance calculations**: Haversine formula implementation
- **Web interface**: FastAPI with embedded HTML/JavaScript

### Logging
The application uses Python's logging module:
- **INFO level**: General application flow
- **ERROR level**: API failures and exceptions
- **DEBUG level**: Detailed error information (not shown by default)

### Adding New Routes
To track additional bus routes:
1. Add pattern IDs to `FILTER_CRITERIA["pattern_ids"]`
2. Add corresponding route IDs to `FILTER_CRITERIA["route_ids"]`
3. Add line IDs to `FILTER_CRITERIA["line_ids"]`

## Dependencies

- `fastapi==0.104.1` - Web framework
- `uvicorn==0.24.0` - ASGI server
- `httpx==0.25.2` - HTTP client for API calls
- `python-multipart==0.0.6` - Form data handling
- `jinja2==3.1.2` - Template engine support

## License

This project is for educational and personal use. Please respect the Carris Metropolitana API usage terms.

## Contributing

1. Follow security best practices
2. Validate all external inputs
3. Add proper error handling and logging
4. Test with various API response scenarios
5. Update documentation for any new features