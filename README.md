# spotify-listening-history-app
Streamlit web app to visualize my Spotify listening history. Listening history is obtained through Spotify's Get Recently Played Tracks [endpoint](https://developer.spotify.com/documentation/web-api/reference/get-recently-played). The architecture diagram below demonstrates the end-to-end application flow.

![alt text](Spotify%20API%20Project%20Architecture.png)

# Setup instructions

## Spotify setup
You will need to create a Spotify application in order to obtain a client ID and client secret that can be exchanged for a bearer token to make API calls with. Spotify has a nice guide you can refer to [here](https://developer.spotify.com/documentation/web-api/concepts/apps) that walks through the process of creating an application.

## AWS setup
You will need to create your own AWS account in order to deploy the various AWS resources that execute the application logic. AWS offers a generous free tier for many of its services so there should be minimal to no costs associated with this project.

1. Follow the items in Steps 1-3 for creating an AWS account using the AWS documentation [here](https://docs.aws.amazon.com/accounts/latest/reference/manage-acct-creating.html)
2. Create a SNS topic + subscription that will be used to receive notifications about Lambda function failures. I have created a [repository](https://github.com/amolrairikar/aws-account-infrastructure) of reusable Terraform modules since I have a few projects in my AWS account. You can use the module like in this [example](https://github.com/amolrairikar/aws-account-infrastructure-setup/blob/main/main.tf#L215-L221) or refer to the Terraform [docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic) if you need additional customization in your SNS topic that my module does not have. You can also create the SNS topic + subscription manually through the console if you don't want to manage it via Terraform.

## GitHub setup
You will need to add a few secrets to your repository for the CI/CD pipeline to work correctly.

- `AWS_ACCOUNT_ID`: The account number for your AWS account
- `CLIENT_ID`: The client ID for your Spotify application
- `CLIENT_SECRET`: The client secret for your Spotify application
- `EMAIL`: The email you used to sign up for your AWS account. This will be the email that Lambda function failure notifications will be sent to.
- `S3_BUCKET_NAME`: The name of the S3 bucket that will be storing your Spotify recently played data
- `S3_STATE_BUCKET_NAME`: The name of the S3 bucket that will be storing the Terraform state file
- `SNS_TOPIC_ARN`: The Amazon Resource Name (ARN) of the SNS topic that receives notifications about Lambda failures
- `TF_VAR_INFRA_ROLE_ARN`: The Amazon Resource Name (ARN) of the IAM role that Terraform uses to deploy infrastructure

## Running the auth flow manually
You will need to run the manual auth flow once using the command `pipenv run python -m src.spotify_auth.auth_flow`.

## Running the Streamlit app locally
You can open the Streamlit app in a local browser window using the command `pipenv run streamlit run main.py`

## Final app
You can view the example Streamlit web app for my listening history [here](https://spotify-listening-history-app-dxnofv5whhfh6esgsgotg5.streamlit.app/).
