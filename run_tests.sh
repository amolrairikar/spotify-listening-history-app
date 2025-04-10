#!/bin/bash

# Stop script execution on any error
set -e

# Run unit tests
echo "Running unit tests..."
if ! pipenv run coverage run --source=src -m unittest discover -s tests/unit; then
    echo "Unit tests failed!"
    exit 1
fi
mv .coverage .coverage.unit  # Move the coverage data to .coverage.unit

# Run component tests
echo "Running component tests..."
if ! pipenv run coverage run --source=src -m unittest discover -s tests/component; then
    echo "Component tests failed!"
    exit 1
fi
mv .coverage .coverage.component  # Move the coverage data to .coverage.component

# Combine the coverage data
echo "Combining coverage data..."
pipenv run coverage combine .coverage.unit .coverage.component

# Generate coverage report
echo "Generating coverage report..."
pipenv run coverage report --omit="tests/*" --fail-under=80

echo "Test execution complete!"
