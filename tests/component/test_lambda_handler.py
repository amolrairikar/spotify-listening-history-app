"""Module for component testing of the lambda handler function."""
import unittest
from unittest.mock import patch, MagicMock
import os

import boto3
import botocore
import requests
from moto import mock_aws

from src.lambdas.get_recently_played import lambda_handler


class MockLambdaContext:
    """Mock class for AWS Lambda context."""

    def __init__(self):
        """Initializes mock Lambda context with constant attributes for tests."""
        self.aws_request_id = 'test-request-id'
        self.function_name = 'test-function-name'
        self.function_version = 'test-function-version'


def cleanup_parquet_files():
    """Deletes .parquet files in /tmp directory."""
    tmp_dir = '/tmp'
    for filename in os.listdir(tmp_dir):
        if filename.endswith('.parquet'):
            file_path = os.path.join(tmp_dir, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)


class TestLambdaHandler(unittest.TestCase):
    """Class for testing the lambda_handler function."""

    def setUp(self):
        """Patch environment variables and common dependencies before each test."""
        self.mock_event = {
            'eventType': 'test-event'
        }
        self.env_patcher = patch.dict(
            os.environ,
            {
                'CLIENT_ID': 'test_client_id',
                'CLIENT_SECRET': 'test_client_secret',
                'REDIRECT_URI': 'https://example.com/callback',
                'S3_BUCKET_NAME': 'test-bucket'
            }
        )
        self.env_patcher.start()


    def tearDown(self):
        """Stop all patches after each test."""
        self.env_patcher.stop()
        cleanup_parquet_files()


    @mock_aws
    @patch('src.lambdas.get_recently_played.requests')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_success(self, mock_request_access_token, mock_requests):
        """Tests the happy path of the lambda_handler function."""
        ssm = boto3.client('ssm', region_name='us-east-2')
        ssm.put_parameter(
            Name='refresh_token',
            Value='dummy_token',
            Type='SecureString'
        )
        ssm.put_parameter(
            Name='last_refresh_timestamp',
            Value='1234567890000',
            Type='String'
        )
        s3 = boto3.client('s3')
        s3.create_bucket(
            Bucket='test-bucket',
            CreateBucketConfiguration={'LocationConstraint': 'us-east-2'}
        )
        mock_requests.get.return_value = MagicMock(
            json=lambda: {
                'items': [
                    {'track_id': 1, 'track_name': 'Track A', 'artist': 'Artist 1'},
                    {'track_id': 2, 'track_name': 'Track B', 'artist': 'Artist 2'}
                ]
            },
            raise_for_status=lambda: None
        )
        mock_request_access_token.return_value = MagicMock(
            json=lambda: {'access_token': 'test-access-token', 'refresh_token': 'new-refresh-token'}
        )
        headers = {
            'Authorization': f'Bearer {'test-access-token'}'
        }

        response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

        self.assertEqual(response['statusCode'], 200)
        mock_request_access_token.assert_called_once_with(
            authorization_type='refresh_auth_token',
            auth_token='dummy_token'
        )
        mock_requests.get.assert_called_once_with(
            url='https://api.spotify.com/v1/me/player/recently-played?limit=50&after=1234567890000',
            headers=headers
        )


    @mock_aws
    def test_retrieve_parameter_failure(self):
        """Tests the lambda handler function when retrieving the refresh token or timestamp fails."""
        response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

        self.assertEqual(response['statusCode'], 500)
        self.assertIn('Failed to retrieve parameters from Parameter Store', response['body'])


    @mock_aws
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_refresh_access_token_failure(self, mock_request_access_token):
        """Tests the lambda handler function when refreshing the access token fails."""
        ssm = boto3.client('ssm', region_name='us-east-2')
        ssm.put_parameter(
            Name='refresh_token',
            Value='dummy_token',
            Type='SecureString'
        )
        ssm.put_parameter(
            Name='last_refresh_timestamp',
            Value='1234567890000',
            Type='String'
        )
        response_mock = MagicMock()
        response_mock.status_code = 500
        mock_request_access_token.side_effect = requests.exceptions.HTTPError(response=response_mock)

        response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

        self.assertEqual(response['statusCode'], 500)
        mock_request_access_token.assert_called_once_with(
            authorization_type='refresh_auth_token',
            auth_token='dummy_token'
        )


    @mock_aws
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_no_access_token_returned(self, mock_request_access_token):
        """Tests the lambda handler function if no access token is returned from the Spotify API."""
        ssm = boto3.client('ssm', region_name='us-east-2')
        ssm.put_parameter(
            Name='refresh_token',
            Value='dummy_token',
            Type='SecureString'
        )
        ssm.put_parameter(
            Name='last_refresh_timestamp',
            Value='1234567890000',
            Type='String'
        )
        mock_request_access_token.return_value = MagicMock(
            json=lambda: {'access_token': None, 'refresh_token': 'new-refresh-token'}
        )

        response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

        self.assertEqual(response['statusCode'], 404)
        self.assertIn('No access token found in response', response['body'])
        mock_request_access_token.assert_called_once_with(
            authorization_type='refresh_auth_token',
            auth_token='dummy_token'
        )


    @mock_aws
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_empty_string_access_token_returned(self, mock_request_access_token):
        """Tests the lambda handler function if an empty string access token is returned from the Spotify API."""
        ssm = boto3.client('ssm', region_name='us-east-2')
        ssm.put_parameter(
            Name='refresh_token',
            Value='dummy_token',
            Type='SecureString'
        )
        ssm.put_parameter(
            Name='last_refresh_timestamp',
            Value='1234567890000',
            Type='String'
        )
        mock_request_access_token.return_value = MagicMock(
            json=lambda: {'access_token': '', 'refresh_token': 'new-refresh-token'}
        )

        response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

        self.assertEqual(response['statusCode'], 404)
        self.assertIn('No access token found in response', response['body'])
        mock_request_access_token.assert_called_once_with(
            authorization_type='refresh_auth_token',
            auth_token='dummy_token'
        )


    @mock_aws
    @patch('src.lambdas.get_recently_played.requests.get')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_fetch_tracks_failure(self, mock_request_access_token, mock_requests_get):
        """Tests the lambda handler function if an error occurs while fetching recently played tracks."""
        ssm = boto3.client('ssm', region_name='us-east-2')
        ssm.put_parameter(
            Name='refresh_token',
            Value='dummy_token',
            Type='SecureString'
        )
        ssm.put_parameter(
            Name='last_refresh_timestamp',
            Value='1234567890000',
            Type='String'
        )
        response_mock = MagicMock()
        response_mock.status_code = 500
        response_mock.raise_for_status.side_effect = requests.exceptions.HTTPError()
        mock_requests_get.return_value = response_mock
        mock_request_access_token.return_value = MagicMock(
            json=lambda: {'access_token': 'test-access-token', 'refresh_token': 'new-refresh-token'}
        )
        headers = {
            'Authorization': f'Bearer {'test-access-token'}'
        }

        response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

        self.assertEqual(response['statusCode'], 500)
        self.assertIn('Failed to fetch recently played tracks', response['body'])
        mock_request_access_token.assert_called_once_with(
            authorization_type='refresh_auth_token',
            auth_token='dummy_token'
        )
        mock_requests_get.assert_called_once_with(
            url='https://api.spotify.com/v1/me/player/recently-played?limit=50&after=1234567890000',
            headers=headers
        )


    @mock_aws
    @patch('src.lambdas.get_recently_played.requests')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_write_to_s3_fail(self, mock_request_access_token, mock_requests):
        """Tests the lambda handler function if an error occurs while writing to S3."""
        ssm = boto3.client('ssm', region_name='us-east-2')
        ssm.put_parameter(
            Name='refresh_token',
            Value='dummy_token',
            Type='SecureString'
        )
        ssm.put_parameter(
            Name='last_refresh_timestamp',
            Value='1234567890000',
            Type='String'
        )
        mock_requests.get.return_value = MagicMock(
            json=lambda: {'items': [{'track': 'test-track'}]},
            raise_for_status=lambda: None
        )
        mock_request_access_token.return_value = MagicMock(
            json=lambda: {'access_token': 'test-access-token', 'refresh_token': 'new-refresh-token'}
        )
        headers = {
            'Authorization': f'Bearer {'test-access-token'}'
        }

        with patch('src.lambdas.get_recently_played.write_parquet_to_s3') as mock_write_s3:
            mock_write_s3.side_effect = botocore.exceptions.ClientError(
                {
                    'Error':
                    {
                        'Code': 'InternalServerError', 'Message': 'Internal Server Error.'
                    }
                },
                'UploadFile'
            )

            response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

            self.assertEqual(response['statusCode'], 500)
            self.assertIn('Failed to write data to S3', response['body'])
            mock_request_access_token.assert_called_once_with(
                authorization_type='refresh_auth_token',
                auth_token='dummy_token'
            )
            mock_requests.get.assert_called_once_with(
                url='https://api.spotify.com/v1/me/player/recently-played?limit=50&after=1234567890000',
                headers=headers
            )
            mock_write_s3.assert_called_once()


    @patch('src.lambdas.get_recently_played.ParameterStoreClient')
    @patch('src.lambdas.get_recently_played.requests')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_update_refresh_token_fail(
        self,
        mock_request_access_token,
        mock_requests,
        mock_parameter_store_client
    ):
        """Tests the lambda handler function if an error occurs while updating the refresh token."""
        mock_instance = mock_parameter_store_client.return_value
        mock_instance.get_parameter.side_effect = ['test-refresh-token', '1234567890']
        mock_instance.create_or_update_parameter.side_effect = botocore.exceptions.ClientError(
            {
                'Error':
                {
                    'Code': 'InternalServerError', 'Message': 'Internal Server Error.'
                }
            },
            'PutParameter'
        )
        mock_requests.get.return_value = MagicMock(
            json=lambda: {'items': [{'track': 'test-track'}]},
            raise_for_status=lambda: None
        )
        mock_request_access_token.return_value = MagicMock(
            json=lambda: {'access_token': 'test-access-token', 'refresh_token': 'new-refresh-token'}
        )
        headers = {
            'Authorization': f'Bearer {'test-access-token'}'
        }

        with patch('src.lambdas.get_recently_played.write_parquet_to_s3') as mock_write_s3, \
             patch('src.lambdas.get_recently_played.convert_json_to_parquet') as mock_convert_parquet:
            mock_write_s3.return_value = None
            mock_convert_parquet.return_value = None

            response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

            self.assertEqual(response['statusCode'], 500)
            mock_instance.get_parameter.assert_any_call(
                parameter_name='refresh_token'
            )
            mock_instance.get_parameter.assert_any_call(
                parameter_name='last_refresh_timestamp'
            )
            mock_request_access_token.assert_called_once_with(
                authorization_type='refresh_auth_token',
                auth_token='test-refresh-token'
            )
            mock_requests.get.assert_called_once_with(
                url='https://api.spotify.com/v1/me/player/recently-played?limit=50&after=1234567890',
                headers=headers
            )
            mock_instance.create_or_update_parameter.assert_any_call(
                parameter_name='refresh_token',
                parameter_value='new-refresh-token',
                parameter_type='SecureString',
                overwrite=True,
                parameter_description='Spotify refresh token'
            )
            mock_write_s3.assert_called_once()
            mock_convert_parquet.assert_called_once()


    @patch('src.lambdas.get_recently_played.get_current_unix_timestamp_milliseconds')
    @patch('src.lambdas.get_recently_played.ParameterStoreClient')
    @patch('src.lambdas.get_recently_played.requests')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_no_refresh_token_returned(
        self,
        mock_request_access_token,
        mock_requests,
        mock_parameter_store_client,
        mock_unix_timestamp
    ):
        """Tests the lambda handler function if no refresh token is returned."""
        mock_instance = mock_parameter_store_client.return_value
        mock_instance.get_parameter.side_effect = ['test-refresh-token', '1234567890']
        mock_instance.create_or_update_parameter.side_effect = botocore.exceptions.ClientError(
            {
                'Error':
                {
                    'Code': 'InternalServerError', 'Message': 'Internal Server Error.'
                }
            },
            'PutParameter'
        )
        mock_requests.get.return_value = MagicMock(
            json=lambda: {'items': [{'track': 'test-track'}]},
            raise_for_status=lambda: None
        )
        mock_request_access_token.return_value = MagicMock(
            json=lambda: {'access_token': 'test-access-token'}
        )
        headers = {
            'Authorization': f'Bearer {'test-access-token'}'
        }
        mock_unix_timestamp.return_value = '1700000000123'

        with patch('src.lambdas.get_recently_played.write_parquet_to_s3') as mock_write_s3, \
             patch('src.lambdas.get_recently_played.convert_json_to_parquet') as mock_convert_parquet:
            mock_write_s3.return_value = None
            mock_convert_parquet.return_value = None

            response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

            self.assertEqual(response['statusCode'], 500)
            mock_instance.get_parameter.assert_any_call(
                parameter_name='refresh_token'
            )
            mock_instance.get_parameter.assert_any_call(
                parameter_name='last_refresh_timestamp'
            )
            mock_request_access_token.assert_called_once_with(
                authorization_type='refresh_auth_token',
                auth_token='test-refresh-token'
            )
            mock_requests.get.assert_called_once_with(
                url='https://api.spotify.com/v1/me/player/recently-played?limit=50&after=1234567890',
                headers=headers
            )
            mock_instance.create_or_update_parameter.assert_any_call(
                parameter_name='last_refresh_timestamp',
                parameter_value='1700000000123',
                parameter_type='String',
                overwrite=True,
                parameter_description='Last refresh timestamp for Spotify API'
            )
            mock_write_s3.assert_called_once()
            mock_convert_parquet.assert_called_once()


    @mock_aws
    @patch('src.lambdas.get_recently_played.requests')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_no_tracks_returned(self, mock_request_access_token, mock_requests):
        """Tests the lambda handler function if no tracks are returned from the Spotify API."""
        ssm = boto3.client('ssm', region_name='us-east-2')
        ssm.put_parameter(
            Name='refresh_token',
            Value='dummy_token',
            Type='SecureString'
        )
        ssm.put_parameter(
            Name='last_refresh_timestamp',
            Value='1234567890000',
            Type='String'
        )
        mock_requests.get.return_value = MagicMock(
            json=lambda: {'items': []},
            raise_for_status=lambda: None
        )
        mock_request_access_token.return_value = MagicMock(
            json=lambda: {'access_token': 'test-access-token', 'refresh_token': 'new-refresh-token'}
        )
        headers = {
            'Authorization': f'Bearer {'test-access-token'}'
        }

        response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

        self.assertEqual(response['statusCode'], 204)
        mock_request_access_token.assert_called_once_with(
            authorization_type='refresh_auth_token',
            auth_token='dummy_token'
        )
        mock_requests.get.assert_called_once_with(
            url='https://api.spotify.com/v1/me/player/recently-played?limit=50&after=1234567890000',
            headers=headers
        )
