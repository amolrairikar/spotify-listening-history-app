"""Module for testing parameterStoreClient class."""
import unittest
from unittest.mock import patch, MagicMock

import botocore
import botocore.exceptions

from src.lambdas.get_recently_played import parameterStoreClient

class testParameterStoreClient(unittest.TestCase):
    """Class for testing methods in parameterStoreClient class."""

    @patch.object(parameterStoreClient, '__init__',lambda x: None)
    def setUp(self):
        """Sets up each test case."""
        self.parameterStoreClient = parameterStoreClient()
        self.parameterStoreClient.client = MagicMock()


    def tearDown(self):
        """Stops all patches after each test case."""
        patch.stopall()


    def test_check_parameter_exists(self):
        """Tests that check_parameter_exists returns True when parameter exists
            and False when parameter does not exist."""
        parameter_not_found_exception = botocore.exceptions.ClientError(
            {
                'Error':
                {
                    'Code': 'ParameterNotFound', 'Message': 'The parameter was not found.'
                }
            },
            'GetParameter'
        )
        self.parameterStoreClient.client.get_parameter.side_effect = [
            {
                'Parameter':
                {
                    'Name': 'test_parameter',
                    'Value': 'test_value'
                }
            },
            parameter_not_found_exception
        ]

        result = self.parameterStoreClient.check_parameter_exists(parameter_name='test_parameter')
        self.assertTrue(result)
        self.parameterStoreClient.client.get_parameter.assert_any_call(Name='test_parameter')

        result = self.parameterStoreClient.check_parameter_exists(parameter_name='nonexistent_parameter')
        self.assertFalse(result)
        self.parameterStoreClient.client.get_parameter.assert_any_call(Name='nonexistent_parameter')


    def test_internal_server_error(self):
        """Tests that class methods are retried if an InternalServerError occurs."""
        server_exception = botocore.exceptions.ClientError(
            {
                'Error':
                {
                    'Code': 'InternalServerError', 'Message': 'Internal Server Error.'
                }
            },
            'GetParameter'
        )
        self.parameterStoreClient.client.get_parameter.side_effect = [
            {
                'Parameter':
                {
                    'Name': 'test_parameter',
                    'Value': 'test_value'
                }
            },
            server_exception
        ]
        retry_counter = [0]

        def count_retries(*args, **kwargs):
            retry_counter[0] += 1
            raise server_exception
        
        self.parameterStoreClient.client.get_parameter.side_effect = count_retries
        with self.assertRaises(botocore.exceptions.ClientError):
            self.parameterStoreClient.check_parameter_exists(parameter_name='test_parameter')

        self.assertGreater(retry_counter[0], 1)


    def test_create_or_update_parameter(self):
        """Tests the create_or_update_parameter method."""
        self.parameterStoreClient.create_or_update_parameter(
            parameter_name='test_parameter',
            parameter_value='test_value',
            parameter_type='SecureString',
            overwrite=True,
            parameter_description='Test description'
        )

        self.parameterStoreClient.client.put_parameter.assert_called_once_with(
            Name='test_parameter',
            Description='Test description',
            Value='test_value',
            Type='SecureString',
            Overwrite=True,
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


    def test_get_parameter(self):
        """Tests the get_parameter method."""
        self.parameterStoreClient.client.get_parameter.return_value = {
            'Parameter':
            {
                'Name': 'test_parameter',
                'Value': 'test_value'
            }
        }

        result = self.parameterStoreClient.get_parameter(
            parameter_name='test_parameter'
        )

        self.assertEqual(result, 'test_value')
        self.parameterStoreClient.client.get_parameter.assert_called_once_with(
            Name='test_parameter',
            WithDecryption=True
        )
