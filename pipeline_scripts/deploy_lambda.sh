#!/bin/bash

FUNCTION_NAME="my-lambda-function"
ZIP_FILE="lambda_deploy.zip"
REGION="us-east-2"
RUNTIME="python3.11"
HANDLER="lambda_function.lambda_handler"
ROLE_ARN="${ROLE_ARN}"

echo "Deploying Lambda function: $FUNCTION_NAME"

if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" > /dev/null 2>&1; then
  echo "Lambda function exists. Updating code..."
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file fileb://"$ZIP_FILE" \
    --region "$REGION"
else
  echo "Creating new Lambda function..."
  aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime "$RUNTIME" \
    --role "$ROLE_ARN" \
    --handler "$HANDLER" \
    --zip-file fileb://"$ZIP_FILE" \
    --region "$REGION"
fi
