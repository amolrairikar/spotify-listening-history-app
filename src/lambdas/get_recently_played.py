"""Module containing code for Lambda function to fetch data from user's recently played tracks endpoint."""
from typing import Optional, Dict, Any
from functools import wraps
import base64
import os
import logging
import time
import datetime
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
# TODO: convert the logging level into an environment variable
logger = logging.getLogger('spotify-listening-history-app')
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# Function to dynamically determine if LocalStack is running and set endpoint URL accordingly
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
        logger.error(f'Error checking LocalStack status, assuming LocalStack is not running')
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


class ParameterStoreClient:
    """Class to interact with AWS SSM Parameter Store."""

    def __init__(self, region: str):
        if AWS_ENDPOINT_URL:
            self.client = boto3.client('ssm', region_name=region, endpoint_url=AWS_ENDPOINT_URL)
        else:
            self.client = boto3.client('ssm', region_name=region)


    @backoff_on_client_error
    def check_parameter_exists(
        self,
        parameter_name: str
    ) -> bool:
        """Check if a parameter exists in AWS Parameter Store."""
        try:
            self.client.get_parameter(Name=parameter_name)
            return True
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'ParameterNotFound':
                return False
            else:
                raise e


    @backoff_on_client_error 
    def create_or_update_parameter(
        self,
        parameter_name: str,
        parameter_value: str,
        parameter_type: str,
        overwrite: bool = True,
        parameter_description: str = None,
    ):
        """Creates or updates a parameter with parameter_name in AWS Parameter Store."""
        if overwrite:
            self.client.put_parameter(
                Name=parameter_name,
                Description=parameter_description,
                Value=parameter_value,
                Type=parameter_type,
                Overwrite=overwrite,
                Tier='Standard',
                DataType='text'
            )
        else:
            self.client.put_parameter(
                Name=parameter_name,
                Description=parameter_description,
                Value=parameter_value,
                Type=parameter_type,
                Overwrite=overwrite,
                Tier='Standard',
                Tags=[
                    {
                        'Key': 'environment',
                        'Value': 'prod'
                    },
                    {
                        'Key': 'project',
                        'Value': 'spotifyListeningHistoryApp'
                    }
                ],
                DataType='text'
            )

    @backoff_on_client_error
    def get_parameter(self, parameter_name: str) -> Optional[str]:
        """Retrieves a parameter value from AWS Parameter Store."""
        response = self.client.get_parameter(
            Name=parameter_name,
            WithDecryption=True
        )
        return response.get('Parameter', {}).get('Value', None)


def encode_string(input_string: str) -> str:
    """Encodes a string using base64 encoding."""
    string_bytes = input_string.encode('utf-8')
    base64_bytes = base64.b64encode(string_bytes)
    return base64_bytes.decode('utf-8')


def get_current_unix_timestamp_milliseconds() -> str:
    """Returns the current Unix timestamp in milliseconds."""
    return str(int(time.time() * 1000))


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


@backoff_on_client_error
def request_access_token(authorization_type: str, auth_token: str) -> Dict[str, Any]:
    """Sends a request to exchange the authorization code for access/refresh tokens."""
    token_url = 'https://accounts.spotify.com/api/token'
    encoded_key = encode_string(
        input_string=f'{os.environ["CLIENT_ID"]}:{os.environ["CLIENT_SECRET"]}'
    )
    # logger.debug(f'Encoded key: {encoded_key}')
    headers = {
        'Authorization': 'Basic ' + encoded_key,
        'content-type': 'application/x-www-form-urlencoded'
    }
    if authorization_type == 'initial_auth':
        logger.info('Performing manual initial authorization flow')
        data = {
            'grant_type': 'authorization_code',
            'code': auth_token,
            'redirect_uri': os.getenv('REDIRECT_URI')
        }
    elif authorization_type == 'refresh_auth_token':
        logger.info('Refreshing access token using refresh token')
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': auth_token
        }
    else:
        raise ValueError('Invalid authorization type. Must be "initial_auth" or "refresh_auth_token".')
    # logger.debug(f'Request data: {data}')
    # logger.debug(f'Request headers: {headers}')
    response = requests.post(token_url, data=data, headers=headers)
    response.raise_for_status()
    return response


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main handler function for the Lambda fetching recently played tracks."""
    # Log basic information about the Lambda function
    logger.info('Begin Lambda execution')
    logger.info(f'Lambda request ID: {context.aws_request_id}')
    logger.info(f'Lambda function name: {context.function_name}')
    logger.info(f'Lambda function version: {context.function_version}')
    logger.info(f'Event: {event}')

    # Refresh access token to make API calls
    try:
        parameter_store_client = ParameterStoreClient(region='us-east-2')  # TODO: Try to avoid hardcoding region
        refresh_token = parameter_store_client.get_parameter(parameter_name='spotify_refresh_token')
        # logger.debug(f'Refresh token: {refresh_token}')
        logger.info('Successfully retrieved refresh token from Parameter Store')
        last_refresh_timestamp = parameter_store_client.get_parameter(parameter_name='spotify_last_fetched_time')
        logger.debug(f'Last refresh timestamp: {last_refresh_timestamp}')
        logger.info('Successfully retrieved last refresh timestamp from Parameter Store')
    except botocore.exceptions.ClientError as e:
        error_message = f'Failed to retrieve parameters from Parameter Store: {str(e)}'
        logger.error(error_message)
        return {
            'statusCode': 500,
            'body': error_message
        }

    # Refresh access token using refresh token
    try:
        tokens = request_access_token(
            authorization_type='refresh_auth_token',
            auth_token=refresh_token
        )
        access_token = tokens.json().get('access_token')
        refresh_token = tokens.json().get('refresh_token')
        if not access_token or access_token == '':
            error_message = 'No access token found in response.'
            logger.error(error_message)
            return {
                'statusCode': 404,
                'body': error_message
            }
        logger.info('Successfully refreshed access token')
    except requests.exceptions.HTTPError as e:
        error_message = f'Failed to refresh access token: {str(e)}'
        logger.error(error_message)
        return {
            'statusCode': 500,
            'body': error_message
        }

    # Use access token to make API request
    recently_played_url = f'https://api.spotify.com/v1/me/player/recently-played?limit=50&after={last_refresh_timestamp}'
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    logger.debug(f'Recently played URL: {recently_played_url}')
    # logger.debug(f'Request header: {headers}')
    try:
        response = requests.get(url=recently_played_url, headers=headers)
        response.raise_for_status()
        recently_played_data = response.json()
        logger.info('Successfully fetched recently played tracks')
    except requests.exceptions.HTTPError as e:
        error_message = f'Failed to fetch recently played tracks: {str(e)}'
        logger.error(error_message)
        return {
            'statusCode': 500,
            'body': error_message
        }

    # Check if any tracks were returned since the last refresh timestamp
    if recently_played_data.get('items', []):
        logger.info(f'Number of recently played tracks: {len(recently_played_data.get("items", []))}')
        recently_played_songs_data = recently_played_data['items']
        # Hardcoding timezone to central for myself
        cst_timezone = pytz.timezone('America/Chicago')
        current_timestamp = datetime.datetime.now(cst_timezone).strftime('%Y%m%d%H%M%S')
        object_path = f'raw/recently_played_tracks_{current_timestamp}.json'
        try:
            write_to_s3(
                bucket_name=os.environ['S3_BUCKET_NAME'],
                object_key=object_path,
                json_data=recently_played_songs_data
            )
            logger.info('Successfully wrote data to S3')
        except botocore.exceptions.ClientError as e:
            error_message = f'Failed to write data to S3: {str(e)}'
            logger.error(error_message)
            return {
                'statusCode': 500,
                'body': error_message
            }

        # Update refresh token and last refresh timestamp in Parameter Store
        try:
            if refresh_token:
                parameter_store_client.create_or_update_parameter(
                    parameter_name='spotify_refresh_token',
                    parameter_value=refresh_token,
                    parameter_type='SecureString',
                    overwrite=True,
                    parameter_description='Spotify refresh token'
                )
                logger.info('Successfully updated refresh token in Parameter Store')
            else:
                logger.info('No new refresh token provided')
            last_refresh_timestamp = get_current_unix_timestamp_milliseconds()
            parameter_store_client.create_or_update_parameter(
                parameter_name='spotify_last_fetched_time',
                parameter_value=last_refresh_timestamp,
                parameter_type='String',
                overwrite=True,
                parameter_description='Last refresh timestamp for Spotify API'
            )
            logger.info('Successfully updated last refresh timestamp in Parameter Store')
            return {
                'statusCode': 200,
                'body': 'Execution successful'
            }
        except botocore.exceptions.ClientError as e:
            error_message = f'Failed to update parameters in Parameter Store: {str(e)}'
            logger.error(error_message)
            return {
                'statusCode': 500,
                'body': error_message
            }
    else:
        logger_message = 'No recently played tracks found.'
        logger.info(logger_message)
        return {
            'statusCode': 204,
            'body': logger_message
        }
