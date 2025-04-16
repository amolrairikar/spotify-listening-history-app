#!/bin/bash

# Function to check command success
check_error() {
    if [ $? -ne 0 ]; then
        echo "Error: $1 failed." >&2
        exit 1
    fi
}

LAMBDA_ROLE_NAME="spotify-listening-history-lambda-execution-role"
POLICY_FILE="iam/lambda-execution-policy.json"
REGION="us-east-2"

# Trust policy for Lambda service
read -r -d '' TRUST_POLICY <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
        "Effect": "Allow",
        "Principal": {
            "Service": "lambda.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
        }
    ]
}
EOF

TRUST_POLICY_FILE="/tmp/trust-policy.json"
echo "$TRUST_POLICY" > "$TRUST_POLICY_FILE"
check_error "Creating trust policy file"

echo "Checking if IAM role '$LAMBDA_ROLE_NAME' exists..."

if aws iam get-role --role-name "$LAMBDA_ROLE_NAME" > /dev/null 2>&1; then
    echo "IAM role '$LAMBDA_ROLE_NAME' already exists."
else
    echo "Creating IAM role '$LAMBDA_ROLE_NAME'..."
    aws iam create-role \
        --role-name "$LAMBDA_ROLE_NAME" \
        --assume-role-policy-document "file://$TRUST_POLICY_FILE" \
        --region "$REGION"
    check_error "Creating IAM role '$LAMBDA_ROLE_NAME'"
fi

# Substitute the placeholders in the policy file
sed "s|{{ACCOUNT_ID}}|$ACCOUNT_ID|g; s|{{S3_BUCKET_NAME}}|$S3_BUCKET_NAME|g" \
    iam/lambda-execution-policy.json.tpl > /tmp/lambda-policy.json
check_error "Substituting placeholders in policy file"

echo "Attaching policy to role..."
aws iam put-role-policy \
    --role-name "$LAMBDA_ROLE_NAME" \
    --policy-name lambda-inline-policy \
    --policy-document file:///tmp/lambda-policy.json \
    --region "$REGION"
check_error "Attaching policy to IAM role"

ROLE_ARN=$(aws iam get-role --role-name "$LAMBDA_ROLE_NAME" --query 'Role.Arn' --output text)
check_error "Retrieving IAM role ARN"
echo "ROLE_ARN=$ROLE_ARN" >> $GITHUB_ENV