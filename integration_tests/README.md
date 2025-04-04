# Weather System Pipeline Integration Tests

This directory contains integration tests for the Weather System Pipeline, which test the entire system working together.

## Setup

1. Install test dependencies:
   ```bash
   pip install -r integration_tests/requirements.txt
   ```

2. Make sure all services are running:
   ```bash
   docker compose up -d
   ```

## Running Tests

### Using the test runner script

The easiest way to run integration tests:

```bash
# Run integration tests only
python integration_tests/run_tests.py --integration

# Run integration tests with verbose output
python integration_tests/run_tests.py --integration --verbose
```

### Using pytest directly

You can also run tests directly with pytest:

```bash
# Run all integration tests
pytest integration_tests/

# Run a specific integration test file
pytest integration_tests/test_pipeline.py

# Run a specific test
pytest integration_tests/test_pipeline.py::test_data_ingestion_and_retrieval
```

## Test Structure

The integration tests test the complete system flow:
- Health endpoint checks across services
- Data ingestion and retrieval through the entire pipeline
- Deduplication testing
- Multi-station data handling

Integration tests are different from unit tests because they test the entire system working together, rather than individual components in isolation. 