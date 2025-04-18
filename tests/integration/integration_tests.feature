Feature: Lambda Integration Tests

    Scenario: Lambda happy path
        Given a S3 bucket named test-bucket
        And a lambda function named test_lambda from source path src/lambdas
        And a SSM parameter named spotify_refresh_token with value REDACTED
        And a SSM parameter named spotify_last_fetched_time with value 1735711200000
        When we trigger the lambda function
        Then the lambda function should complete with status code 200
        And the S3 bucket test-bucket should have an output file
        And the SSM parameter spotify_last_fetched_time should have been updated