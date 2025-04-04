"""Module containing code for Lambda function to fetch data from user's recently played tracks endpoint."""
from typing import Optional
from functools import wraps

import boto3
import botocore
import backoff
import botocore.exceptions


def backoff_on_client_error(func):
    """Reusable decorator to retry AWS API calls for server errors."""
    @wraps(func)
    @backoff.on_exception(
        backoff.expo,
        botocore.exceptions.ClientError,
        max_tries=5,
        giveup=lambda e: e.response['Error']['Code'] != 'InternalServerError'
    )
    def wrapper(self, *args, **kwargs):
        return func(self, *args, **kwargs)
    
    return wrapper


class ParameterStoreClient:
    """Class to interact with AWS SSM Parameter Store."""

    def __init__(self, region: str):
        self.client = boto3.client('ssm', region_name=region)


    @backoff_on_client_error
    def check_parameter_exists(
        self,
        parameter_name: str
    ) -> bool:
        """Check if a parameter exists in AWS Parameter Store."""
        try:
            self.client.get_parameter(Name=parameter_name)
            return True
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'ParameterNotFound':
                return False
            else:
                raise e


    @backoff_on_client_error 
    def create_or_update_parameter(
        self,
        parameter_name: str,
        parameter_value: str,
        parameter_type: str,
        overwrite: bool = True,
        parameter_description: str = None,
    ):
        """Creates or updates a parameter with parameter_name in AWS Parameter Store."""
        self.client.put_parameter(
            Name=parameter_name,
            Description=parameter_description,
            Value=parameter_value,
            Type=parameter_type,
            Overwrite=overwrite,
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


    @backoff_on_client_error
    def get_parameter(self, parameter_name: str) -> Optional[str]:
        """Retrieves a parameter value from AWS Parameter Store."""
        response = self.client.get_parameter(
            Name=parameter_name,
            WithDecryption=True
        )
        return response.get('Parameter', {}).get('Value', None)
