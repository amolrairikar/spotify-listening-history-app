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
  project        = "spotifyListeningHistoryApp"
}

data "aws_iam_policy_document" "eventbridge_trust_relationship_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = "scheduler.amazonaws.com"
    }
  }
}

module "eventbridge_role" {
  source                    = "git::https://github.com/amolrairikar/aws-account-infrastructure.git//modules/iam-role?ref=main"
  role_name                 = "eventbridge-role"
  trust_relationship_policy = data.aws_iam_policy_document.eventbridge_trust_relationship_policy.json
  environment               = var.environment
  project                   = "spotifyListeningHistoryApp"
}

output "eventbridge_role_name" {
  value = module.eventbridge_role.role_name
}

output "eventbridge_role_arn" {
  value = module.eventbridge_role.role_arn
}

data "aws_iam_policy_document" "eventbridge_role_policy_document" {
  statement {
    effect = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [var.lambda_arn]
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
  lambda_arn           = var.lambda_arn
  environment          = "prod"
  project              = "spotifyListeningHistoryApp"
}