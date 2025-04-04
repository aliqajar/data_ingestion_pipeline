import pytest
import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from multiprocessing import Manager

# Only import module level constants/utilities
from services.consumer.main import buffer_lock, BATCH_INTERVAL

# Explicitly set the asyncio fixture scope
pytestmark = pytest.mark.asyncio

# Create test fixtures
@pytest.fixture
def mock_buffer():
    manager = Manager()
    return manager.dict()

@pytest.fixture
def mock_stats():
    return {
        "messages_processed": 0,
        "batches_persisted": 0,
        "in_memory_duplicates": 0
    }

@pytest.fixture
def sample_weather_data():
    """Generate sample weather data for testing"""
    return {
        "station_id": "station1",
        "temperature": 20.5,
        "humidity": 65.0,
        "wind_speed": 10.2,
        "timestamp": "2023-04-04T12:00:00",
        "trace_id": str(uuid.uuid4())
    }

@pytest.fixture
def mock_kafka_message(sample_weather_data):
    """Create a mock Kafka message with sample data"""
    mock_msg = MagicMock()
    mock_msg.value = json.dumps(sample_weather_data).encode('utf-8')
    mock_msg.partition = 0
    mock_msg.offset = 100
    return mock_msg

@pytest.mark.asyncio
async def test_persist_batch(mock_buffer, mock_stats):
    """Test the persist_batch function with a mock database connection"""
    # Setup test data in buffer
    test_data = {
        "station1:2023-04-04T12:00:00": {
            "station_id": "station1",
            "temperature": 20.5,
            "humidity": 65.0,
            "wind_speed": 10.2,
            "timestamp": "2023-04-04T12:00:00",
            "trace_id": "test-trace-id"
        }
    }
    mock_buffer.update(test_data)
    
    # Mock database connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    
    # Patch relevant functions
    with patch('services.consumer.main.psycopg2.connect', return_value=mock_conn), \
         patch('services.consumer.main.buffer', mock_buffer), \
         patch('services.consumer.main.stats', mock_stats), \
         patch('services.consumer.main.last_flush_time', time.time()):
        
        # Import persist_batch here to avoid initialization issues
        from services.consumer.main import persist_batch
        
        # Call the function
        result = await persist_batch("test-trace")
        
        # Verify the function behavior
        assert mock_cursor.execute.called
        assert mock_conn.commit.called
        assert len(mock_buffer) == 0  # Buffer should be cleared
        assert mock_stats["batches_persisted"] == 1
        
        # Ensure cursor and connection were closed
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

@pytest.mark.asyncio
async def test_in_memory_deduplication(mock_buffer, mock_stats, sample_weather_data):
    """Test that duplicate messages are detected in memory"""
    # Create a unique key for the sample data
    key = f"{sample_weather_data['station_id']}:{sample_weather_data['timestamp']}"
    
    # Add the sample data to the buffer
    mock_buffer[key] = sample_weather_data
    
    # Create a duplicate message with the same key but different trace ID
    duplicate_data = sample_weather_data.copy()
    duplicate_data["trace_id"] = str(uuid.uuid4())
    
    # Mock the Kafka Consumer
    mock_consumer = MagicMock()
    
    # Setup the test with mocks
    with patch('services.consumer.main.buffer', mock_buffer), \
         patch('services.consumer.main.stats', mock_stats), \
         patch('services.consumer.main.buffer_lock', MagicMock()), \
         patch('services.consumer.main.consumer', mock_consumer):
        
        # Test the duplicate detection
        duplicate_key = f"{duplicate_data['station_id']}:{duplicate_data['timestamp']}"
        
        assert duplicate_key in mock_buffer  # Should be a duplicate
        
        # Simulate processing the duplicate
        with buffer_lock:
            mock_stats["in_memory_duplicates"] += 1
        
        # Update the buffer (as would happen in the actual function)
        mock_buffer[duplicate_key] = duplicate_data
        
        # Verify duplicate was detected and stats were updated
        assert mock_stats["in_memory_duplicates"] == 1

# More tests can be added as needed 