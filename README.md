# Carris Bus Tracker

A secure, real-time bus tracking application for Carris Metropolitana buses with intelligent stop sequence filtering and responsive design.

## Features

### 🚌 Smart Bus Filtering
- Tracks buses with patterns: 1637_0_1, 1636_0_1, 1636_1_1, 1603_0_2
- Uses stop sequence logic to show only relevant buses:
  - **Orange markers**: Buses heading to target stop (ID: 110004)
  - **Yellow markers**: Buses between stops 110004 and 171577
  - **Black markers**: Buses that have passed R Principal 146 (ID: 171577)
- Calculates distance and ETA based on current position and speed
- Auto-refreshes every 30 seconds with visual countdown timer

### 🗺️ Interactive Map
- Real-time bus positions with Leaflet.js integration
- Automatically centers on both target stops (ESCOLA and R Principal 146)
- Target and additional stop markers with detailed info
- Dynamic map centering includes buses when available
- Color-coded legend with compact 2-column layout on mobile

### 📅 Schedule Integration
- Real-time schedule display for all tracked bus lines
- **Next bus highlighting**: Automatically highlights the next scheduled bus time
- Responsive schedule grids that adapt to different screen sizes
- Larger, more readable schedule time display

### 📱 Responsive Design
- **Mobile-optimized layout**: Map and sidebar split 50/50 on mobile devices
- **Compact legend**: 2-column grid layout saves space on smaller screens
- **Adaptive schedule grids**: Adjust column count based on screen size
- **Visual countdown timer**: Centered in header, shows time until next refresh
- Full-screen utilization on all device sizes

### 🔒 Security Features
- **Enhanced Security Headers**: Content Security Policy, X-Frame-Options, X-XSS-Protection
- **Input Validation**: All coordinates, speeds, and strings validated with reasonable bounds
- **HTML Sanitization**: Prevents XSS attacks with proper escaping
- **Rate Limiting**: 30 requests per minute per IP to prevent API abuse
- **Secure External Resources**: Subresource Integrity (SRI) for Leaflet.js
- **Production Security**: Environment-specific CORS and trusted host configuration
- **Structured Logging**: Comprehensive error handling without information disclosure

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
- All coordinates validated against reasonable ranges (-90/90 lat, -180/180 lon)
- Speed values checked for sanity (0-200 km/h)
- String inputs sanitized with HTML escaping and length-limited

### Error Handling
- Structured logging with appropriate levels
- No sensitive data exposed in error messages
- Graceful handling of API failures with proper HTTP status codes

### Network Security
- CORS configured for specific origins (wildcard only for development)
- Trusted host middleware enabled
- HTTP client timeouts (10 seconds) and proper exception handling
- API requests limited to official Carris Metropolitana endpoints

### Security Recommendations for Production

**✅ Security Hardening Complete (Version 2.1):**
- ✅ **CORS Configuration**: Fixed wildcard origins, now uses environment-specific domains
- ✅ **TrustedHost Security**: Fixed wildcard hosts, now uses specific production domains
- ✅ **Dependencies Updated**: FastAPI >=0.115.0, uvicorn >=0.32.0, latest security patches
- ✅ **Content Security Policy**: Comprehensive CSP headers implemented
- ✅ **Subresource Integrity**: SRI hashes added to all external resources (Leaflet.js)
- ✅ **Rate Limiting**: 30 requests per minute per IP with proper 429 responses
- ✅ **Enhanced Error Handling**: Structured error responses without information disclosure

**Production Deployment Notes:**
- Set `RENDER_SERVICE_NAME` environment variable on Render for proper domain configuration
- Rate limiting uses in-memory storage (suitable for single-instance deployments)
- All external resources protected with integrity checks
- Security headers prevent XSS, clickjacking, and content-type confusion

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

## Latest Updates

### Version 2.1 Security Update (2024)
- **Enhanced Security**: Implemented comprehensive security hardening
- **Bus Color Update**: Changed between-stops buses from dark yellow to regular yellow
- **Next Bus Highlighting**: Automatically highlights the next scheduled bus time based on device time
- **Visual Countdown Timer**: 30-second countdown in header showing time until next refresh
- **Mobile-Optimized Layout**: 50/50 split between map and sidebar on mobile devices
- **Compact Legend**: 2-column grid layout for legend items on all devices
- **Auto-Centering Map**: Map automatically centers on both ESCOLA and R Principal 146 markers
- **Third Bus Status**: Added tracking for buses that have passed R Principal 146 (black markers)
- **Larger Schedule Times**: Improved readability with bigger font size and better spacing
- **Responsive Schedule Grids**: Adapt column count based on screen size

### Schedule Integration
The application includes comprehensive schedule data for all tracked lines:
- **Line 1603**: 15 daily scheduled times to ESCOLA stop
- **Line 1636**: Two variations (0_1 and 1_1) with different schedules
- **Line 1637**: 9 daily scheduled times
- **Smart Highlighting**: Next bus time highlighted in green, falls back to first time after midnight

## Development

### Code Structure
- **Input validation**: `validate_coordinate()`, `validate_speed()`, `sanitize_string()`
- **Data fetching**: `fetch_pattern_stops()`, `fetch_bus_data()` with async HTTP client
- **Distance calculations**: Haversine formula implementation with proper error handling
- **Schedule management**: Real-time next bus calculation with device time
- **Web interface**: FastAPI with embedded HTML template and JavaScript
- **Responsive design**: CSS Grid and Flexbox for mobile-first approach

### Frontend Architecture
- **Leaflet.js**: Interactive mapping with custom markers and popups
- **Real-time updates**: JavaScript polling every 30 seconds with visual feedback
- **Responsive CSS**: Mobile-first design with breakpoints at 768px and 480px
- **Schedule logic**: Client-side next bus calculation with automatic highlighting
- **Error handling**: Graceful degradation when API calls fail

### Logging
The application uses Python's logging module:
- **INFO level**: General application flow and successful operations
- **ERROR level**: API failures, external service issues, and exceptions
- **DEBUG level**: Detailed error information (not shown by default)
- **WARNING level**: Invalid data from external APIs

### Adding New Routes
To track additional bus routes:
1. Add pattern IDs to `FILTER_CRITERIA["pattern_ids"]`
2. Add corresponding route IDs to `FILTER_CRITERIA["route_ids"]`
3. Add line IDs to `FILTER_CRITERIA["line_ids"]`
4. Add schedule data to `SCHEDULES` dictionary with times for target stop

## Dependencies

- `fastapi>=0.115.0` - Modern web framework with security updates
- `uvicorn[standard]>=0.32.0` - Production ASGI server with performance optimizations
- `httpx>=0.28.0` - Async HTTP client with security patches
- `python-multipart>=0.0.6` - Form data handling
- `jinja2>=3.1.4` - Template engine with security updates

All dependencies updated to latest secure versions (December 2024).

## License

This project is for educational and personal use. Please respect the Carris Metropolitana API usage terms.

## Contributing

1. Follow security best practices
2. Validate all external inputs
3. Add proper error handling and logging
4. Test with various API response scenarios
5. Update documentation for any new features