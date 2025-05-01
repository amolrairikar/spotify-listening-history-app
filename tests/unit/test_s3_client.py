import unittest
from unittest.mock import patch, MagicMock
import json

import botocore

from src.lambdas.etl_process.perform_etl import S3Client


class TestS3Client(unittest.TestCase):
    """Class for testing the S3Client class."""

    @patch('src.lambdas.etl_process.perform_etl.boto3.client')
    def test_read_json_from_s3_success(self, mock_boto_client):
        """Test successful reading of JSON data from S3."""
        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client
        mock_response = {
            'Body': MagicMock(read=MagicMock(return_value=json.dumps({'key': 'value'}).encode('utf-8')))
        }
        mock_s3_client.get_object.return_value = mock_response
        s3_client = S3Client(region='us-east-1')
        result = s3_client.read_json_from_s3(bucket='test-bucket', object='test-object.json')

        self.assertEqual(result, {'key': 'value'})
        mock_s3_client.get_object.assert_called_once_with(Bucket='test-bucket', Key='test-object.json')

    @patch('src.lambdas.etl_process.perform_etl.boto3.client')
    def test_read_json_from_s3_client_error(self, mock_boto_client):
        """Test reading JSON data from S3 with a ClientError."""
        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client
        mock_s3_client.get_object.side_effect = botocore.exceptions.ClientError(
            error_response={'Error': {'Code': 'NoSuchKey'}},
            operation_name='GetObject'
        )
        s3_client = S3Client(region='us-east-1')

        with self.assertRaises(botocore.exceptions.ClientError):
            s3_client.read_json_from_s3(bucket='test-bucket', object='nonexistent-object.json')

        mock_s3_client.get_object.assert_called_once_with(Bucket='test-bucket', Key='nonexistent-object.json')

    @patch('src.lambdas.etl_process.perform_etl.boto3.client')
    def test_write_json_to_s3_success(self, mock_boto_client):
        """Test successful writing of JSON data to S3."""
        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client
        s3_client = S3Client(region='us-east-1')
        json_data = {'key': 'value'}
        s3_client.write_json_to_s3(json_data=json_data, bucket='test-bucket', object='test-object.json')

        mock_s3_client.put_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='test-object.json',
            Body=json.dumps(json_data),
            ContentType='application/json'
        )

    @patch('src.lambdas.etl_process.perform_etl.boto3.client')
    def test_write_json_to_s3_client_error(self, mock_boto_client):
        """Test writing JSON data to S3 with a ClientError."""
        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client
        mock_s3_client.put_object.side_effect = botocore.exceptions.ClientError(
            error_response={'Error': {'Code': 'AccessDenied'}},
            operation_name='PutObject'
        )
        s3_client = S3Client(region='us-east-1')
        json_data = {'key': 'value'}

        with self.assertRaises(botocore.exceptions.ClientError):
            s3_client.write_json_to_s3(json_data=json_data, bucket='test-bucket', object='test-object.json')

        mock_s3_client.put_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='test-object.json',
            Body=json.dumps(json_data),
            ContentType='application/json'
        )