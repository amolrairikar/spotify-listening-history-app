#!/bin/bash

# Function to check command success
check_error() {
    if [ $? -ne 0 ]; then
        echo "Error: $1 failed." >&2
        exit 1
    fi
}

FUNCTION_NAME="spotify-listening-history-lambda"
ZIP_FILE="lambda_function.zip"
REGION="us-east-2"
RUNTIME="python3.12"
MEMORY_SIZE=512
HANDLER="get_recently_played.lambda_handler"
ROLE_ARN="${ROLE_ARN}"
ENV_VARS="Variables={\"CLIENT_ID\":\"$CLIENT_ID\",\"CLIENT_SECRET\":\"$CLIENT_SECRET\",\"S3_BUCKET_NAME\":\"$S3_BUCKET_NAME\"}"

echo "Deploying Lambda function: $FUNCTION_NAME"

if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" > /dev/null 2>&1; then
    echo "Lambda function exists. Updating code..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb://"$ZIP_FILE" \
        --region "$REGION"
    check_error "Updating Lambda function code"

    # Wait for AWS to finish updating the code before updating config
    aws lambda wait function-updated \
        --function-name "$FUNCTION_NAME" \
        --region "$REGION"
    check_error "Waiting for Lambda function update"

    echo "Updating Lambda function environment variables..."
    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --environment "$ENV_VARS" \
        --memory-size "$MEMORY_SIZE" \
        --region "$REGION"
    check_error "Updating Lambda function environment variables"
else
    echo "Creating new Lambda function..."
    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime "$RUNTIME" \
        --role "$ROLE_ARN" \
        --handler "$HANDLER" \
        --zip-file fileb://"$ZIP_FILE" \
        --region "$REGION" \
        --memory-size "$MEMORY_SIZE" \
        --environment "$ENV_VARS" \
        --tags "environment=prod,project=spotifyListeningHistoryApp"
    check_error "Creating new Lambda function"
fi
