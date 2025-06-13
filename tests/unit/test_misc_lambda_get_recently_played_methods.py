"""Module for testing utility functions in the get recently played tracks Lambda function."""
import unittest
from unittest.mock import patch, MagicMock
import os
import json

import requests

from src.lambdas.get_recently_played.get_recently_played import (
    encode_string,
    request_access_token,
    get_current_unix_timestamp_milliseconds,
    write_to_s3
)


class TestEncodeString(unittest.TestCase):
    """Class for testing encode_string method."""

    def test_encode_regular_string(self):
        """Test encoding of a regular string."""
        input_string = 'hello world'
        expected_output = 'aGVsbG8gd29ybGQ='
        self.assertEqual(encode_string(input_string), expected_output)

    def test_encode_empty_string(self):
        """Test encoding of an empty string."""
        input_string = ''
        expected_output = ''
        self.assertEqual(encode_string(input_string), expected_output)

    def test_encode_special_characters(self):
        """Test encoding of a string with special characters."""
        input_string = '!@#$%^&*()_+'
        expected_output = 'IUAjJCVeJiooKV8r'
        self.assertEqual(encode_string(input_string), expected_output)


class TestRequestAccessToken(unittest.TestCase):
    """Class for testing request_access_token method."""

    def setUp(self):
        """Patch environment variables before each test."""
        self.env_patcher = patch.dict(
            os.environ,
            {
                'CLIENT_ID': 'test_client_id',
                'CLIENT_SECRET': 'test_client_secret',
                'REDIRECT_URI': 'https://example.com/callback'
            }
        )
        self.env_patcher.start()

    def tearDown(self):
        """Stop all patches after each test."""
        self.env_patcher.stop()

    @patch('src.lambdas.get_recently_played.get_recently_played.requests.post')
    def test_initial_auth_success(self, mock_post):
        """Test request_access_token for 'initial_auth' authorization type."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'access_token': 'test_access_token'}
        mock_post.return_value = mock_response

        result = request_access_token(
            authorization_type='initial_auth',
            auth_token='test_auth_code'
        )

        mock_post.assert_called_once_with(
            'https://accounts.spotify.com/api/token',
            data={
                'grant_type': 'authorization_code',
                'code': 'test_auth_code',
                'redirect_uri': 'https://example.com/callback'
            },
            headers={
                'Authorization': 'Basic dGVzdF9jbGllbnRfaWQ6dGVzdF9jbGllbnRfc2VjcmV0',
                'content-type': 'application/x-www-form-urlencoded'
            }
        )
        self.assertEqual(result, mock_response)


    @patch('src.lambdas.get_recently_played.get_recently_played.requests.post')
    def test_refresh_auth_token_success(self, mock_post):
        """Test request_access_token for 'refresh_auth_token' authorization type."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'access_token': 'test_access_token'}
        mock_post.return_value = mock_response

        result = request_access_token(
            authorization_type='refresh_auth_token',
            auth_token='test_refresh_token'
        )

        mock_post.assert_called_once_with(
            'https://accounts.spotify.com/api/token',
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': 'test_refresh_token'
            },
            headers = {
                'Authorization': 'Basic dGVzdF9jbGllbnRfaWQ6dGVzdF9jbGllbnRfc2VjcmV0',
                'content-type': 'application/x-www-form-urlencoded'
            }
        )
        self.assertEqual(result, mock_response)


    def test_invalid_authorization_type(self):
        """Test request_access_token with an invalid authorization type."""
        with self.assertRaises(ValueError) as context:
            request_access_token(
                authorization_type='invalid_auth',
                auth_token='test_token'
            )
        self.assertEqual(
            str(context.exception),
            'Invalid authorization type. Must be "initial_auth" or "refresh_auth_token".'
        )


    @patch('src.lambdas.get_recently_played.get_recently_played.requests.post')
    def test_http_error(self, mock_post):
        """Test request_access_token raises an HTTPError if encountered."""
        response_mock = MagicMock()
        response_mock.status_code = 400
        http_error = requests.exceptions.HTTPError(
            '400 Client Error: Bad Request for url'
        )
        http_error.response = response_mock
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = http_error
        mock_post.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            request_access_token(
                authorization_type='initial_auth',
                auth_token='test_auth_code'
            )

        self.assertEqual(mock_post.call_count, 1)


    @patch('src.lambdas.get_recently_played.get_recently_played.requests.post')
    def test_retry_http_error(self, mock_post):
        """Test request_access_token retrys a retryable HTTPError if encountered."""
        response_mock = MagicMock()
        response_mock.status_code = 429
        http_error = requests.exceptions.HTTPError(
            '429 Client Error: Too many requests'
        )
        http_error.response = response_mock
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = http_error
        mock_post.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            request_access_token(
                authorization_type='initial_auth',
                auth_token='test_auth_code'
            )

        self.assertEqual(mock_post.call_count, 3)


class TestGetCurrentUnixTimestampMilliseconds(unittest.TestCase):
    """Class for testing get_current_unix_timestamp_milliseconds method."""

    @patch('src.lambdas.get_recently_played.get_recently_played.time.time')
    def test_mocked_time(self, mock_time):
        """Test the function with a mocked time value."""
        mock_time.return_value = 1700000000.123
        expected_result = str(int(1700000000.123 * 1000))

        result = get_current_unix_timestamp_milliseconds()

        self.assertEqual(result, expected_result)
        self.assertIsInstance(result, str)


class TestWriteToS3(unittest.TestCase):
    """Class for testing the write_to_s3 method."""

    @patch('src.lambdas.get_recently_played.get_recently_played.boto3.client')
    def test_write_parquet_to_s3_success(self, mock_boto_client):
        """Test writing a Parquet file to S3."""
        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client
        json_data = {'key': 'value'}

        write_to_s3(
            bucket_name='test-bucket',
            object_key='test-key',
            json_data=json_data
        )

        mock_s3_client.put_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='test-key',
            Body=json.dumps(json_data),
            ContentType='application/json'
        )