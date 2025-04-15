#!/bin/bash

# Start Docker container running LocalStack for integration tests
echo "Starting LocalStack Docker container..."
docker compose up -d

# Wait for LocalStack to be ready
STATUS=0
echo "Checking if LocalStack services are ready (Lambda, SSM, S3)..."
for i in {1..60}; do
    RESPONSE=$(curl -s http://localhost:4566/_localstack/health)
    if echo "$RESPONSE" | grep -q '"lambda": *"available"' && \
       echo "$RESPONSE" | grep -q '"s3": *"available"' && \
       echo "$RESPONSE" | grep -q '"ssm": *"available"'; then
        echo "All required LocalStack services are available."
        STATUS=1
        break
    else
        echo "Waiting for services to become available... ($i/60)"
        sleep 1
    fi
done

if [ "$STATUS" -lt 1 ]; then
    echo "LocalStack did not become ready in time."
    exit 1
fi

# Run integration tests
echo "Running integration tests..."
if ! behave tests/integration --no-capture --format=pretty; then
    echo "Integration tests failed!"
    exit 1
fi

# Stop LocalStack Docker container
echo "Stopping LocalStack Docker container..."
docker compose down