variable "infra_role_arn" {
  description = "The ARN for the role assumed by the Terraform user"
  type        = string
}

variable "account_number" {
  description = "The AWS account number"
  type        = string
}

variable "environment" {
  description = "The deployment environment (QA or PROD)"
  type        = string
}

variable "lambda_arn" {
  description = "The ARN for the Spotify listening history Lambda function"
  type        = string
}