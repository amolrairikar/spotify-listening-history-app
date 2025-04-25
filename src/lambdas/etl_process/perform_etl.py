"""Module containing ETL code for Lambda function to write processed Spotify listening history data to S3."""
from typing import Dict, Any
from functools import wraps
import logging
import json

import boto3
import botocore
import botocore.exceptions
import backoff
import pytz
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logger
logger = logging.getLogger('spotify-listening-history-app-etl')
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# Function to dynamically determine if LocalStack is running and set endpoint URL accordingly
# TODO: see if this function and the retry wrapper can be turned into a Lambda layer
def is_localstack_running(localstack_health_url: str):
    try:
        response = requests.get(localstack_health_url)
        if response.status_code == 200:
            data = response.json()
            logger.debug(f'LocalStack health check response: {data}')
            for service, status in data.get('services', {}).items():
                if status not in ('available', 'running'):
                    logger.warning(f'LocalStack service {service} is not available.')
                    return False
            logger.info('LocalStack is running and all services are available.')
            return True
    except requests.RequestException as e:
        logger.warning(f'LocalStack health endpoint not found')
        pass
    return False


if is_localstack_running(localstack_health_url='http://localstack:4566/_localstack/health'):
    logger.info('Setting endpoint URL to http://localstack:4566')
    AWS_ENDPOINT_URL = 'http://localstack:4566'
else:
    logger.info('Setting endpoint URL to None')
    AWS_ENDPOINT_URL = None


def is_retryable_exception(e: botocore.exceptions.ClientError | requests.exceptions.HTTPError) -> bool:
    """Checks if the returned exception is retryable."""
    if isinstance(e, botocore.exceptions.ClientError):
        return e.response['Error']['Code'] in [
            'InternalServerError'
        ]
    elif isinstance(e, requests.exceptions.HTTPError):
        return e.response.status_code in [
            429, 500, 502, 503, 504
        ]
    return False


def backoff_on_client_error(func):
    """Reusable decorator to retry API calls for server errors."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        instance_or_class = None

        # If the function is a method, extract `self` or `cls`
        if args and hasattr(args[0], func.__name__):
            instance_or_class, *args = args

        @backoff.on_exception(
            backoff.expo,
            (botocore.exceptions.ClientError, requests.exceptions.HTTPError),
            max_tries=5,
            giveup=lambda e: not is_retryable_exception(e),
            on_success=lambda details: print(f"Success after {details['tries']} tries"),
            on_giveup=lambda details: print(f"Giving up after {details['tries']} tries"),
            on_backoff=lambda details: print(f"Backing off after {details['tries']} tries due to {details['exception']}")
        )
        def retryable_call(*args, **kwargs):
            if instance_or_class:
                return func(instance_or_class, *args, **kwargs)  # Call method
            return func(*args, **kwargs)  # Call standalone function

        return retryable_call(*args, **kwargs)

    return wrapper


def perform_etl(raw_json_data: Dict[str, Any]) -> Dict[str, Any]:
    """Performs ETL on raw Spotify listening history data by extracting fields necessary for
        reporting from raw API response JSON."""
    return raw_json_data


@backoff_on_client_error
def write_to_s3(bucket_name: str, object_key: str, json_data: str) -> None:
    """Writes JSON data to an S3 bucket."""
    json_string = json.dumps(json_data)
    if AWS_ENDPOINT_URL:
        s3_client = boto3.client('s3', endpoint_url=AWS_ENDPOINT_URL)
    else:
        s3_client = boto3.client('s3')
    logger.info(f'Uploading data to s3://{bucket_name}/{object_key}...')
    s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=json_string,
        ContentType='application/json'
    )
    logger.info(f'Successfully uploaded data to s3://{bucket_name}/{object_key}')


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main handler function for the Lambda performing ETL on the raw JSON API response data."""
    # Log basic information about the Lambda function
    logger.info('Begin Lambda execution')
    logger.info(f'Lambda request ID: {context.aws_request_id}')
    logger.info(f'Lambda function name: {context.function_name}')
    logger.info(f'Lambda function version: {context.function_version}')
    logger.info(f'Event: {event}')

    # Perform ETL