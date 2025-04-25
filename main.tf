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

module "spotify_project_data_bucket" {
  source         = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/s3-bucket-private?ref=main"
  bucket_prefix  = "spotify-listening-history-app-data-lake"
  account_number = var.account_number
  environment    = var.environment
  project        = var.project_name
}

data "aws_iam_policy_document" "eventbridge_trust_relationship_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "eventbridge_role_inline_policy_document" {
  statement {
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [module.spotify_get_recently_played_lambda.lambda_arn]
  }
}

module "eventbridge_role" {
  source                    = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/iam-role?ref=main"
  role_name                 = "eventbridge-role"
  trust_relationship_policy = data.aws_iam_policy_document.eventbridge_trust_relationship_policy.json
  inline_policy             = data.aws_iam_policy_document.eventbridge_role_inline_policy_document.json
  inline_policy_description = "Policy for EventBridge Scheduler to invoke Lambda functions"
  environment               = var.environment
  project                   = var.project_name
}

module "eventbridge_scheduler" {
  source               = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/eventbridge-scheduler?ref=main"
  eventbridge_role_arn = module.eventbridge_role.role_arn
  lambda_arn           = module.spotify_get_recently_played_lambda.lambda_arn
  environment          = var.environment
  project              = var.project_name
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
        "arn:aws:ssm:us-east-2:${var.account_number}:parameter/spotify_refresh_token",
        "arn:aws:ssm:us-east-2:${var.account_number}:parameter/spotify_last_fetched_time"
    ]
  }
  statement {
    effect    = "Allow"
    actions = [
      "s3:PutObject"
    ]
    resources = [
      "arn:aws:s3:::${var.datalake_bucket_name}/raw/*"
    ]
  }
  statement {
    effect    = "Allow"
    actions = [
      "sns:Publish"
    ]
    resources = [
      module.sns_email_subscription.topic_arn
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
  lambda_name                    = "spotify-listening-history-lambda"
  lambda_description             = "Lambda function to fetch recently played tracks from Spotify API"
  lambda_filename                = "get_recently_played.zip"
  lambda_handler                 = "get_recently_played.lambda_handler"
  lambda_memory_size             = "256"
  lambda_runtime                 = "python3.12"
  lambda_execution_role_arn      = module.lambda_get_recently_played_role.role_arn
  sns_topic_arn                  = module.sns_email_subscription.topic_arn
    lambda_environment_variables = {
      CLIENT_ID      = var.spotify_client_id
      CLIENT_SECRET  = var.spotify_client_secret
      S3_BUCKET_NAME = var.datalake_bucket_name
  }
}

module "sns_email_subscription" {
  source         = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/sns-email-subscription?ref=main"
  sns_topic_name = "lambda-failure-notification-topic"
  user_email     = var.email
  environment    = var.environment
  project        = var.project_name
}

module "s3_trigger_lambda_etl" {
  source               = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/s3-lambda-trigger?ref=main"
  bucket_name          = module.spotify_project_data_bucket.bucket_id
  bucket_arn           = module.spotify_project_data_bucket.bucket_arn
  lambda_function_name = "spotify-etl-lambda"
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
      "arn:aws:s3:::${var.datalake_bucket_name}/processed/*"
    ]
  }
  statement {
    effect    = "Allow"
    actions = [
      "s3:GetObject"
    ]
    resources = [
      "arn:aws:s3:::${var.datalake_bucket_name}/raw/*"
    ]
  }
  statement {
    effect    = "Allow"
    actions   = [
      "s3:ListBucket"
    ]
    resources = [
      "arn:aws:s3:::${var.datalake_bucket_name}"
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
      module.sns_email_subscription.topic_arn
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
  lambda_name                    = "spotify-etl-lambda"
  lambda_description             = "Lambda function to perform ETL on Spotify API recently played tracks response raw JSON"
  lambda_filename                = "perform_etl.zip"
  lambda_handler                 = "perform_etl.lambda_handler"
  lambda_memory_size             = "256"
  lambda_runtime                 = "python3.12"
  lambda_execution_role_arn      = module.lambda_get_recently_played_role.role_arn
  sns_topic_arn                  = module.sns_email_subscription.topic_arn
    lambda_environment_variables = {
      S3_BUCKET_NAME = var.datalake_bucket_name
  }
}