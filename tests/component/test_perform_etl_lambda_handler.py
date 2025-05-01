"""Module for component testing of the get recently played lambda handler function."""
import unittest
import json

import boto3
from moto import mock_aws

from src.lambdas.etl_process.perform_etl import lambda_handler
from tests.helpers.mock_raw_api_s3_file import MOCK_RAW_API_S3_FILE
from tests.helpers.mock_s3_event import MOCK_S3_EVENT


class MockLambdaContext:
    """Mock class for AWS Lambda context."""

    def __init__(self):
        """Initializes mock Lambda context with constant attributes for tests."""
        self.aws_request_id = 'test-request-id'
        self.function_name = 'test-function-name'
        self.function_version = 'test-function-version'


class TestLambdaHandler(unittest.TestCase):
    """Class for testing the lambda_handler function."""

    def setUp(self):
        """Patch common dependencies before each test."""
        self.mock_event = {
            'eventType': 'test-event'
        }


    @mock_aws
    def test_etl_success(self):
        """Tests the happy path of the lambda_handler function."""
        s3 = boto3.client('s3')
        s3.create_bucket(
            Bucket='bucket-name',
            CreateBucketConfiguration={'LocationConstraint': 'us-east-2'}
        )
        s3.put_object(
            Bucket='bucket-name',
            Key='raw/recently_played_tracks_20250425140632.json',
            Body=json.dumps(MOCK_RAW_API_S3_FILE).encode('utf-8')
        )

        response = lambda_handler(
            event=MOCK_S3_EVENT,
            context=MockLambdaContext()
        )

        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(response['body'], 'Execution successful')


    @mock_aws
    def test_etl_no_bucket(self):
        """Tests the case where no bucket is provided in the S3 event."""
        with self.assertRaises(KeyError) as context:
            lambda_handler(
                event={
                    'Records': [
                        {
                            's3': {
                                'bucket': {
                                    'name': ''
                                }
                            }
                        }
                    ]
                },
                context=MockLambdaContext()
            )
        self.assertEqual(str(context.exception), "'No bucket name provided in S3 notification event'")


    @mock_aws
    def test_etl_no_object(self):
        """Tests the case where no object is provided in the S3 event."""
        with self.assertRaises(KeyError) as context:
            lambda_handler(
                event={
                    'Records': [
                        {
                            's3': {
                                'bucket': {
                                    'name': 'bucket-name'
                                },
                                'object': {
                                    'key': ''
                                }
                            }
                        }
                    ]
                },
                context=MockLambdaContext()
            )
        self.assertEqual(str(context.exception), "'No object name provided in S3 notification event'")