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


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main handler function for the Lambda performing ETL on the raw JSON API response data."""
    # Log basic information about the Lambda function
    logger.info('Begin Lambda execution')
    logger.info(f'Lambda request ID: {context.aws_request_id}')
    logger.info(f'Lambda function name: {context.function_name}')
    logger.info(f'Lambda function version: {context.function_version}')
    logger.info(f'Event: {event}')

    return {
        'statusCode': 200,
        'body': 'Execution successful'
    }