terraform {
  backend "s3" {}
}

provider "aws" {
  region = "us-east-2"
  assume_role {
    role_arn     = var.infra_role_arn
    session_name = "terraform-session"
  }
}

data "aws_caller_identity" "current" {}

module "spotify_project_data_bucket" {
  source            = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/s3-bucket-private?ref=main"
  bucket_name       = "spotify-listening-history-app-data-lake-${data.aws_caller_identity.current.account_id}-${var.environment}"
  account_number    = data.aws_caller_identity.current.account_id
  environment       = var.environment
  project           = var.project_name
  versioning_status = "Enabled"
  enable_acl        = false
  object_ownership  = "BucketOwnerEnforced"
}

module "eventbridge_scheduler" {
  source               = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/eventbridge-scheduler?ref=main"
  eventbridge_role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/eventbridge-role"
  lambda_arn           = module.spotify_get_recently_played_lambda.lambda_arn
  schedule_frequency   = "rate(1 hour)"
  schedule_timezone    = "America/Chicago"
  schedule_state       = "ENABLED"
  scheduler_name       = "spotify-listening-history-app-eventbridge-scheduler"
}

data "aws_lambda_layer_version" "latest_retry_api" {
  layer_name = "retry_api_exceptions"
}

data "aws_iam_policy_document" "lambda_trust_relationship_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "lambda_get_recently_played_execution_role_inline_policy_document" {
  statement {
    effect    = "Allow"
    actions = [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:PutParameter"
    ]
    resources = [
        "arn:aws:ssm:us-east-2:${data.aws_caller_identity.current.account_id}:parameter/spotify_refresh_token",
        "arn:aws:ssm:us-east-2:${data.aws_caller_identity.current.account_id}:parameter/spotify_last_fetched_time"
    ]
  }
  statement {
    effect    = "Allow"
    actions = [
      "s3:PutObject"
    ]
    resources = [
      "arn:aws:s3:::${module.spotify_project_data_bucket.bucket_id}/raw/*"
    ]
  }
  statement {
    effect    = "Allow"
    actions = [
      "sns:Publish"
    ]
    resources = [
      "arn:aws:sns:${var.aws_region_name}:${data.aws_caller_identity.current.account_id}:lambda-failure-notification-topic"
    ]
  }
  statement {
    effect    = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "*"
    ]
  }
}

module "lambda_get_recently_played_role" {
  source                    = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/iam-role?ref=main"
  role_name                 = "spotify-lambda-get-recently-played-execution-role"
  trust_relationship_policy = data.aws_iam_policy_document.lambda_trust_relationship_policy.json
  inline_policy             = data.aws_iam_policy_document.lambda_get_recently_played_execution_role_inline_policy_document.json
  inline_policy_description = "Inline policy for Spotify Lambda function execution role"
  environment               = var.environment
  project                   = var.project_name
}

module "spotify_get_recently_played_lambda" {
  source                         = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/lambda?ref=main"
  environment                    = var.environment
  project                        = var.project_name
  lambda_name                    = "spotify-listening-history"
  lambda_description             = "Lambda function to fetch recently played tracks from Spotify API"
  lambda_filename                = "get_recently_played.zip"
  lambda_handler                 = "get_recently_played.lambda_handler"
  lambda_memory_size             = "256"
  lambda_runtime                 = "python3.12"
  lambda_timeout                 = 30
  lambda_execution_role_arn      = module.lambda_get_recently_played_role.role_arn
  lambda_layers                  = [data.aws_lambda_layer_version.latest_retry_api.arn]
  sns_topic_arn                  = "arn:aws:sns:${var.aws_region_name}:${data.aws_caller_identity.current.account_id}:lambda-failure-notification-topic"
    lambda_environment_variables = {
      CLIENT_ID      = var.spotify_client_id
      CLIENT_SECRET  = var.spotify_client_secret
      S3_BUCKET_NAME = module.spotify_project_data_bucket.bucket_id
  }
}

module "s3_trigger_lambda_etl" {
  source               = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/s3-lambda-trigger?ref=main"
  bucket_name          = module.spotify_project_data_bucket.bucket_id
  bucket_arn           = module.spotify_project_data_bucket.bucket_arn
  lambda_function_name = "spotify-etl"
  lambda_function_arn  = module.spotify_etl_lambda.lambda_arn
  events               = ["s3:ObjectCreated:*"]
  filter_prefix        = "raw/"
  filter_suffix        = ".json"
}

data "aws_iam_policy_document" "lambda_etl_execution_role_inline_policy_document" {
  statement {
    effect    = "Allow"
    actions = [
      "s3:PutObject"
    ]
    resources = [
      "arn:aws:s3:::${module.spotify_project_data_bucket.bucket_id}/processed/*"
    ]
  }
  statement {
    effect    = "Allow"
    actions = [
      "s3:GetObject"
    ]
    resources = [
      "arn:aws:s3:::${module.spotify_project_data_bucket.bucket_id}/raw/*"
    ]
  }
  statement {
    effect    = "Allow"
    actions   = [
      "s3:ListBucket"
    ]
    resources = [
      "arn:aws:s3:::${module.spotify_project_data_bucket.bucket_id}"
    ]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*", "processed/*"]
    }
  }
  statement {
    effect    = "Allow"
    actions = [
      "sns:Publish"
    ]
    resources = [
      "arn:aws:sns:${var.aws_region_name}:${data.aws_caller_identity.current.account_id}:lambda-failure-notification-topic"
    ]
  }
  statement {
    effect    = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "*"
    ]
  }
}

module "lambda_etl_role" {
  source                    = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/iam-role?ref=main"
  role_name                 = "spotify-lambda-etl-execution-role"
  trust_relationship_policy = data.aws_iam_policy_document.lambda_trust_relationship_policy.json
  inline_policy             = data.aws_iam_policy_document.lambda_etl_execution_role_inline_policy_document.json
  inline_policy_description = "Inline policy for Spotify Lambda ETL function execution role"
  environment               = var.environment
  project                   = var.project_name
}

module "spotify_etl_lambda" {
  source                         = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/lambda?ref=main"
  environment                    = var.environment
  project                        = var.project_name
  lambda_name                    = "spotify-etl"
  lambda_description             = "Lambda function to perform ETL on Spotify API recently played tracks response raw JSON"
  lambda_filename                = "etl_process.zip"
  lambda_handler                 = "perform_etl.lambda_handler"
  lambda_memory_size             = "256"
  lambda_runtime                 = "python3.12"
  lambda_timeout                 = 30
  lambda_execution_role_arn      = module.lambda_etl_role.role_arn
  lambda_layers                  = [data.aws_lambda_layer_version.latest_retry_api.arn]
  sns_topic_arn                  = "arn:aws:sns:${var.aws_region_name}:${data.aws_caller_identity.current.account_id}:lambda-failure-notification-topic"
    lambda_environment_variables = {
      S3_BUCKET_NAME = module.spotify_project_data_bucket.bucket_id
  }
}