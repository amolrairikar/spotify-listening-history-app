"""Module containing ETL code for Lambda function to write processed Spotify listening history data to S3."""
from typing import Dict, Any, Tuple, List
import logging
import json
import uuid

import boto3
import pytz
import datetime
from dotenv import load_dotenv
from retry_api_exceptions import backoff_on_client_error

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


def convert_utc_to_cst(utc_string: str) -> str:
    """Converts a UTC datetime string to America/Chicago time."""
    utc_time = datetime.datetime.strptime(utc_string, '%Y-%m-%dT%H:%M:%S.%fZ')
    utc_timezone = pytz.utc
    cst_timezone = pytz.timezone('America/Chicago')
    utc_time = utc_timezone.localize(utc_time)
    return utc_time.astimezone(cst_timezone).strftime('%Y-%m-%dT%H:%M:%S')


def milliseconds_to_mmss(track_length: int) -> str:
    """Converts a track length in milliseconds to mm:ss length"""
    if track_length <= 0:
        raise ValueError('Track length must be greater than 0 seconds')
    total_seconds = track_length / 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f'{int(minutes):02}:{int(seconds):02}'


def get_bucket_and_object(event: Dict[str, Any]) -> Tuple[str, str]:
    """Gets the S3 bucket and object from the event payload that triggered the ETL lambda."""
    event_details = event.get('Records', [])
    if event_details:
        bucket = event_details[0].get('s3', {}).get('bucket', {}).get('name', '')
        object = event_details[0].get('s3', {}).get('object', {}).get('key', '')
        return bucket, object
    raise Exception('No data present in event payload')


def perform_etl(json_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Performs ETL by selecting fields for analytics from raw Spotify API response."""
    processed_data = {}
    for item in json_data:
        track_uri = item['track']['uri']
        processed_data[track_uri] = {
            'album': item['track']['album']['name'],
            'release_date': item['track']['album']['release_date'],
            'artists': [artist['name'] for artist in item['track']['artists']],
            'track_length': milliseconds_to_mmss(track_length=item['track']['duration_ms']),
            'track_name': item['track']['name'],
            'track_url': item['track']['external_urls']['spotify'],
            'track_popularity': item['track']['popularity'],
            'played_at': convert_utc_to_cst(utc_string=item['played_at'])
        }
    return processed_data


def partition_spotify_data(track_data: Dict[str, Any]) -> Dict[Tuple[str, str], Any]:
    """Partitions data into year/month buckets based on the played_at field."""
    partitions = {}
    for track_id, track_info in track_data.items():
        year = track_info['played_at'].split('-')[0]
        month = track_info['played_at'].split('-')[1]
        partition_key = (year, month)
        if partition_key not in partitions:
            partitions[partition_key] = []
        track_record = {'track_id': track_id, **track_info}
        partitions[partition_key].append(track_record)
    return partitions


class S3Client:
    "Class to interact with objects in S3."

    def __init__(self, region: str):
        self.client = boto3.client('s3', region_name=region)


    @backoff_on_client_error
    def read_json_from_s3(self, bucket: str, object: str) -> List[Dict[str, Any]]:
        """Reads a JSON file corresponding to an object in a bucket."""
        response = self.client.get_object(
            Bucket=bucket,
            Key=object
        )
        logger.info(f'Successfully read file at s3://{bucket}/{object}')
        return json.loads(response['Body'].read().decode('utf-8'))
    

    @backoff_on_client_error
    def write_json_to_s3(self, json_data: Dict[str, Any], bucket: str, object: str) -> None:
        """Writes a JSON file to S3."""
        self.client.put_object(
            Bucket=bucket,
            Key=object,
            Body=json.dumps(json_data),
            ContentType='application/json'
        )
        logger.info(f'Successfully wrote {len(json_data)} records to s3://{bucket}/{object}')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main handler function for the Lambda performing ETL on the raw JSON API response data."""
    # Log basic information about the Lambda function
    logger.info('Begin Lambda execution')
    logger.info(f'Lambda request ID: {context.aws_request_id}')
    logger.info(f'Lambda function name: {context.function_name}')
    logger.info(f'Lambda function version: {context.function_version}')
    logger.info(f'Event: {event}')

    bucket, object = get_bucket_and_object(event=event)
    if not bucket or bucket == '':
        raise KeyError('No bucket name provided in S3 notification event')
    if not object or object == '':
        raise KeyError('No object name provided in S3 notification event')

    s3_client = S3Client(region='us-east-2')
    response = s3_client.read_json_from_s3(bucket=bucket, object=object)
    processed_data = perform_etl(json_data=response)
    partitioned_data = partition_spotify_data(track_data=processed_data)
    for (year, month), records in partitioned_data.items():
        file_name = f'tracks_{uuid.uuid4()}.json'
        s3_key = f'processed/year={year}/month={month}/{file_name}'
        s3_client.write_json_to_s3(json_data=records, bucket=bucket, object=s3_key)

    return {
        'statusCode': 200,
        'body': 'Execution successful'
    }