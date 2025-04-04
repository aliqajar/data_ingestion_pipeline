#!/bin/bash

# Display help message
function show_help {
  echo "Usage: $0 [OPTIONS]"
  echo "Run tests for the weather data pipeline"
  echo ""
  echo "Options:"
  echo "  -a, --all         Run all tests (unit and integration)"
  echo "  -u, --unit        Run only unit tests (default)"
  echo "  -i, --integration Run only integration tests"
  echo "  -s, --service     Run tests only for specific service (collector, consumer, query)"
  echo "  -h, --help        Display this help message"
  echo ""
  echo "Examples:"
  echo "  $0 --unit                   # Run all unit tests"
  echo "  $0 --integration            # Run all integration tests"
  echo "  $0 --all                    # Run all tests (unit and integration)"
  echo "  $0 --service collector      # Run all tests for the collector service"
  echo "  $0 --integration --service query  # Run integration tests for the query service"
}

# Default values
RUN_UNIT=true
RUN_INTEGRATION=false
SERVICE=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -a|--all)
      RUN_UNIT=true
      RUN_INTEGRATION=true
      shift
      ;;
    -u|--unit)
      RUN_UNIT=true
      RUN_INTEGRATION=false
      shift
      ;;
    -i|--integration)
      RUN_UNIT=false
      RUN_INTEGRATION=true
      shift
      ;;
    -s|--service)
      SERVICE="$2"
      shift
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      show_help
      exit 1
      ;;
  esac
done

# Set environment variable for integration tests
if [[ "$RUN_INTEGRATION" == "true" ]]; then
  export RUN_INTEGRATION_TESTS=true
fi

# Construct pytest command
PYTEST_CMD="python -m pytest"

# Apply filters
if [[ "$RUN_UNIT" == "true" && "$RUN_INTEGRATION" == "true" ]]; then
  # Run all tests
  PYTEST_CMD="$PYTEST_CMD -v"
elif [[ "$RUN_UNIT" == "true" ]]; then
  # Run only unit tests
  PYTEST_CMD="$PYTEST_CMD -v -m unit"
elif [[ "$RUN_INTEGRATION" == "true" ]]; then
  # Run only integration tests
  PYTEST_CMD="$PYTEST_CMD -v -m integration"
fi

# Filter by service if specified
if [[ -n "$SERVICE" ]]; then
  PYTEST_CMD="$PYTEST_CMD services/$SERVICE"
fi

# Print the command
echo "Running: $PYTEST_CMD"

# Execute pytest
eval $PYTEST_CMD

# Display results
echo ""
echo "Tests completed!" 