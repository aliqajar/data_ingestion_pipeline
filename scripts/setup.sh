#!/bin/bash

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/Scripts/activate

# Install base dependencies
pip install -r requirements/base.txt

# Install service-specific dependencies
pip install -r requirements/collector.txt
pip install -r requirements/consumer.txt
pip install -r requirements/query.txt

# Create .env file from template if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env file from template. Please update the values in .env file."
fi

echo "Setup completed successfully!" 