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

module "eventbridge_role" {
  source                    = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/iam-role?ref=main"
  role_name                 = "eventbridge-role"
  trust_relationship_policy = data.aws_iam_policy_document.eventbridge_trust_relationship_policy.json
  environment               = var.environment
  project                   = var.project_name
}

data "aws_iam_policy_document" "eventbridge_role_policy_document" {
  statement {
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [module.spotify_lambda.lambda_arn]
  }
}

resource "aws_iam_policy" "eventbridge_role_policy" {
  name        = "eventbridge-scheduler-trigger-lambda"
  description = "IAM policy allowing EventBridge scheduler to trigger Lambda functions"
  policy      = data.aws_iam_policy_document.eventbridge_role_policy_document.json
}

resource "aws_iam_role_policy_attachment" "eventbridge_role_policy_attachment" {
  role       = module.eventbridge_role.role_name
  policy_arn = aws_iam_policy.eventbridge_role_policy.arn
}

module "eventbridge_scheduler" {
  source               = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/eventbridge-scheduler?ref=main"
  eventbridge_role_arn = module.eventbridge_role.role_arn
  lambda_arn           = module.spotify_lambda.lambda_arn
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

module "lambda_role" {
  source                    = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/iam-role?ref=main"
  role_name                 = "spotify-listening-history-lambda-execution-role"
  trust_relationship_policy = data.aws_iam_policy_document.lambda_trust_relationship_policy.json
  environment               = var.environment
  project                   = var.project_name
}

data "aws_iam_policy_document" "lambda_execution_role_policy_document" {
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
      "arn:aws:s3:::${var.datalake_bucket_name}/*"
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

resource "aws_iam_policy" "lambda_role_policy" {
  name        = "${module.lambda_role.role_name}-inline-policy"
  description = "IAM policy for Spotify Lambda function role"
  policy      = data.aws_iam_policy_document.lambda_execution_role_policy_document.json
}

resource "aws_iam_role_policy_attachment" "eventbridge_role_policy_attachment" {
  role       = module.lambda_role.role_name
  policy_arn = aws_iam_policy.lambda_role_policy.arn
}

module "spotify_lambda" {
  source                    = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/lambda?ref=main"
  environment               = var.environment
  project                   = var.project_name
  lambda_name               = "spotify-listening-history-lambda"
  lambda_description        = "Lambda function to fetch recently played tracks from Spotify API"
  lambda_filename           = "lambda_function.zip"
  lambda_handler            = "get_recently_played.lambda_handler"
  lambda_memory_size        = "256"
  lambda_runtime            = "python3.12"
  lambda_execution_role_arn = module.lambda_role.role_arn
  sns_topic_arn             = module.sns_email_subscription.topic_arn
}

module "sns_email_subscription" {
  source         = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/sns-email-subscription?ref=main"
  sns_topic_name = "lambda-failure-notification-topic"
  user_email     = var.email
  environment    = var.environment
  project        = var.project_name
}