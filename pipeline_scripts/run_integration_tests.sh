#!/bin/bash

# Stop script execution on any error
set -e

# Start Docker container running LocalStack for integration tests
echo "Starting LocalStack Docker container..."
docker compose up -d

# Wait for LocalStack to be ready
echo "Checking if LocalStack is ready..."
# TODO: insert code to check if LocalStack is ready here

# Run integration tests
echo "Running integration tests..."
if ! pipenv run coverage run --source=src -m behave tests/integration; then
    echo "Integration tests failed!"
    exit 1
fi
mv .coverage .coverage.integration  # Move the coverage data to .coverage.integration

# Stop LocalStack Docker container
echo "Stopping LocalStack Docker container..."
docker compose down

# Delete the artifacts generated for zipping the Lambda function
echo "Cleaning up artifacts..."
# TODO: insert code to delete build directory and .zip file here