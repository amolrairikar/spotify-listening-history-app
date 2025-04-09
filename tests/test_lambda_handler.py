"""Module for testing one-off utility functions in the Lambda function."""
import unittest
from unittest.mock import patch, MagicMock
import os

import botocore
import requests

from src.lambdas.get_recently_played import lambda_handler


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


    @patch('src.lambdas.get_recently_played.get_current_unix_timestamp_milliseconds')
    @patch('src.lambdas.get_recently_played.ParameterStoreClient')
    @patch('src.lambdas.get_recently_played.requests')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_success(
        self,
        mock_request_access_token,
        mock_requests,
        mock_parameter_store_client,
        mock_unix_timestamp
    ):
        """Tests the happy path of the lambda_handler function."""
        mock_instance = mock_parameter_store_client.return_value
        mock_instance.get_parameter.side_effect = ['test-refresh-token', '1234567890']
        mock_instance.create_or_update_parameter.return_value = None
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
        mock_unix_timestamp.return_value = '1700000000123'

        with patch('src.lambdas.get_recently_played.write_parquet_to_s3') as mock_write_s3, \
             patch('src.lambdas.get_recently_played.convert_json_to_parquet') as mock_convert_parquet:
            mock_write_s3.return_value = None
            mock_convert_parquet.return_value = None

            response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

            self.assertEqual(response['statusCode'], 200)
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
            mock_instance.create_or_update_parameter.assert_any_call(
                parameter_name='last_refresh_timestamp',
                parameter_value='1700000000123',
                parameter_type='String',
                overwrite=True,
                parameter_description='Last refresh timestamp for Spotify API'
            )
            mock_write_s3.assert_called_once()
            mock_convert_parquet.assert_called_once()


    @patch('src.lambdas.get_recently_played.ParameterStoreClient')
    def test_retrieve_parameter_failure(
        self,
        mock_parameter_store_client
    ):
        """Tests the lambda handler function when retrieving the refresh token or timestamp fails."""
        mock_instance = mock_parameter_store_client.return_value
        mock_instance.get_parameter.side_effect = botocore.exceptions.ClientError(
            {
                'Error':
                {
                    'Code': 'InternalServerError', 'Message': 'Internal Server Error.'
                }
            },
            'GetParameter'
        )

        response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

        self.assertEqual(response['statusCode'], 500)
        mock_instance.get_parameter.assert_any_call(
            parameter_name='refresh_token'
        )


    @patch('src.lambdas.get_recently_played.ParameterStoreClient')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_refresh_access_token_failure(
        self,
        mock_request_access_token,
        mock_parameter_store_client
    ):
        """Tests the lambda handler function when refreshing the access token fails."""
        mock_instance = mock_parameter_store_client.return_value
        mock_instance.get_parameter.side_effect = ['test-refresh-token', '1234567890']
        response_mock = MagicMock()
        response_mock.status_code = 500
        mock_request_access_token.side_effect = requests.exceptions.HTTPError(response=response_mock)

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


    @patch('src.lambdas.get_recently_played.ParameterStoreClient')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_no_access_token_returned(
        self,
        mock_request_access_token,
        mock_parameter_store_client
    ):
        """Tests the lambda handler function if no access token is returned from the Spotify API."""
        mock_instance = mock_parameter_store_client.return_value
        mock_instance.get_parameter.side_effect = ['test-refresh-token', '1234567890']
        mock_request_access_token.return_value = MagicMock(
            json=lambda: {'access_token': None, 'refresh_token': 'new-refresh-token'}
        )

        response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

        self.assertEqual(response['statusCode'], 404)
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


    @patch('src.lambdas.get_recently_played.ParameterStoreClient')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_empty_string_access_token_returned(
        self,
        mock_request_access_token,
        mock_parameter_store_client
    ):
        """Tests the lambda handler function if an empty string access token is returned from the Spotify API."""
        mock_instance = mock_parameter_store_client.return_value
        mock_instance.get_parameter.side_effect = ['test-refresh-token', '1234567890']
        mock_request_access_token.return_value = MagicMock(
            json=lambda: {'access_token': '', 'refresh_token': 'new-refresh-token'}
        )

        response = lambda_handler(event=self.mock_event, context=MockLambdaContext())

        self.assertEqual(response['statusCode'], 404)
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


    @patch('src.lambdas.get_recently_played.ParameterStoreClient')
    @patch('src.lambdas.get_recently_played.requests.get')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_fetch_tracks_failure(
        self,
        mock_request_access_token,
        mock_requests_get,
        mock_parameter_store_client
    ):
        """Tests the lambda handler function if an error occurs while fetching recently played tracks."""
        mock_instance = mock_parameter_store_client.return_value
        mock_instance.get_parameter.side_effect = ['test-refresh-token', '1234567890']
        mock_instance.create_or_update_parameter.return_value = None
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
        mock_requests_get.assert_called_once_with(
            url='https://api.spotify.com/v1/me/player/recently-played?limit=50&after=1234567890',
            headers=headers
        )


    @patch('src.lambdas.get_recently_played.ParameterStoreClient')
    @patch('src.lambdas.get_recently_played.requests')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_write_to_s3_fail(
        self,
        mock_request_access_token,
        mock_requests,
        mock_parameter_store_client
    ):
        """Tests the lambda handler function if an error occurs while writing to S3."""
        mock_instance = mock_parameter_store_client.return_value
        mock_instance.get_parameter.side_effect = ['test-refresh-token', '1234567890']
        mock_instance.create_or_update_parameter.return_value = None
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
            mock_write_s3.side_effect = botocore.exceptions.ClientError(
                {
                    'Error':
                    {
                        'Code': 'InternalServerError', 'Message': 'Internal Server Error.'
                    }
                },
                'UploadFile'
            )
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
            mock_write_s3.assert_called_once()
            mock_convert_parquet.assert_called_once()


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


    @patch('src.lambdas.get_recently_played.ParameterStoreClient')
    @patch('src.lambdas.get_recently_played.requests')
    @patch('src.lambdas.get_recently_played.request_access_token')
    def test_no_tracks_returned(
        self,
        mock_request_access_token,
        mock_requests,
        mock_parameter_store_client
    ):
        """Tests the lambda handler function if no tracks are returned from the Spotify API."""
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
