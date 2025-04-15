import os
from typing import Any
import pathlib
import shutil
import subprocess
import zipfile
import json
import time

from behave import given, when, then
from dotenv import load_dotenv
import boto3
import botocore

from src.lambdas.get_recently_played import lambda_handler

# Load environment variables
load_dotenv()


def create_localstack_client(service_name: str) -> boto3.client:
    """Returns a localstack client for the given service_name at endpoint http://localhost:4566."""
    return boto3.client(
        service_name,
        region_name='us-east-1',
        aws_access_key_id='test-access-key',
        aws_secret_access_key='test-secret-key',
        endpoint_url='http://localhost:4566'
    )


class MockLambdaContext:
    """Mock class for AWS Lambda context."""

    def __init__(self):
        """Initializes mock Lambda context with constant attributes for tests."""
        self.aws_request_id = 'test-request-id'
        self.function_name = 'test-function-name'
        self.function_version = 'test-function-version'


def wait_for_lambda_ready(function_name: str, lambda_client: boto3.client, timeout_seconds=1000) -> None:
    """Polls a Lambda function until it is successfully provisioned."""
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            response = lambda_client.get_function(FunctionName=function_name)
            status = response['Configuration'].get('State', 'Unknown')
            if status == 'Active':
                print(f'Lambda "{function_name}" is ready!')
                return
            else:
                print(f'Waiting for Lambda to be Active (current: {status})...')
        except botocore.exceptions.ClientError as e:
            print(f"⚠️ Still waiting... {str(e)}")
        time.sleep(10)

    raise TimeoutError(f'Lambda "{function_name}" did not become ready in {timeout_seconds} seconds.')


@given('a S3 bucket named {bucket_name}')
def create_s3_bucket(context: Any, bucket_name: str):
    """Create an S3 bucket on LocalStack."""
    s3_client = create_localstack_client(service_name='s3')
    s3_client.create_bucket(Bucket=bucket_name)
    context.s3_client = s3_client

    # Ensure the bucket was created successfully
    response = s3_client.head_bucket(Bucket=bucket_name)
    assert response is not None


@given('a lambda function named {function_name} from source path {source_path}')
def create_lambda_function(context: Any, function_name: str, source_path: str):
    """Create a Lambda function on LocalStack."""
    # Set up paths for zipping
    project_dir = pathlib.Path(source_path).resolve()
    requirements_path = project_dir / 'requirements.txt'
    handler_path = project_dir / 'get_recently_played.py'
    build_dir = project_dir / 'build'
    zip_path = project_dir / 'lambda_function.zip'

    # Clean build directory
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    # Install dependencies
    site_packages_dir = build_dir / 'python'
    subprocess.check_call(
        [
            'pip',
            'install',
            '-r', str(requirements_path),
            '-t', str(site_packages_dir)
        ]
    )

    # Copy lambda_function.py into build dir
    shutil.copy(handler_path, build_dir)

    # Create zip
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(site_packages_dir):
            for file in files:
                full_path = pathlib.Path(root) / file
                rel_path = full_path.relative_to(build_dir)
                zipf.write(full_path, rel_path)
        zipf.write(build_dir / 'get_recently_played.py', 'get_recently_played.py')

    # Create Lambda function in LocalStack
    lambda_client = create_localstack_client(service_name='lambda')
    context.lambda_client = lambda_client
    context.lambda_function_name = function_name
    with open(zip_path, 'rb') as f:
        zipped_code = f.read()

    response = lambda_client.create_function(
        FunctionName=function_name,
        Runtime='python3.12',
        Role='arn:aws:iam::000000000000:role/lambda-role',  # Dummy role for LocalStack
        Handler='get_recently_played.lambda_handler',
        Code={'ZipFile': zipped_code},
        Timeout=10,
        MemorySize=128
    )
    wait_for_lambda_ready(function_name=function_name, lambda_client=lambda_client)

    assert response['FunctionArn'] is not None


@given('a {string_type} SSM parameter named {parameter_name} with value {parameter_value}')
def create_ssm_parameter(context: Any, string_type: str, parameter_name: str, parameter_value: str):
    """Create an SSM parameter on LocalStack."""
    ssm_client = create_localstack_client(service_name='ssm')
    if parameter_value == 'REDACTED':
        parameter_value = os.environ[parameter_name.upper()]
    ssm_client.put_parameter(
        Name=parameter_name,
        Value=parameter_value,
        Type=string_type,
        Overwrite=True
    )
    context.ssm_client = ssm_client
    setattr(context, parameter_name, parameter_value)

    # Ensure the parameter was created successfully
    response = ssm_client.get_parameter(Name=parameter_name)
    assert parameter_value in response['Parameter']['Value']


@when('we trigger the Lambda function')
def trigger_lambda(context: Any):
    """Trigger the Lambda function using a mock event and context."""
    response = context.lambda_client.invoke(
        FunctionName=context.lambda_function_name,
        InvocationType='RequestResponse',
        Payload=json.dumps({'key': 'value'}),
        ClientContext=json.dumps(MockLambdaContext().__dict__)
    )
    context.lambda_response = response
    assert response is not None


@then('the lambda function should return a response code of {response_code}')
def check_lambda_response_code(context: Any, response_code: str):
    """Check the Lambda function's response code."""
    assert context.lambda_response['StatusCode'] == int(response_code)
    