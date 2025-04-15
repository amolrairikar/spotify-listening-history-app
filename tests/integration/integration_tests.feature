Feature: Lambda Integration Tests

    Scenario: Lambda happy path
        Given a S3 bucket named test-bucket
        And a lambda function named test_lambda from source path src/lambdas
        And a SecureString SSM parameter named refresh_token with value REDACTED
        And a String SSM parameter named last_refresh_timestamp with value 1735711200  # Jan 1, 2025 00:00:00 CST
        When we trigger the lambda function
        Then the lambda function should return a response code of 200