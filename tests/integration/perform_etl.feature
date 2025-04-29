Feature: Fetch recently played tracks lambda integration tests

    Scenario: Lambda happy path
        Given a S3 bucket named test-etl-bucket
        And a lambda function named perform_etl with handler file perform_etl.py from source path src/lambdas/etl_process
        When we trigger the lambda function
        # Then the lambda function should complete with status code 200