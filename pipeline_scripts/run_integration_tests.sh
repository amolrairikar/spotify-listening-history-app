#!/bin/bash

# Stop script execution on any error
set -e

# Start Docker container running LocalStack for integration tests
echo "Starting LocalStack Docker container..."
docker compose up -d

# Wait for LocalStack to be ready
echo "Checking if LocalStack is ready..."
for i in {1..60}; do
  STATUS=$(curl -s http://localhost:4566/_localstack/health | jq -r '.services | to_entries[] | select(.value == "running") | .key' | wc -l)

  if [ "$STATUS" -ge 1 ]; then
    echo "LocalStack is ready."
    break
  else
    echo "LocalStack not ready yet... ($i/60)"
    sleep 1
  fi
done

if [ "$STATUS" -lt 1 ]; then
  echo "LocalStack did not become ready in time."
  exit 1
fi

# Run integration tests
echo "Running integration tests..."
if ! coverage run --source=src -m behave tests/integration; then
    echo "Integration tests failed!"
    exit 1
fi

# Stop LocalStack Docker container
echo "Stopping LocalStack Docker container..."
docker compose down