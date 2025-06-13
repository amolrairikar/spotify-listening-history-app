"""Module for testing utility functions in the ETL Lambda function."""
import unittest

from src.lambdas.etl_process.perform_etl import (
    convert_utc_to_cst,
    milliseconds_to_mmss,
    get_bucket_and_object,
    perform_etl,
    partition_spotify_data
)


class TestConvertUtcToCst(unittest.TestCase):
    """Class for testing the convert_utc_to_cst method."""

    def test_valid_conversion(self):
        """Test conversion of a valid UTC datetime string to CST."""
        utc_string = "2023-03-15T12:00:00.000Z"
        expected_cst = "2023-03-15T07:00:00"  # CST is UTC-5
        self.assertEqual(convert_utc_to_cst(utc_string=utc_string), expected_cst)


    def test_daylight_saving_time_start(self):
        """Test conversion during the start of daylight saving time."""
        utc_string = "2023-03-12T08:00:00.000Z"
        expected_cst = "2023-03-12T03:00:00"  # CST switches to CDT (UTC-5)
        self.assertEqual(convert_utc_to_cst(utc_string=utc_string), expected_cst)


    def test_daylight_saving_time_end(self):
        """Test conversion during the end of daylight saving time."""
        utc_string = "2023-11-05T07:00:00.000Z"
        expected_cst = "2023-11-05T01:00:00"  # CDT switches to CST (UTC-6)
        self.assertEqual(convert_utc_to_cst(utc_string=utc_string), expected_cst)


    def test_invalid_format(self):
        """Test handling of an invalid UTC datetime string format."""
        utc_string = "2023-03-15 12:00:00"
        with self.assertRaises(ValueError):
            convert_utc_to_cst(utc_string=utc_string)


    def test_empty_string(self):
        """Test handling of an empty string."""
        utc_string = ""
        with self.assertRaises(ValueError):
            convert_utc_to_cst(utc_string=utc_string)


    def test_none_input(self):
        """Test handling of a None input."""
        utc_string = None
        with self.assertRaises(TypeError):
            convert_utc_to_cst(utc_string=utc_string)


class TestMillisecondsToMmss(unittest.TestCase):
    """Tests for the milliseconds_to_mmss function."""

    def test_typical_track_length(self):
        """Test conversion of typical track length."""
        self.assertEqual(milliseconds_to_mmss(track_length=180000), '03:00')


    def test_edge_cases(self):
        """Test edge cases like small time amounts and rounding."""
        self.assertEqual(milliseconds_to_mmss(track_length=1), '00:00')
        self.assertEqual(milliseconds_to_mmss(track_length=59999), '00:59')


    def test_invalid_negative_value(self):
        """Test handling of negative values."""
        with self.assertRaises(ValueError):
            milliseconds_to_mmss(track_length=-1000)


class TestGetBucketAndObject(unittest.TestCase):
    """Class for testing the get_bucket_and_object method."""

    def test_valid_event(self):
        """Test with a valid event payload containing bucket and object."""
        event = {
            'Records': [
                {
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'test-object.json'}
                    }
                }
            ]
        }
        bucket, obj = get_bucket_and_object(event=event)
        self.assertEqual(bucket, 'test-bucket')
        self.assertEqual(obj, 'test-object.json')


    def test_missing_records_key(self):
        """Test with an event payload missing the 'Records' key."""
        event = {}
        with self.assertRaises(Exception) as context:
            get_bucket_and_object(event=event)
        self.assertEqual(str(context.exception), 'No data present in event payload')


    def test_empty_records_list(self):
        """Test with an event payload containing an empty 'Records' list."""
        event = {'Records': []}
        with self.assertRaises(Exception) as context:
            get_bucket_and_object(event=event)
        self.assertEqual(str(context.exception), 'No data present in event payload')


    def test_missing_s3_key(self):
        """Test with an event payload missing the 's3' key."""
        event = {
            'Records': [
                {}
            ]
        }
        bucket, obj = get_bucket_and_object(event=event)
        self.assertEqual(bucket, '')
        self.assertEqual(obj, '')


    def test_missing_bucket_and_object_keys(self):
        """Test with an event payload missing 'bucket' and 'object' keys."""
        event = {
            'Records': [
                {
                    's3': {}
                }
            ]
        }
        bucket, obj = get_bucket_and_object(event=event)
        self.assertEqual(bucket, '')
        self.assertEqual(obj, '')


    def test_empty_bucket_and_object_values(self):
        """Test with an event payload containing empty bucket and object values."""
        event = {
            'Records': [
                {
                    's3': {
                        'bucket': {'name': ''},
                        'object': {'key': ''}
                    }
                }
            ]
        }
        bucket, obj = get_bucket_and_object(event=event)
        self.assertEqual(bucket, '')
        self.assertEqual(obj, '')


class TestPerformEtl(unittest.TestCase):
    """Class for testing the perform_etl method."""

    def test_valid_json_data(self):
        """Test with valid JSON data."""
        json_data = [
            {
                'track': {
                    'uri': 'spotify:track:123',
                    'album': {'name': 'Test Album', 'release_date': '2023-03-01'},
                    'artists': [{'name': 'Test Artist'}],
                    'duration_ms': 210000,
                    'name': 'Test Track',
                    'external_urls': {'spotify': 'https://open.spotify.com/track/123'},
                    'popularity': 85,
                },
                'played_at': '2023-03-15T12:00:00.000Z',
            }
        ]

        expected_output = {
            'spotify:track:123': {
                'album': 'Test Album',
                'release_date': '2023-03-01',
                'artists': ['Test Artist'],
                'track_length': '03:30',
                'track_name': 'Test Track',
                'track_url': 'https://open.spotify.com/track/123',
                'track_popularity': 85,
                'played_at': '2023-03-15T07:00:00',
            }
        }

        result = perform_etl(json_data=json_data)
        self.assertEqual(result, expected_output)


    def test_empty_json_data(self):
        """Test with empty JSON data."""
        json_data = []
        expected_output = {}
        result = perform_etl(json_data=json_data)
        self.assertEqual(result, expected_output)


    def test_missing_fields(self):
        """Test with JSON data missing some fields (duration ms)."""
        json_data = [
            {
                'track': {
                    'uri': 'spotify:track:123',
                    'album': {'name': 'Test Album', 'release_date': '2023-03-01'},
                    'artists': [{'name': 'Test Artist'}],
                    'name': 'Test Track',
                    'external_urls': {'spotify': 'https://open.spotify.com/track/123'},
                    'popularity': 85,
                },
                'played_at': '2023-03-15T12:00:00.000Z',
            }
        ]

        with self.assertRaises(KeyError):
            perform_etl(json_data=json_data)


class TestPartitionSpotifyData(unittest.TestCase):
    """Class for testing the partition_spotify_data method."""

    def test_valid_data(self):
        """Test partitioning with valid track data."""
        track_data = {
            'spotify:track:123': {
                'played_at': '2023-03-15T12:00:00',
                'track_name': 'Test Track 1',
            },
            'spotify:track:456': {
                'played_at': '2023-03-15T15:00:00',
                'track_name': 'Test Track 2',
            },
            'spotify:track:789': {
                'played_at': '2023-04-01T10:00:00',
                'track_name': 'Test Track 3',
            },
        }

        expected_output = {
            ('2023', '03'): [
                {'track_id': 'spotify:track:123', 'played_at': '2023-03-15T12:00:00', 'track_name': 'Test Track 1'},
                {'track_id': 'spotify:track:456', 'played_at': '2023-03-15T15:00:00', 'track_name': 'Test Track 2'},
            ],
            ('2023', '04'): [
                {'track_id': 'spotify:track:789', 'played_at': '2023-04-01T10:00:00', 'track_name': 'Test Track 3'},
            ],
        }

        result = partition_spotify_data(track_data)
        self.assertEqual(result, expected_output)


    def test_empty_data(self):
        """Test partitioning with empty track data."""
        track_data = {}
        expected_output = {}
        result = partition_spotify_data(track_data)
        self.assertEqual(result, expected_output)
