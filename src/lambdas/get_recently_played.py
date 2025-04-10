"""Module containing code for Lambda function to fetch data from user's recently played tracks endpoint."""
from typing import Optional, Dict, Any
from functools import wraps
import base64
import os
import logging
import time
import datetime
import pytz

import boto3
import botocore
import botocore.exceptions
import backoff
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logger
logger = logging.getLogger('spotify-listening-history-app')
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


def is_retryable_exception(e: botocore.exceptions.ClientError | requests.exceptions.HTTPError) -> bool:
    """Checks if the returned exception is retryable."""
    if isinstance(e, botocore.exceptions.ClientError):
        return e.response['Error']['Code'] in [
            'InternalServerError'
        ]
    elif isinstance(e, requests.exceptions.HTTPError):
        return e.response.status_code in [
            429, 500, 502, 503
        ]
    return False


def backoff_on_client_error(func):
    """Reusable decorator to retry API calls for server errors."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        instance_or_class = None

        # If the function is a method, extract `self` or `cls`
        if args and hasattr(args[0], func.__name__):
            instance_or_class, *args = args  # Extract `self` or `cls`

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


def convert_json_to_parquet(json_data: Dict[str, Any], output_path: str) -> None:
    """Converts nested Spotify API response JSON data to Parquet format."""
    df = pd.json_normalize(data=json_data, sep='.')
    table = pa.Table.from_pandas(df)

    # Ensure the directory exists before writing the file
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    logger.info('Writing data to Parquet file...')
    pq.write_table(table=table, where=output_path, compression='snappy')
    logger.info(f'Successfully wrote data to Parquet file at {output_path}')


@backoff_on_client_error
def write_parquet_to_s3(bucket_name: str, object_key: str, file_path: str) -> None:
    """Writes a Parquet file to an S3 bucket."""
    s3_client = boto3.client('s3')  # TODO: Try to avoid hardcoding region
    logger.info(f'Uploading {file_path} to s3://{bucket_name}/{object_key}...')
    s3_client.upload_file(Filename=file_path, Bucket=bucket_name, Key=object_key)
    logger.info(f'Successfully uploaded {file_path} to s3://{bucket_name}/{object_key}')


@backoff_on_client_error
def request_access_token(authorization_type: str, auth_token: str) -> Dict[str, Any]:
    """Sends a request to exchange the authorization code for access/refresh tokens."""
    token_url = 'https://accounts.spotify.com/api/token'
    encoded_key = encode_string(
        input_string=f'{os.environ["CLIENT_ID"]}:{os.environ["CLIENT_SECRET"]}'
    )
    headers = {
        'Authorization': 'Basic ' + encoded_key,
        'content-type': 'application/x-www-form-urlencoded'
    }
    if authorization_type == 'initial_auth':
        data = {
            'grant_type': 'authorization_code',
            'code': auth_token,
            'redirect_uri': os.environ['REDIRECT_URI']
        }
    elif authorization_type == 'refresh_auth_token':
        data = {
            'grant_type': 'authorization_code',
            'refresh_token': auth_token,
            'client_id': os.environ['CLIENT_ID']
        }
    else:
        raise ValueError('Invalid authorization type. Must be "initial_auth" or "refresh_auth_token".')
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
        refresh_token = parameter_store_client.get_parameter(parameter_name='refresh_token')
        logger.info('Successfully retrieved refresh token from Parameter Store')
        last_refresh_timestamp = parameter_store_client.get_parameter(parameter_name='last_refresh_timestamp')
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

    # Convert data into parquet to write to S3
    if recently_played_data.get('items', []):
        output_path = '/tmp/recently_played_tracks.parquet'
        convert_json_to_parquet(
            json_data=recently_played_data,
            output_path=output_path
        )
        # Hardcoding timezone to central for myself
        cst_timezone = pytz.timezone('America/Chicago')
        current_time_cst = datetime.datetime.now(cst_timezone)
        current_timestamp = current_time_cst.strftime('%Y%m%d%H%M%S')
        partition_path = f'{current_time_cst.year}/{current_time_cst.strftime('%m')}/{current_time_cst.strftime('%d')}/recently_played_tracks_{current_timestamp}.parquet'
        logger.info(f'Partition path: {partition_path}')
        try:
            write_parquet_to_s3(
                bucket_name=os.environ['S3_BUCKET_NAME'],
                object_key=partition_path,
                file_path=output_path
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
                    parameter_name='refresh_token',
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
                parameter_name='last_refresh_timestamp',
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

# Uncomment the below code for local testing of the Lambda function

# class MockLambdaContext:
#     """Mock class for AWS Lambda context."""

#     def __init__(self):
#         """Initializes mock Lambda context with constant attributes for tests."""
#         self.aws_request_id = 'test-request-id'
#         self.function_name = 'test-function-name'
#         self.function_version = 'test-function-version'

# response = lambda_handler(
#     event={
#         'body': {
#             'code': 'sample_code',
#             'state': 'sample_state'
#         }
#     },
#     context=MockLambdaContext()
# )