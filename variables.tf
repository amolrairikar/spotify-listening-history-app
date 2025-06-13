variable "infra_role_arn" {
  description = "The ARN for the role assumed by the Terraform user"
  type        = string
}

variable "email" {
  description = "Developer email to send notifications to"
  type        = string
}

variable "environment" {
  description = "The deployment environment (QA or PROD)"
  type        = string
}

variable "project_name" {
  description = "The name of the project (to be used in tags)"
  type        = string
}

variable "aws_region_name" {
  description = "The AWS region where resources are deployed"
  type        = string
}

variable "datalake_bucket_name" {
  description = "The name of the S3 bucket serving as the project datalake"
  type        = string
}

variable "spotify_client_id" {
  description = "Spotify API client ID"
  type        = string
}

variable "spotify_client_secret" {
  description = "Spotify API client secret"
  type        = string
}