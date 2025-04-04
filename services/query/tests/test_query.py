import pytest
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import status
from datetime import datetime, timedelta

# Import the Query service modules
from services.query.main import app

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Create test client
@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def sample_weather_data():
    """Generate sample weather data for testing"""
    current_time = datetime.utcnow()
    return [
        {
            "id": 1,
            "station_id": "station1",
            "temperature": 20.5,
            "humidity": 65.0,
            "wind_speed": 10.2,
            "timestamp": current_time,
            "trace_id": str(uuid.uuid4())
        },
        {
            "id": 2,
            "station_id": "station1",
            "temperature": 21.0,
            "humidity": 63.0,
            "wind_speed": 11.0,
            "timestamp": current_time - timedelta(hours=1),
            "trace_id": str(uuid.uuid4())
        },
        {
            "id": 3,
            "station_id": "station2",
            "temperature": 18.5,
            "humidity": 70.0,
            "wind_speed": 8.5,
            "timestamp": current_time - timedelta(hours=2),
            "trace_id": str(uuid.uuid4())
        }
    ]

@pytest.fixture
def test_date_range():
    """Get a test date range for queries"""
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=2)
    return {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat()
    }

def test_health_check(client):
    """Test the health check endpoint"""
    # Create mock connection objects that behave like real connections
    mock_db_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
    mock_db_conn.cursor.return_value = mock_cursor
    
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    
    # Mock the database and redis connections
    with patch('services.query.main.get_db_connection', return_value=mock_db_conn), \
         patch('services.query.main.get_redis_client', return_value=mock_redis):
        
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == {
            "status": "healthy",
            "service": "query",
            "components": {
                "database": "healthy",
                "redis": "healthy"
            }
        }

def test_health_check_degraded(client):
    """Test health check when services are degraded"""
    # Mock DB connection failing but Redis working
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    
    # Use a custom handler to properly simulate the DB error without crashing
    def mock_db_error(*args, **kwargs):
        raise Exception("DB Error")
    
    with patch('services.query.main.get_db_connection', side_effect=mock_db_error), \
         patch('services.query.main.get_redis_client', return_value=mock_redis):
        
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == {
            "status": "degraded",
            "service": "query",
            "components": {
                "database": "degraded",
                "redis": "healthy"
            }
        }

def test_get_weather_data_by_station(client, sample_weather_data, test_date_range):
    """Test retrieving weather data for a specific station"""
    station_id = "station1"
    station_data = [row for row in sample_weather_data if row["station_id"] == station_id]
    
    # Mock the database connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    
    # Configure the cursor to return filtered data with correct column order
    mock_cursor.__enter__.return_value.fetchall.return_value = [
        (row["station_id"], row["temperature"], row["humidity"],
         row["wind_speed"], row["timestamp"])  # Removed trace_id
        for row in station_data
    ]
    
    # Mock the column names in correct order
    mock_cursor.__enter__.return_value.description = [
        ("station_id", None, None, None, None, None, None),
        ("temperature", None, None, None, None, None, None),
        ("humidity", None, None, None, None, None, None),
        ("wind_speed", None, None, None, None, None, None),
        ("timestamp", None, None, None, None, None, None)
    ]
    
    # Mock Redis to return None (cache miss)
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    
    # Patch the connection functions
    with patch('services.query.main.get_db_connection', return_value=mock_conn), \
         patch('services.query.main.get_redis_client', return_value=mock_redis):
        
        # Call the endpoint with station filter and date range
        url = f"/weather/{station_id}?start_time={test_date_range['start_time']}&end_time={test_date_range['end_time']}"
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        
        # Verify the response
        results = response.json()
        assert len(results) == len(station_data)
        assert all(item["station_id"] == station_id for item in results)
        
        # Verify the SQL query included the station filter
        mock_cursor.__enter__.return_value.execute.assert_called_once()
        query_args = mock_cursor.__enter__.return_value.execute.call_args[0]
        assert "WHERE" in query_args[0]
        assert station_id == query_args[1][0]  # First parameter should be station_id

def test_redis_caching(client, sample_weather_data, test_date_range):
    """Test that Redis cache is used when available"""
    station_id = "station1"
    station_data = [row for row in sample_weather_data if row["station_id"] == station_id]
    
    # Mock Redis to return cached data
    cached_data = json.dumps(station_data, cls=DateTimeEncoder)
    mock_redis = MagicMock()
    mock_redis.get.return_value = cached_data
    
    # Mock DB connection (should not be used)
    mock_conn = MagicMock()
    
    with patch('services.query.main.get_db_connection', return_value=mock_conn), \
         patch('services.query.main.get_redis_client', return_value=mock_redis):
        
        # Call the endpoint
        url = f"/weather/{station_id}?start_time={test_date_range['start_time']}&end_time={test_date_range['end_time']}"
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        
        # Verify Redis was used
        mock_redis.get.assert_called_once()
        mock_conn.cursor.assert_not_called()  # DB should not be queried
        
        # Verify the response matches cached data
        results = response.json()
        assert len(results) == len(station_data)
        assert all(item["station_id"] == station_id for item in results)

def test_db_connection_failure(client, test_date_range):
    """Test behavior when database connection fails"""
    station_id = "station1"

    # Mock the database connection to fail
    with patch('services.query.main.get_db_connection', side_effect=Exception("DB Error")), \
         patch('services.query.main.get_redis_client', return_value=None):

        # Call the endpoint
        url = f"/weather/{station_id}?start_time={test_date_range['start_time']}&end_time={test_date_range['end_time']}"
        response = client.get(url)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

        # Verify the error response
        data = response.json()
        assert data["detail"] == {
            "error": "Database error",
            "message": "DB Error"
        }

def test_aggregate_weather_data(client, sample_weather_data, test_date_range):
    """Test retrieving aggregated weather data for a station"""
    station_id = "station1"
    
    # Mock the database connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    
    # Configure the cursor to return aggregate data
    mock_cursor.__enter__.return_value.fetchone.return_value = (
        station_id,        # station_id
        20.75,             # avg_temperature
        64.0,              # avg_humidity 
        10.85,             # avg_wind_speed
        20.5,              # min_temperature
        21.0               # max_temperature
    )
    
    # Mock Redis to return None (cache miss)
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    
    # Patch the connection functions
    with patch('services.query.main.get_db_connection', return_value=mock_conn), \
         patch('services.query.main.get_redis_client', return_value=mock_redis):
        
        # Call the aggregate endpoint
        url = f"/weather/aggregate/{station_id}?start_time={test_date_range['start_time']}&end_time={test_date_range['end_time']}"
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        
        # Verify the response
        data = response.json()
        assert data["station_id"] == station_id
        assert "avg_temperature" in data
        assert "min_temperature" in data
        assert "max_temperature" in data 