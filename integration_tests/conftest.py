import pytest
import time
import subprocess
import os
import sys
import socket
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def is_port_in_use(port):
    """Check if a port is in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def pytest_sessionstart(session):
    """Setup before all tests - check if services are running"""
    # Check if services are available
    collector_port = int(os.getenv('COLLECTOR_PORT', '8000'))
    consumer_port = int(os.getenv('CONSUMER_PORT', '8002'))
    query_port = int(os.getenv('QUERY_PORT', '8000'))
    
    if not (is_port_in_use(collector_port) and 
            is_port_in_use(consumer_port) and 
            is_port_in_use(query_port)):
        print("\nWARNING: Not all services appear to be running!")
        print("For integration tests to work, make sure all services are up with Docker Compose.")
        print("Run: docker compose up -d")
        print("Waiting 10 seconds for services to potentially start up...")
        time.sleep(10)
        
        # Check again
        if not (is_port_in_use(collector_port) and 
                is_port_in_use(consumer_port) and 
                is_port_in_use(query_port)):
            print("Services are still not available. Some tests may fail.")

# Register custom markers
def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "performance: mark test as performance test")

@pytest.fixture(scope="session")
def wait_for_services():
    """Fixture to wait for services to be ready"""
    # Add a short delay to ensure all services are ready
    time.sleep(3)
    yield 