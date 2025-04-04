import pytest
import json
import uuid
import time
import logging
from fastapi.testclient import TestClient
from fastapi import status
import os

# Import the Collector service app
from services.collector.main import app

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Integration test markers
pytestmark = [pytest.mark.integration]

@pytest.fixture
def client():
    """Create a FastAPI test client"""
    logger.info("Setting up test client for Collector API")
    # Create test client
    test_client = TestClient(app)
    return test_client

@pytest.fixture
def sample_weather_data():
    """Generate sample weather data for testing"""
    return {
        "station_id": f"test-station-{uuid.uuid4().hex[:8]}",
        "temperature": 20.5,
        "humidity": 65.0,
        "wind_speed": 10.2,
        "timestamp": "2023-04-04T12:00:00Z"
    }

@pytest.fixture
def sample_batch_data():
    """Generate sample batch data for testing"""
    batch_id = f"test-batch-{uuid.uuid4().hex[:8]}"
    return {
        "batch_id": batch_id,
        "records": [
            {
                "station_id": f"test-station-{uuid.uuid4().hex[:8]}",
                "temperature": 20.5,
                "humidity": 65.0,
                "wind_speed": 10.2,
                "timestamp": "2023-04-04T12:00:00Z"
            },
            {
                "station_id": f"test-station-{uuid.uuid4().hex[:8]}",
                "temperature": 22.5,
                "humidity": 70.0,
                "wind_speed": 8.5,
                "timestamp": "2023-04-04T12:00:00Z"
            }
        ]
    }

def test_health_check_integration(client):
    """Integration test for health check endpoint"""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    # Verify response structure
    assert "status" in data
    assert "service" in data
    assert "trace_id" in data
    
    # Health check should show service details
    assert data["service"] == "collector"

def test_single_record_endpoint(client, sample_weather_data):
    """Integration test for single record ingestion endpoint"""
    # Generate a unique trace ID for tracking
    trace_id = str(uuid.uuid4())
    sample_weather_data["trace_id"] = trace_id
    
    # Send the request
    response = client.post(
        "/weather-data", 
        json=sample_weather_data,
        headers={"X-Trace-ID": trace_id}
    )
    
    # Verify the response
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "success"
    assert "detail" in data

def test_batch_record_endpoint(client, sample_batch_data):
    """Integration test for batch record ingestion endpoint"""
    batch_id = sample_batch_data["batch_id"]
    
    # Send the request
    response = client.post(
        "/weather-data/batch", 
        json=sample_batch_data,
        headers={"X-Trace-ID": batch_id}
    )
    
    # Verify the response
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "completed"
    assert data["batch_id"] == batch_id
    assert data["total"] == 2
    assert data["successful"] == 2
    assert data["failed"] == 0
    assert "failures" in data

def test_invalid_data_handling(client):
    """Integration test for invalid data handling"""
    # Create invalid data (missing required fields)
    invalid_data = {
        "station_id": "test-station",
        # Missing temperature, humidity, wind_speed, timestamp
    }
    
    trace_id = str(uuid.uuid4())
    
    # Send the request
    response = client.post(
        "/weather-data", 
        json=invalid_data,
        headers={"X-Trace-ID": trace_id}
    )
    
    # Response may be 400 or may be 200 with data sent to DLQ depending on implementation
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
    
    # If 200, there should be a success status
    if response.status_code == status.HTTP_200_OK:
        data = response.json()
        assert "status" in data
    
    # If 400, there should be a detail message
    if response.status_code == status.HTTP_400_BAD_REQUEST:
        data = response.json()
        assert "detail" in data

def test_batch_with_partial_invalid_data(client):
    """Integration test for batch with mixed valid and invalid records"""
    batch_id = f"test-batch-{uuid.uuid4().hex[:8]}"
    
    # Create a batch with one valid and one invalid record
    mixed_batch = {
        "batch_id": batch_id,
        "records": [
            {
                "station_id": f"test-station-{uuid.uuid4().hex[:8]}",
                "temperature": 20.5,
                "humidity": 65.0,
                "wind_speed": 10.2,
                "timestamp": "2023-04-04T12:00:00Z"
            },
            {
                "station_id": f"test-station-{uuid.uuid4().hex[:8]}",
                # Missing required fields
            }
        ]
    }
    
    # Send the request
    response = client.post(
        "/weather-data/batch", 
        json=mixed_batch,
        headers={"X-Trace-ID": batch_id}
    )
    
    # Verify the response indicates partial success
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 2
    assert data["successful"] == 1
    assert data["failed"] == 1
    assert len(data["failures"]) == 1
    
    # Verify failure details
    failure = data["failures"][0]
    assert "index" in failure
    assert "error" in failure
    assert not failure["success"] 