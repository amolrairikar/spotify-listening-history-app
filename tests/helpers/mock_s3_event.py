MOCK_S3_EVENT = {
    "Records": [
        {
            "eventVersion": "2.1",
            "eventSource": "aws:s3",
            "awsRegion": "us-east-2",
            "eventTime": "2025-04-25T19:06:33.703Z",
            "eventName": "ObjectCreated:Put",
            "userIdentity": {
                "principalId": "AWS:ABCDEFGHIJKLMN:lambda-name"
            },
            "requestParameters": {
                "sourceIPAddress": "0.000.000.000"
            },
            "responseElements": {
                "x-amz-request-id": "ABCDEFGHIJ",
                "x-amz-id-2": "thisisauniqueidentifier"
            },
            "s3": {
                "s3SchemaVersion": "1.0",
                "configurationId": "tf-s3-lambda-20250425180129198500000001",
                "bucket": {
                    "name": "bucket-name",
                    "ownerIdentity": {
                        "principalId": "ABCDEFG123"
                    },
                    "arn": "arn:aws:s3:::bucket-name"
                },
                "object": {
                    "key": "raw/recently_played_tracks_20250425140632.json",
                    "size": 4675,
                    "eTag": "abc123def456ghi789",
                    "versionId": "abc123def456ghi789",
                    "sequencer": "abc123def456ghi789"
                }
            }
        }
    ]
}