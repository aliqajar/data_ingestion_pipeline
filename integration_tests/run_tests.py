#!/usr/bin/env python
"""
Test runner for the Weather System Pipeline tests.
Run this script to execute unit tests, integration tests, or both.
"""

import os
import sys
import argparse
import subprocess

def main():
    parser = argparse.ArgumentParser(description='Run Weather System Pipeline tests')
    parser.add_argument('--unit', action='store_true', help='Run unit tests only')
    parser.add_argument('--integration', action='store_true', help='Run integration tests only')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    parser.add_argument('--service', type=str, help='Run tests for a specific service (collector, consumer, query)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show verbose output')
    
    args = parser.parse_args()
    
    # Default to running all tests if no specific option is provided
    if not (args.unit or args.integration or args.all or args.service):
        args.all = True
    
    # Build the pytest command
    cmd = ["pytest"]
    
    # Add verbosity
    if args.verbose:
        cmd.append("-v")
    
    # Add test selection
    if args.unit:
        cmd.extend([
            "services/collector/tests/",
            "services/consumer/tests/",
            "services/query/tests/"
        ])
    elif args.integration:
        cmd.append("integration_tests/")
    elif args.service:
        valid_services = ["collector", "consumer", "query"]
        if args.service not in valid_services:
            print(f"Error: Invalid service '{args.service}'. Must be one of: {', '.join(valid_services)}")
            sys.exit(1)
        
        cmd.append(f"services/{args.service}/tests/")
    elif args.all:
        cmd.extend([
            "services/collector/tests/",
            "services/consumer/tests/",
            "services/query/tests/",
            "integration_tests/"
        ])
    
    # Add pretty output
    cmd.extend(["-v", "--color=yes"])
    
    # Print the command being run
    print(f"Running: {' '.join(cmd)}")
    
    # Run the tests
    result = subprocess.run(cmd)
    
    sys.exit(result.returncode)

if __name__ == "__main__":
    main() 