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
MEMORY_SIZE=512  # in MB
HANDLER="get_recently_played.lambda_handler"
ROLE_ARN="${ROLE_ARN}"

echo "Deploying Lambda function: $FUNCTION_NAME"

if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" > /dev/null 2>&1; then
    echo "Lambda function exists. Updating code..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb://"$ZIP_FILE" \
        --region "$REGION"
    check_error "Updating Lambda function code"

    echo "Updating Lambda function environment variables..."
    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --environment Variables={$ENV_VARS} \
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
        --environment Variables={$ENV_VARS}
    check_error "Creating new Lambda function"
fi
