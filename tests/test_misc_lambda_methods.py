"""Module for testing one-off utility functions in the Lambda function."""
import unittest
from unittest.mock import patch, MagicMock
import os
from tempfile import TemporaryDirectory

import requests
import botocore
import pandas as pd
import pyarrow.parquet as pq

from src.lambdas.get_recently_played import (
    encode_string,
    request_access_token,
    is_retryable_exception,
    get_current_unix_timestamp_milliseconds,
    convert_json_to_parquet,
    write_parquet_to_s3
)


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
                'grant_type': 'authorization_code',
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


class TestConvertJsonToParquet(unittest.TestCase):
    """Class for testing the convert_json_to_parquet method."""
    def setUp(self):
        """Set up a temporary directory for test output files."""
        self.temp_dir = TemporaryDirectory()
        self.output_path = os.path.join(self.temp_dir.name, 'test_output.parquet')

    def tearDown(self):
        """Clean up the temporary directory."""
        self.temp_dir.cleanup()

    def test_valid_json_input(self):
        """Test with a valid nested JSON object."""
        json_data = {
            'track': {
                'name': 'Song A',
                'artist': 'Artist A'
            },
            'played_at': '2025-01-01T00:00:00Z'
        }
        expected_df = pd.DataFrame(
            [
                {
                    'played_at': '2025-01-01T00:00:00Z',
                    'track.name': 'Song A',
                    'track.artist': 'Artist A'
                }
            ]
        )

        convert_json_to_parquet(json_data, self.output_path)

        self.assertTrue(os.path.exists(self.output_path))
        table = pq.read_table(self.output_path)
        df = table.to_pandas()
        pd.testing.assert_frame_equal(df, expected_df)

    def test_invalid_output_path(self):
        """Test with an invalid output path."""
        json_data = {
            'track': {
                'name': 'Song A',
                'artist': 'Artist A'
            },
            'played_at': '2025-01-01T00:00:00Z'
        }
        invalid_path = '/invalid_path/test_output.parquet'

        with self.assertRaises(OSError):
            convert_json_to_parquet(json_data, invalid_path)

    def test_json_with_special_characters(self):
        """Test with a JSON object where artist names contain special characters."""
        json_data = {
            'track': {
                'name': 'Søng B',
                'artist': 'Ärtist B'
            },
            'played_at': '2025-01-02T00:00:00Z'
        }
        expected_df = pd.DataFrame(
            [
                {
                    'played_at': '2025-01-02T00:00:00Z',
                    'track.name': 'Søng B',
                    'track.artist': 'Ärtist B'
                }
            ]
        )

        convert_json_to_parquet(json_data, self.output_path)

        self.assertTrue(os.path.exists(self.output_path))
        table = pq.read_table(self.output_path)
        df = table.to_pandas()
        pd.testing.assert_frame_equal(df, expected_df)


class TestWriteParquetToS3(unittest.TestCase):
    """Class for testing the write_parquet_to_s3 method."""

    @patch('src.lambdas.get_recently_played.boto3.client')
    def test_write_parquet_to_s3_success(self, mock_boto_client):
        """Test writing a Parquet file to S3."""
        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client

        write_parquet_to_s3(
            bucket_name='test-bucket',
            object_key='test-key',
            file_path='/tmp/test.parquet'
        )

        mock_s3_client.upload_file.assert_called_once_with(
            Filename='/tmp/test.parquet',
            Bucket='test-bucket',
            Key='test-key'
        )