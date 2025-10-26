"""
Test configuration and utilities for infrastructure tests.

This module provides:
- Test fixtures and setup utilities
- Mock configurations for testing
- Test data generators
- Common test assertions
"""

import os
import tempfile
from unittest.mock import Mock, MagicMock, patch
from django.test import TestCase, TransactionTestCase
from django.conf import settings


class InfrastructureTestMixin:
    """Mixin class providing common infrastructure test utilities."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test class."""
        super().setUpClass()
        cls.test_files = []
        cls.test_tables = []
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test class."""
        super().tearDownClass()
        # Clean up test files
        for file_path in cls.test_files:
            try:
                from django.core.files.storage import default_storage
                default_storage.delete(file_path)
            except Exception:
                pass
        
        # Clean up test tables
        from django.db import connection
        with connection.cursor() as cursor:
            for table_name in cls.test_tables:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                except Exception:
                    pass
    
    def create_test_file(self, filename, content="Test content"):
        """Create a test file in storage."""
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        
        file_content = ContentFile(content.encode('utf-8'))
        saved_path = default_storage.save(filename, file_content)
        self.test_files.append(saved_path)
        return saved_path
    
    def create_test_table(self, table_name, schema):
        """Create a test table in database."""
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({schema})")
            self.test_tables.append(table_name)
    
    def assert_gcs_configured(self):
        """Assert that GCS is properly configured."""
        storages = getattr(settings, 'STORAGES', {})
        self.assertIn('default', storages)
        
        default_storage_config = storages['default']
        self.assertEqual(
            default_storage_config['BACKEND'],
            'storages.backends.gcloud.GoogleCloudStorage'
        )
        
        options = default_storage_config.get('OPTIONS', {})
        self.assertIn('bucket_name', options)
        self.assertIn('credentials', options)
    
    def assert_database_configured(self):
        """Assert that database is properly configured."""
        databases = settings.DATABASES
        self.assertIn('default', databases)
        
        default_db = databases['default']
        self.assertEqual(default_db['ENGINE'], 'django.db.backends.postgresql')
        
        required_fields = ['NAME', 'USER', 'PASSWORD', 'HOST']
        for field in required_fields:
            self.assertIn(field, default_db)
    
    def assert_environment_variables(self, required_vars=None):
        """Assert that required environment variables are set."""
        if required_vars is None:
            required_vars = [
                'GCS_STORAGE_SA_KEY_BASE64',
                'GCS_BUCKET_NAME',
                'DATABASE_URL',
            ]
        
        missing_vars = []
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
        
        if missing_vars:
            self.skipTest(f"Missing required environment variables: {', '.join(missing_vars)}")


class MockGCSStorage:
    """Mock GCS storage for testing."""
    
    def __init__(self):
        self.files = {}
    
    def save(self, name, content):
        """Mock save method."""
        self.files[name] = content.read() if hasattr(content, 'read') else content
        return name
    
    def exists(self, name):
        """Mock exists method."""
        return name in self.files
    
    def delete(self, name):
        """Mock delete method."""
        if name in self.files:
            del self.files[name]
    
    def open(self, name):
        """Mock open method."""
        if name in self.files:
            from django.core.files.base import ContentFile
            return ContentFile(self.files[name])
        raise FileNotFoundError(f"File {name} not found")
    
    def url(self, name):
        """Mock url method."""
        if name in self.files:
            return f"https://storage.googleapis.com/test-bucket/{name}"
        raise FileNotFoundError(f"File {name} not found")
    
    def size(self, name):
        """Mock size method."""
        if name in self.files:
            return len(self.files[name])
        raise FileNotFoundError(f"File {name} not found")


class MockCloudSQLConnection:
    """Mock Cloud SQL connection for testing."""
    
    def __init__(self):
        self.tables = {}
        self.data = {}
    
    def cursor(self):
        """Mock cursor method."""
        return MockCloudSQLCursor(self)
    
    def close(self):
        """Mock close method."""
        pass


class MockCloudSQLCursor:
    """Mock Cloud SQL cursor for testing."""
    
    def __init__(self, connection):
        self.connection = connection
        self.last_result = None
    
    def execute(self, query, params=None):
        """Mock execute method."""
        query_lower = query.lower().strip()
        
        if query_lower.startswith('select'):
            if 'django_migrations' in query_lower:
                self.last_result = [('test_app', '0001_initial')]
            elif 'count(*)' in query_lower:
                self.last_result = [(0,)]
            else:
                self.last_result = [(1,)]
        elif query_lower.startswith('create table'):
            # Extract table name (simplified)
            table_name = query_lower.split('table')[1].split('(')[0].strip()
            self.connection.tables[table_name] = True
        elif query_lower.startswith('insert'):
            # Mock successful insert
            self.last_result = None
        elif query_lower.startswith('update'):
            # Mock successful update
            self.last_result = None
        elif query_lower.startswith('delete'):
            # Mock successful delete
            self.last_result = None
        else:
            # Mock other queries
            self.last_result = None
    
    def fetchone(self):
        """Mock fetchone method."""
        return self.last_result[0] if self.last_result else None
    
    def fetchall(self):
        """Mock fetchall method."""
        return self.last_result or []
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass


def mock_gcs_storage():
    """Decorator to mock GCS storage for testing."""
    def decorator(test_func):
        def wrapper(self, *args, **kwargs):
            with patch('django.core.files.storage.default_storage', MockGCSStorage()):
                return test_func(self, *args, **kwargs)
        return wrapper
    return decorator


def mock_cloudsql_connection():
    """Decorator to mock Cloud SQL connection for testing."""
    def decorator(test_func):
        def wrapper(self, *args, **kwargs):
            with patch('django.db.connection', MockCloudSQLConnection()):
                return test_func(self, *args, **kwargs)
        return wrapper
    return decorator


def skip_if_no_gcs():
    """Decorator to skip test if GCS is not configured."""
    def decorator(test_func):
        def wrapper(self, *args, **kwargs):
            if not os.environ.get('GCS_STORAGE_SA_KEY_BASE64'):
                self.skipTest("GCS not configured - skipping test")
            return test_func(self, *args, **kwargs)
        return wrapper
    return decorator


def skip_if_no_cloudsql():
    """Decorator to skip test if Cloud SQL is not configured."""
    def decorator(test_func):
        def wrapper(self, *args, **kwargs):
            database_url = os.environ.get('DATABASE_URL')
            if not database_url or '/cloudsql/' not in database_url:
                self.skipTest("Cloud SQL not configured - skipping test")
            return test_func(self, *args, **kwargs)
        return wrapper
    return decorator


class TestDataGenerator:
    """Utility class for generating test data."""
    
    @staticmethod
    def generate_file_content(size_kb=1):
        """Generate test file content of specified size."""
        return "x" * (size_kb * 1024)
    
    @staticmethod
    def generate_test_files(count=5):
        """Generate multiple test files."""
        files = []
        for i in range(count):
            filename = f"test_file_{i}.txt"
            content = f"Test content for file {i}"
            files.append((filename, content))
        return files
    
    @staticmethod
    def generate_database_records(count=10):
        """Generate test database records."""
        records = []
        for i in range(count):
            record = {
                'id': i + 1,
                'name': f'Test Record {i}',
                'description': f'Description for record {i}',
                'created_at': '2024-01-01 00:00:00'
            }
            records.append(record)
        return records


class InfrastructureTestAssertions:
    """Custom assertions for infrastructure tests."""
    
    @staticmethod
    def assert_file_uploaded(file_path, expected_content=None):
        """Assert that a file was uploaded successfully."""
        from django.core.files.storage import default_storage
        
        assert default_storage.exists(file_path), f"File {file_path} does not exist"
        
        if expected_content:
            actual_content = default_storage.open(file_path).read().decode('utf-8')
            assert actual_content == expected_content, f"File content mismatch"
    
    @staticmethod
    def assert_database_record_exists(table_name, conditions):
        """Assert that a database record exists."""
        from django.db import connection
        
        with connection.cursor() as cursor:
            where_clause = " AND ".join([f"{k} = %s" for k in conditions.keys()])
            query = f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}"
            cursor.execute(query, list(conditions.values()))
            count = cursor.fetchone()[0]
            assert count > 0, f"Record not found in {table_name} with conditions {conditions}"
    
    @staticmethod
    def assert_service_healthy(service_name):
        """Assert that a service is healthy."""
        # This is a placeholder for service health checks
        # Implement actual health check logic based on your services
        assert True, f"Service {service_name} health check not implemented"
    
    @staticmethod
    def assert_performance_within_limits(operation_time, max_time):
        """Assert that operation completed within time limits."""
        assert operation_time <= max_time, f"Operation took {operation_time}s, exceeds limit of {max_time}s"
