"""
Comprehensive tests for Cloud SQL proxy and database infrastructure.

These tests verify:
- Cloud SQL connection string parsing
- Database connectivity through Cloud SQL proxy
- Database operations and query execution
- Connection pooling and error handling
- Migration and schema operations
"""

import os
import socket
import time
from unittest.mock import Mock, patch, MagicMock
from urllib.parse import urlparse, parse_qs

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import override_settings as django_override_settings


class TestCloudSQLInfrastructure(TestCase):
    """Test Cloud SQL infrastructure components."""

    def setUp(self):
        """Set up test environment."""
        self.test_table_name = 'test_infrastructure_table'
        
    def tearDown(self):
        """Clean up test data."""
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {self.test_table_name}")
        except Exception:
            pass

    def test_cloud_sql_connection_string_parsing(self):
        """Test parsing of Cloud SQL connection string."""
        database_url = os.environ.get('DATABASE_URL')
        
        if not database_url:
            self.skipTest("DATABASE_URL not set - skipping connection string test")
        
        # Test Cloud SQL connection string format
        if "/cloudsql/" in database_url:
            try:
                parsed_url = urlparse(database_url)
                query_params = parse_qs(parsed_url.query)
                
                # Extract components
                database_name = parsed_url.path.lstrip('/')
                cloud_sql_host = query_params.get('host', [''])[0]
                
                # Extract credentials
                if '@' in parsed_url.netloc:
                    user_pass, _ = parsed_url.netloc.split('@', 1)
                    if ':' in user_pass:
                        username, password = user_pass.split(':', 1)
                    else:
                        username = user_pass
                        password = ""
                else:
                    username = parsed_url.netloc
                    password = ""
                
                # Validate components
                self.assertIsNotNone(database_name)
                self.assertIsNotNone(cloud_sql_host)
                self.assertIsNotNone(username)
                
                # Validate Cloud SQL connection name format
                self.assertTrue(cloud_sql_host.startswith('/cloudsql/'))
                
            except Exception as e:
                self.fail(f"Cloud SQL connection string parsing failed: {e}")
        else:
            self.skipTest("Not a Cloud SQL connection string")

    def test_database_connection_establishment(self):
        """Test that database connection can be established."""
        try:
            # Test connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                self.assertEqual(result[0], 1)
                
        except Exception as e:
            self.fail(f"Database connection establishment failed: {e}")

    def test_database_basic_operations(self):
        """Test basic database operations."""
        try:
            with connection.cursor() as cursor:
                # Test CREATE TABLE
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.test_table_name} (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Test INSERT
                cursor.execute(f"""
                    INSERT INTO {self.test_table_name} (name) 
                    VALUES ('test_record')
                """)
                
                # Test SELECT
                cursor.execute(f"SELECT * FROM {self.test_table_name} WHERE name = 'test_record'")
                result = cursor.fetchone()
                
                self.assertIsNotNone(result)
                self.assertEqual(result[1], 'test_record')
                
                # Test UPDATE
                cursor.execute(f"""
                    UPDATE {self.test_table_name} 
                    SET name = 'updated_record' 
                    WHERE name = 'test_record'
                """)
                
                # Verify update
                cursor.execute(f"SELECT * FROM {self.test_table_name} WHERE name = 'updated_record'")
                result = cursor.fetchone()
                
                self.assertIsNotNone(result)
                self.assertEqual(result[1], 'updated_record')
                
                # Test DELETE
                cursor.execute(f"DELETE FROM {self.test_table_name} WHERE name = 'updated_record'")
                
                # Verify deletion
                cursor.execute(f"SELECT COUNT(*) FROM {self.test_table_name}")
                count = cursor.fetchone()[0]
                self.assertEqual(count, 0)
                
        except Exception as e:
            self.fail(f"Database basic operations test failed: {e}")

    def test_database_transaction_handling(self):
        """Test database transaction handling."""
        try:
            with connection.cursor() as cursor:
                # Start transaction
                cursor.execute("BEGIN")
                
                try:
                    # Insert test data
                    cursor.execute(f"""
                        INSERT INTO {self.test_table_name} (name) 
                        VALUES ('transaction_test')
                    """)
                    
                    # Verify data exists within transaction
                    cursor.execute(f"SELECT COUNT(*) FROM {self.test_table_name}")
                    count = cursor.fetchone()[0]
                    self.assertEqual(count, 1)
                    
                    # Rollback transaction
                    cursor.execute("ROLLBACK")
                    
                    # Verify data is gone after rollback
                    cursor.execute(f"SELECT COUNT(*) FROM {self.test_table_name}")
                    count = cursor.fetchone()[0]
                    self.assertEqual(count, 0)
                    
                except Exception:
                    # Ensure rollback on error
                    cursor.execute("ROLLBACK")
                    raise
                    
        except Exception as e:
            self.fail(f"Database transaction handling test failed: {e}")

    def test_database_connection_pooling(self):
        """Test database connection pooling."""
        try:
            # Test multiple connections
            connections_to_test = []
            
            for i in range(5):
                conn = connections['default']
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    self.assertEqual(result[0], 1)
                    connections_to_test.append(conn)
            
            # All connections should work
            self.assertEqual(len(connections_to_test), 5)
            
        except Exception as e:
            self.fail(f"Database connection pooling test failed: {e}")

    def test_database_error_handling(self):
        """Test database error handling."""
        try:
            with connection.cursor() as cursor:
                # Test invalid SQL
                with self.assertRaises(Exception):
                    cursor.execute("INVALID SQL STATEMENT")
                
                # Test table not found
                with self.assertRaises(Exception):
                    cursor.execute("SELECT * FROM non_existent_table")
                
                # Test constraint violation
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.test_table_name} (
                        id SERIAL PRIMARY KEY,
                        unique_field VARCHAR(100) UNIQUE
                    )
                """)
                
                # Insert first record
                cursor.execute(f"""
                    INSERT INTO {self.test_table_name} (unique_field) 
                    VALUES ('unique_value')
                """)
                
                # Try to insert duplicate (should fail)
                with self.assertRaises(Exception):
                    cursor.execute(f"""
                        INSERT INTO {self.test_table_name} (unique_field) 
                        VALUES ('unique_value')
                    """)
                
        except Exception as e:
            self.fail(f"Database error handling test failed: {e}")

    def test_database_performance_basic(self):
        """Test basic database performance."""
        try:
            with connection.cursor() as cursor:
                # Create test table
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.test_table_name} (
                        id SERIAL PRIMARY KEY,
                        data TEXT
                    )
                """)
                
                # Test bulk insert performance
                start_time = time.time()
                
                for i in range(100):
                    cursor.execute(f"""
                        INSERT INTO {self.test_table_name} (data) 
                        VALUES ('test_data_{i}')
                    """)
                
                insert_time = time.time() - start_time
                
                # Test bulk select performance
                start_time = time.time()
                
                cursor.execute(f"SELECT COUNT(*) FROM {self.test_table_name}")
                count = cursor.fetchone()[0]
                
                select_time = time.time() - start_time
                
                # Verify results
                self.assertEqual(count, 100)
                
                # Performance should be reasonable (adjust thresholds as needed)
                self.assertLess(insert_time, 5.0, "Bulk insert took too long")
                self.assertLess(select_time, 1.0, "Bulk select took too long")
                
        except Exception as e:
            self.fail(f"Database performance test failed: {e}")

    def test_database_environment_variables(self):
        """Test that required database environment variables are set."""
        required_vars = [
            'DATABASE_URL',
        ]
        
        # Check if we're using individual database settings
        individual_vars = [
            'DJANGO_DATABASE_HOST',
            'DJANGO_DATABASE_NAME',
            'DJANGO_DATABASE_USER',
            'DJANGO_DATABASE_PASSWORD',
        ]
        
        # Either DATABASE_URL or individual settings should be present
        has_database_url = bool(os.environ.get('DATABASE_URL'))
        has_individual_settings = all(os.environ.get(var) for var in individual_vars)
        
        if not (has_database_url or has_individual_settings):
            self.skipTest("No database configuration found")
        
        if has_database_url:
            database_url = os.environ.get('DATABASE_URL')
            self.assertIsNotNone(database_url)
            self.assertGreater(len(database_url), 0)
            
            # Validate URL format
            self.assertTrue(database_url.startswith('postgresql://'))
        
        if has_individual_settings:
            for var in individual_vars:
                value = os.environ.get(var)
                self.assertIsNotNone(value, f"{var} should not be None")
                self.assertGreater(len(value), 0, f"{var} should not be empty")

    def test_database_settings_configuration(self):
        """Test Django database settings configuration."""
        databases = settings.DATABASES
        
        # Check default database configuration
        self.assertIn('default', databases)
        
        default_db = databases['default']
        
        # Check required fields
        required_fields = ['ENGINE', 'NAME', 'USER', 'PASSWORD', 'HOST']
        for field in required_fields:
            self.assertIn(field, default_db)
        
        # Check engine
        self.assertEqual(default_db['ENGINE'], 'django.db.backends.postgresql')
        
        # Check SSL configuration for Cloud SQL
        if 'OPTIONS' in default_db:
            options = default_db['OPTIONS']
            if 'sslmode' in options:
                self.assertEqual(options['sslmode'], 'require')

    def test_database_migration_capability(self):
        """Test that database migrations can be run."""
        try:
            # Test migration status check
            with connection.cursor() as cursor:
                # Check if django_migrations table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'django_migrations'
                    )
                """)
                migrations_table_exists = cursor.fetchone()[0]
                
                self.assertTrue(migrations_table_exists, "django_migrations table should exist")
                
                # Check migration records
                cursor.execute("SELECT COUNT(*) FROM django_migrations")
                migration_count = cursor.fetchone()[0]
                
                self.assertGreater(migration_count, 0, "Should have migration records")
                
        except Exception as e:
            self.fail(f"Database migration capability test failed: {e}")

    def test_cloud_sql_proxy_connectivity(self):
        """Test Cloud SQL proxy connectivity."""
        database_url = os.environ.get('DATABASE_URL')
        
        if not database_url or "/cloudsql/" not in database_url:
            self.skipTest("Not using Cloud SQL proxy")
        
        try:
            # Parse connection string to get host
            parsed_url = urlparse(database_url)
            query_params = parse_qs(parsed_url.query)
            cloud_sql_host = query_params.get('host', [''])[0]
            
            if cloud_sql_host.startswith('/cloudsql/'):
                # Extract connection name
                connection_name = cloud_sql_host.replace('/cloudsql/', '')
                
                # Test socket connectivity (if using Unix socket)
                if connection_name:
                    socket_path = f"/cloudsql/{connection_name}"
                    if os.path.exists(socket_path):
                        # Test socket is accessible
                        self.assertTrue(os.access(socket_path, os.R_OK))
                        self.assertTrue(os.access(socket_path, os.W_OK))
                    else:
                        # Test TCP connectivity (if using TCP)
                        # This is a basic connectivity test
                        try:
                            with connection.cursor() as cursor:
                                cursor.execute("SELECT 1")
                                result = cursor.fetchone()
                                self.assertEqual(result[0], 1)
                        except Exception as e:
                            self.fail(f"Cloud SQL proxy connectivity test failed: {e}")
            
        except Exception as e:
            self.fail(f"Cloud SQL proxy connectivity test failed: {e}")

    def test_database_backup_restore_capability(self):
        """Test database backup and restore capabilities."""
        try:
            with connection.cursor() as cursor:
                # Create test data
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.test_table_name} (
                        id SERIAL PRIMARY KEY,
                        backup_data TEXT
                    )
                """)
                
                cursor.execute(f"""
                    INSERT INTO {self.test_table_name} (backup_data) 
                    VALUES ('backup_test_data')
                """)
                
                # Test backup capability (pg_dump equivalent)
                cursor.execute(f"SELECT * FROM {self.test_table_name}")
                backup_data = cursor.fetchall()
                
                self.assertIsNotNone(backup_data)
                self.assertEqual(len(backup_data), 1)
                self.assertEqual(backup_data[0][1], 'backup_test_data')
                
                # Test restore capability (simulate)
                cursor.execute(f"DELETE FROM {self.test_table_name}")
                
                # Verify deletion
                cursor.execute(f"SELECT COUNT(*) FROM {self.test_table_name}")
                count = cursor.fetchone()[0]
                self.assertEqual(count, 0)
                
                # Restore data
                cursor.execute(f"""
                    INSERT INTO {self.test_table_name} (backup_data) 
                    VALUES ('backup_test_data')
                """)
                
                # Verify restoration
                cursor.execute(f"SELECT COUNT(*) FROM {self.test_table_name}")
                count = cursor.fetchone()[0]
                self.assertEqual(count, 1)
                
        except Exception as e:
            self.fail(f"Database backup/restore capability test failed: {e}")


class TestCloudSQLIntegration(TransactionTestCase):
    """Integration tests for Cloud SQL with Django ORM."""

    def setUp(self):
        """Set up test environment."""
        self.test_data = {
            'name': 'Integration Test',
            'description': 'Test data for Cloud SQL integration',
            'created_at': '2024-01-01 00:00:00'
        }

    def test_django_orm_basic_operations(self):
        """Test Django ORM basic operations."""
        from django.contrib.auth.models import User
        
        try:
            # Test CREATE
            user = User.objects.create_user(
                username='testuser',
                email='test@example.com',
                password='testpass123'
            )
            
            self.assertIsNotNone(user.id)
            self.assertEqual(user.username, 'testuser')
            
            # Test READ
            retrieved_user = User.objects.get(username='testuser')
            self.assertEqual(retrieved_user.id, user.id)
            
            # Test UPDATE
            user.email = 'updated@example.com'
            user.save()
            
            updated_user = User.objects.get(username='testuser')
            self.assertEqual(updated_user.email, 'updated@example.com')
            
            # Test DELETE
            user.delete()
            
            with self.assertRaises(User.DoesNotExist):
                User.objects.get(username='testuser')
                
        except Exception as e:
            self.fail(f"Django ORM basic operations test failed: {e}")

    def test_django_orm_bulk_operations(self):
        """Test Django ORM bulk operations."""
        from django.contrib.auth.models import User
        
        try:
            # Test bulk create
            users_data = [
                {'username': f'bulkuser{i}', 'email': f'bulk{i}@example.com'}
                for i in range(10)
            ]
            
            users = User.objects.bulk_create([
                User(**data) for data in users_data
            ])
            
            self.assertEqual(len(users), 10)
            
            # Test bulk update
            User.objects.filter(username__startswith='bulkuser').update(
                email='bulk_updated@example.com'
            )
            
            updated_count = User.objects.filter(
                email='bulk_updated@example.com'
            ).count()
            
            self.assertEqual(updated_count, 10)
            
            # Test bulk delete
            deleted_count, _ = User.objects.filter(
                username__startswith='bulkuser'
            ).delete()
            
            self.assertEqual(deleted_count, 10)
            
        except Exception as e:
            self.fail(f"Django ORM bulk operations test failed: {e}")

    def test_django_orm_transactions(self):
        """Test Django ORM transaction handling."""
        from django.contrib.auth.models import User
        from django.db import transaction
        
        try:
            # Test transaction rollback
            with self.assertRaises(Exception):
                with transaction.atomic():
                    User.objects.create_user(
                        username='transaction_user',
                        email='transaction@example.com',
                        password='testpass123'
                    )
                    
                    # Force an error to test rollback
                    raise Exception("Test rollback")
            
            # Verify user was not created
            with self.assertRaises(User.DoesNotExist):
                User.objects.get(username='transaction_user')
            
            # Test successful transaction
            with transaction.atomic():
                user = User.objects.create_user(
                    username='successful_user',
                    email='successful@example.com',
                    password='testpass123'
                )
                
                self.assertIsNotNone(user.id)
            
            # Verify user was created
            created_user = User.objects.get(username='successful_user')
            self.assertEqual(created_user.id, user.id)
            
            # Clean up
            created_user.delete()
            
        except Exception as e:
            self.fail(f"Django ORM transactions test failed: {e}")

    def test_django_orm_queries_performance(self):
        """Test Django ORM query performance."""
        from django.contrib.auth.models import User
        
        try:
            # Create test data
            users = []
            for i in range(100):
                user = User.objects.create_user(
                    username=f'perfuser{i}',
                    email=f'perf{i}@example.com',
                    password='testpass123'
                )
                users.append(user)
            
            # Test query performance
            start_time = time.time()
            
            # Test select_related
            users_with_profiles = User.objects.select_related().filter(
                username__startswith='perfuser'
            )[:10]
            
            query_time = time.time() - start_time
            
            # Performance should be reasonable
            self.assertLess(query_time, 2.0, "Query took too long")
            self.assertEqual(len(list(users_with_profiles)), 10)
            
            # Clean up
            User.objects.filter(username__startswith='perfuser').delete()
            
        except Exception as e:
            self.fail(f"Django ORM queries performance test failed: {e}")

    def test_database_migrations_integration(self):
        """Test database migrations integration."""
        try:
            # Test that migrations can be applied
            # Note: This is a basic test - actual migration testing
            # should be done in a separate test environment
            
            with connection.cursor() as cursor:
                # Check migration status
                cursor.execute("""
                    SELECT app, name FROM django_migrations 
                    ORDER BY applied DESC LIMIT 5
                """)
                
                recent_migrations = cursor.fetchall()
                
                self.assertIsNotNone(recent_migrations)
                self.assertGreater(len(recent_migrations), 0)
                
        except Exception as e:
            self.fail(f"Database migrations integration test failed: {e}")

    def test_database_connection_resilience(self):
        """Test database connection resilience."""
        try:
            # Test connection recovery
            original_connection = connection
            
            # Simulate connection issues by closing
            original_connection.close()
            
            # Test that new connection is established
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                self.assertEqual(result[0], 1)
            
            # Test multiple connection attempts
            for i in range(5):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT %s", [i])
                    result = cursor.fetchone()
                    self.assertEqual(result[0], i)
            
        except Exception as e:
            self.fail(f"Database connection resilience test failed: {e}")
