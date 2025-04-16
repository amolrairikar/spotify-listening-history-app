"""Module for testing one-off utility functions in the Lambda function."""
import unittest
from unittest.mock import patch, MagicMock
import os
import json

import requests
import botocore

from src.lambdas.get_recently_played import (
    encode_string,
    request_access_token,
    is_retryable_exception,
    get_current_unix_timestamp_milliseconds,
    write_to_s3,
    is_localstack_running
)


class TestIsLocalstackRunning(unittest.TestCase):
    """Class for testing is_localstack_running method."""

    @patch('src.lambdas.get_recently_played.requests.get')
    def test_localstack_running(self, mock_get):
        """Tests the method returns True when Localstack is running."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'services': {'s3': 'available', 'lambda': 'available'}}
        mock_get.return_value = mock_response

        result = is_localstack_running(localstack_health_url='http://localhost:4566/_localstack/health')

        self.assertTrue(result)
        mock_get.assert_called_once_with('http://localhost:4566/_localstack/health')

    @patch('src.lambdas.get_recently_played.requests.get')
    def test_localstack_running(self, mock_get):
        """Tests the method returns False when Localstack is running."""
        mock_get.side_effect = requests.RequestException('Connection error')

        result = is_localstack_running(localstack_health_url='http://localhost:4566/_localstack/health')

        self.assertFalse(result)
        mock_get.assert_called_once_with('http://localhost:4566/_localstack/health')


class TestIsRetryableException(unittest.TestCase):
    """Class for testing is_retryable_exception method."""

    def test_retryable_aws_error(self):
        """Test a retryable botocore ClientError with InternalServerError."""
        error_response = {'Error': {'Code': 'InternalServerError'}}
        client_error = botocore.exceptions.ClientError(error_response, 'OperationName')
        self.assertTrue(is_retryable_exception(client_error))


    def test_non_retryable_aws_error(self):
        """Test a non-retryable botocore ClientError with a different error code."""
        error_response = {'Error': {'Code': 'AccessDenied'}}
        client_error = botocore.exceptions.ClientError(error_response, 'OperationName')
        self.assertFalse(is_retryable_exception(client_error))


    def test_retryable_http_error(self):
        """Test a retryable requests HTTPError with status code 429."""
        response_mock = MagicMock()
        response_mock.status_code = 429
        http_error = requests.exceptions.HTTPError(response=response_mock)
        self.assertTrue(is_retryable_exception(http_error))


    def test_non_retryable_http_error(self):
        """Test a non-retryable requests HTTPError with status code 429."""
        response_mock = MagicMock()
        response_mock.status_code = 404
        http_error = requests.exceptions.HTTPError(response=response_mock)
        self.assertFalse(is_retryable_exception(http_error))

    def test_non_retryable_other_exception(self):
        """Test an exception that is neither ClientError nor HTTPError."""
        other_exception = ValueError('Some other exception')
        self.assertFalse(is_retryable_exception(other_exception))


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

    @patch('src.lambdas.get_recently_played.requests.post')
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


    @patch('src.lambdas.get_recently_played.requests.post')
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
                'refresh_token': 'test_refresh_token',
                'client_id': 'test_client_id'
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


    @patch('src.lambdas.get_recently_played.requests.post')
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


    @patch('src.lambdas.get_recently_played.requests.post')
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

        self.assertEqual(mock_post.call_count, 5)


class TestGetCurrentUnixTimestampMilliseconds(unittest.TestCase):
    """Class for testing get_current_unix_timestamp_milliseconds method."""

    @patch('src.lambdas.get_recently_played.time.time')
    def test_mocked_time(self, mock_time):
        """Test the function with a mocked time value."""
        mock_time.return_value = 1700000000.123
        expected_result = str(int(1700000000.123 * 1000))

        result = get_current_unix_timestamp_milliseconds()

        self.assertEqual(result, expected_result)
        self.assertIsInstance(result, str)


class TestWriteToS3(unittest.TestCase):
    """Class for testing the write_to_s3 method."""

    @patch('src.lambdas.get_recently_played.boto3.client')
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