#!/bin/bash

# Initialize Terraform
echo "Initializing Terraform..."
terraform init \
  -backend-config="bucket=${S3_STATE_BUCKET_NAME}" \
  -backend-config="key=spotify-listening-history-app/terraform.tfstate" \
  -backend-config="region=us-east-2" \
  -backend-config="assume_role={role_arn=\"${TF_VAR_infra_role_arn}\", session_name=\"terraform-session\"}"

# Plan the Terraform configuration
echo "Planning Terraform configuration..."
terraform plan -out=tfplan

# Apply the Terraform configuration
echo "Applying Terraform configuration..."
# terraform apply -auto-approve tfplan
