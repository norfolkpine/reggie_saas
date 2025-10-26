"""
End-to-end integration tests for infrastructure components.

These tests verify:
- Complete file upload workflow (GCS + Database)
- Service communication and data consistency
- Error handling across multiple services
- Performance under load
- Environment variable validation
- Health check endpoints
"""

import os
import tempfile
import time
from unittest.mock import Mock, patch, MagicMock

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse


class TestInfrastructureIntegration(TransactionTestCase):
    """End-to-end integration tests for infrastructure components."""

    def setUp(self):
        """Set up test environment."""
        self.client = Client()
        self.test_file_content = "Integration test file content"
        self.test_file_name = "integration-test-file.txt"
        self.test_user_data = {
            'username': 'integration_test_user',
            'email': 'integration@example.com',
            'password': 'testpass123'
        }

    def tearDown(self):
        """Clean up test data."""
        try:
            default_storage.delete(self.test_file_name)
        except Exception:
            pass

    def test_complete_file_upload_workflow(self):
        """Test complete file upload workflow from upload to storage."""
        try:
            # Step 1: Upload file to GCS
            test_content = ContentFile(self.test_file_content.encode('utf-8'))
            saved_path = default_storage.save(self.test_file_name, test_content)
            
            self.assertIsNotNone(saved_path)
            self.assertTrue(default_storage.exists(saved_path))
            
            # Step 2: Store file metadata in database
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_file_metadata (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255),
                        file_path VARCHAR(500),
                        file_size BIGINT,
                        upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    INSERT INTO test_file_metadata (filename, file_path, file_size)
                    VALUES (%s, %s, %s)
                """, [self.test_file_name, saved_path, len(self.test_file_content)])
                
                # Step 3: Verify metadata was stored
                cursor.execute("""
                    SELECT filename, file_path, file_size 
                    FROM test_file_metadata 
                    WHERE filename = %s
                """, [self.test_file_name])
                
                result = cursor.fetchone()
                self.assertIsNotNone(result)
                self.assertEqual(result[0], self.test_file_name)
                self.assertEqual(result[1], saved_path)
                self.assertEqual(result[2], len(self.test_file_content))
                
                # Step 4: Verify file can be retrieved
                retrieved_content = default_storage.open(saved_path).read()
                self.assertEqual(retrieved_content.decode('utf-8'), self.test_file_content)
                
                # Step 5: Generate signed URL
                signed_url = default_storage.url(saved_path)
                self.assertIsNotNone(signed_url)
                self.assertTrue(signed_url.startswith('http'))
                
                # Clean up
                cursor.execute("DROP TABLE IF EXISTS test_file_metadata")
                
        except Exception as e:
            self.fail(f"Complete file upload workflow test failed: {e}")

    def test_service_communication_consistency(self):
        """Test that services communicate consistently."""
        try:
            # Test that database and storage are in sync
            test_files = [
                ('file1.txt', 'Content 1'),
                ('file2.txt', 'Content 2'),
                ('file3.txt', 'Content 3'),
            ]
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_service_sync (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255),
                        file_path VARCHAR(500),
                        content_hash VARCHAR(64)
                    )
                """)
                
                for filename, content in test_files:
                    # Upload to GCS
                    file_content = ContentFile(content.encode('utf-8'))
                    saved_path = default_storage.save(filename, file_content)
                    
                    # Store metadata in database
                    content_hash = hash(content)
                    cursor.execute("""
                        INSERT INTO test_service_sync (filename, file_path, content_hash)
                        VALUES (%s, %s, %s)
                    """, [filename, saved_path, str(content_hash)])
                
                # Verify consistency
                cursor.execute("SELECT filename, file_path, content_hash FROM test_service_sync")
                db_records = cursor.fetchall()
                
                self.assertEqual(len(db_records), len(test_files))
                
                for db_record in db_records:
                    filename, file_path, content_hash = db_record
                    
                    # Verify file exists in storage
                    self.assertTrue(default_storage.exists(file_path))
                    
                    # Verify content matches
                    stored_content = default_storage.open(file_path).read().decode('utf-8')
                    expected_content = next(content for name, content in test_files if name == filename)
                    self.assertEqual(stored_content, expected_content)
                    
                    # Verify hash matches
                    expected_hash = str(hash(expected_content))
                    self.assertEqual(content_hash, expected_hash)
                
                # Clean up
                cursor.execute("DROP TABLE IF EXISTS test_service_sync")
                for filename, _ in test_files:
                    default_storage.delete(filename)
                
        except Exception as e:
            self.fail(f"Service communication consistency test failed: {e}")

    def test_error_handling_across_services(self):
        """Test error handling across multiple services."""
        try:
            # Test GCS error handling
            with patch('django.core.files.storage.default_storage.save') as mock_save:
                mock_save.side_effect = Exception("GCS upload failed")
                
                with self.assertRaises(Exception):
                    test_content = ContentFile("test content".encode('utf-8'))
                    default_storage.save("error-test.txt", test_content)
            
            # Test database error handling
            with connection.cursor() as cursor:
                with self.assertRaises(Exception):
                    cursor.execute("INVALID SQL STATEMENT")
            
            # Test combined error handling
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_error_handling (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255),
                        status VARCHAR(50)
                    )
                """)
                
                # Simulate partial failure scenario
                try:
                    # This should succeed
                    cursor.execute("""
                        INSERT INTO test_error_handling (filename, status)
                        VALUES ('test.txt', 'uploading')
                    """)
                    
                    # This should fail
                    with patch('django.core.files.storage.default_storage.save') as mock_save:
                        mock_save.side_effect = Exception("Storage error")
                        
                        with self.assertRaises(Exception):
                            test_content = ContentFile("test content".encode('utf-8'))
                            default_storage.save("test.txt", test_content)
                    
                    # Verify rollback occurred
                    cursor.execute("SELECT COUNT(*) FROM test_error_handling")
                    count = cursor.fetchone()[0]
                    self.assertEqual(count, 0)  # Should be 0 if transaction was rolled back
                    
                except Exception:
                    # Ensure cleanup
                    cursor.execute("DROP TABLE IF EXISTS test_error_handling")
                    raise
                
                # Clean up
                cursor.execute("DROP TABLE IF EXISTS test_error_handling")
                
        except Exception as e:
            self.fail(f"Error handling across services test failed: {e}")

    def test_performance_under_load(self):
        """Test system performance under load."""
        try:
            # Test concurrent file operations
            import threading
            import queue
            
            results = queue.Queue()
            errors = queue.Queue()
            
            def upload_file(file_num):
                """Upload a file in a separate thread."""
                try:
                    start_time = time.time()
                    
                    # Upload file
                    content = f"Load test file {file_num}"
                    file_content = ContentFile(content.encode('utf-8'))
                    filename = f"load_test_{file_num}.txt"
                    saved_path = default_storage.save(filename, file_content)
                    
                    # Store metadata
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS test_load_performance (
                                id SERIAL PRIMARY KEY,
                                filename VARCHAR(255),
                                file_path VARCHAR(500),
                                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        """)
                        
                        cursor.execute("""
                            INSERT INTO test_load_performance (filename, file_path)
                            VALUES (%s, %s)
                        """, [filename, saved_path])
                    
                    end_time = time.time()
                    results.put((file_num, end_time - start_time, saved_path))
                    
                except Exception as e:
                    errors.put((file_num, str(e)))
            
            # Start multiple upload threads
            threads = []
            num_threads = 10
            
            for i in range(num_threads):
                thread = threading.Thread(target=upload_file, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            # Check results
            if not errors.empty():
                error_messages = []
                while not errors.empty():
                    file_num, error_msg = errors.get()
                    error_messages.append(f"File {file_num}: {error_msg}")
                self.fail(f"Load test errors: {'; '.join(error_messages)}")
            
            # Analyze performance
            upload_times = []
            while not results.empty():
                file_num, upload_time, saved_path = results.get()
                upload_times.append(upload_time)
                
                # Clean up
                default_storage.delete(saved_path)
            
            # Performance analysis
            avg_upload_time = sum(upload_times) / len(upload_times)
            max_upload_time = max(upload_times)
            
            # Performance thresholds (adjust as needed)
            self.assertLess(avg_upload_time, 2.0, f"Average upload time too high: {avg_upload_time}")
            self.assertLess(max_upload_time, 5.0, f"Max upload time too high: {max_upload_time}")
            
            # Clean up database
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS test_load_performance")
            
        except Exception as e:
            self.fail(f"Performance under load test failed: {e}")

    def test_environment_variables_validation(self):
        """Test that all required environment variables are properly set."""
        required_vars = {
            'GCS_STORAGE_SA_KEY_BASE64': 'Service account key for GCS',
            'GCS_BUCKET_NAME': 'GCS bucket name for media files',
            'DATABASE_URL': 'Database connection string',
        }
        
        optional_vars = {
            'GCS_STATIC_BUCKET_NAME': 'GCS bucket name for static files',
            'DJANGO_DATABASE_HOST': 'Database host',
            'DJANGO_DATABASE_NAME': 'Database name',
            'DJANGO_DATABASE_USER': 'Database user',
            'DJANGO_DATABASE_PASSWORD': 'Database password',
        }
        
        missing_required = []
        missing_optional = []
        
        # Check required variables
        for var, description in required_vars.items():
            value = os.environ.get(var)
            if not value:
                missing_required.append(f"{var} ({description})")
            else:
                # Validate format
                if var == 'GCS_STORAGE_SA_KEY_BASE64':
                    try:
                        import base64
                        import json
                        decoded = base64.b64decode(value).decode('utf-8')
                        json.loads(decoded)
                    except Exception:
                        self.fail(f"{var} is not valid base64-encoded JSON")
                
                elif var == 'DATABASE_URL':
                    if not value.startswith('postgresql://'):
                        self.fail(f"{var} should start with 'postgresql://'")
        
        # Check optional variables
        for var, description in optional_vars.items():
            value = os.environ.get(var)
            if not value:
                missing_optional.append(f"{var} ({description})")
        
        # Report missing variables
        if missing_required:
            self.fail(f"Missing required environment variables: {', '.join(missing_required)}")
        
        if missing_optional:
            print(f"Missing optional environment variables: {', '.join(missing_optional)}")

    def test_health_check_endpoints(self):
        """Test health check endpoints."""
        try:
            # Test Django health check
            response = self.client.get('/')
            self.assertIn(response.status_code, [200, 302])  # 302 for redirect to login
            
            # Test database health
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                self.assertEqual(result[0], 1)
            
            # Test storage health
            test_content = ContentFile("health check".encode('utf-8'))
            health_file = "health-check.txt"
            saved_path = default_storage.save(health_file, test_content)
            
            self.assertTrue(default_storage.exists(saved_path))
            
            # Clean up
            default_storage.delete(health_file)
            
        except Exception as e:
            self.fail(f"Health check endpoints test failed: {e}")

    def test_data_consistency_across_restarts(self):
        """Test data consistency across service restarts."""
        try:
            # Create test data
            test_data = {
                'filename': 'consistency_test.txt',
                'content': 'Data consistency test content',
                'metadata': 'Test metadata'
            }
            
            # Store data
            file_content = ContentFile(test_data['content'].encode('utf-8'))
            saved_path = default_storage.save(test_data['filename'], file_content)
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_consistency (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255),
                        file_path VARCHAR(500),
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    INSERT INTO test_consistency (filename, file_path, metadata)
                    VALUES (%s, %s, %s)
                """, [test_data['filename'], saved_path, test_data['metadata']])
            
            # Simulate service restart by reconnecting
            connection.close()
            
            # Verify data persistence
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT filename, file_path, metadata 
                    FROM test_consistency 
                    WHERE filename = %s
                """, [test_data['filename']])
                
                result = cursor.fetchone()
                self.assertIsNotNone(result)
                self.assertEqual(result[0], test_data['filename'])
                self.assertEqual(result[1], saved_path)
                self.assertEqual(result[2], test_data['metadata'])
            
            # Verify file still exists
            self.assertTrue(default_storage.exists(saved_path))
            
            # Verify content integrity
            retrieved_content = default_storage.open(saved_path).read().decode('utf-8')
            self.assertEqual(retrieved_content, test_data['content'])
            
            # Clean up
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS test_consistency")
            default_storage.delete(saved_path)
            
        except Exception as e:
            self.fail(f"Data consistency across restarts test failed: {e}")

    def test_backup_and_restore_workflow(self):
        """Test backup and restore workflow."""
        try:
            # Create test data
            test_files = [
                ('backup1.txt', 'Backup test content 1'),
                ('backup2.txt', 'Backup test content 2'),
            ]
            
            # Upload files and store metadata
            file_paths = []
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_backup_restore (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255),
                        file_path VARCHAR(500),
                        content TEXT,
                        backup_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                for filename, content in test_files:
                    # Upload file
                    file_content = ContentFile(content.encode('utf-8'))
                    saved_path = default_storage.save(filename, file_content)
                    file_paths.append(saved_path)
                    
                    # Store metadata
                    cursor.execute("""
                        INSERT INTO test_backup_restore (filename, file_path, content)
                        VALUES (%s, %s, %s)
                    """, [filename, saved_path, content])
            
            # Simulate backup process
            backup_data = []
            with connection.cursor() as cursor:
                cursor.execute("SELECT filename, file_path, content FROM test_backup_restore")
                backup_data = cursor.fetchall()
            
            # Simulate restore process
            with connection.cursor() as cursor:
                # Clear existing data
                cursor.execute("DELETE FROM test_backup_restore")
                
                # Restore data
                for filename, file_path, content in backup_data:
                    cursor.execute("""
                        INSERT INTO test_backup_restore (filename, file_path, content)
                        VALUES (%s, %s, %s)
                    """, [filename, file_path, content])
            
            # Verify restore
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM test_backup_restore")
                count = cursor.fetchone()[0]
                self.assertEqual(count, len(test_files))
                
                for filename, file_path, content in backup_data:
                    # Verify file exists
                    self.assertTrue(default_storage.exists(file_path))
                    
                    # Verify content
                    retrieved_content = default_storage.open(file_path).read().decode('utf-8')
                    self.assertEqual(retrieved_content, content)
            
            # Clean up
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS test_backup_restore")
            for file_path in file_paths:
                default_storage.delete(file_path)
            
        except Exception as e:
            self.fail(f"Backup and restore workflow test failed: {e}")

    def test_security_and_permissions(self):
        """Test security and permissions."""
        try:
            # Test file access permissions
            test_content = ContentFile("Security test content".encode('utf-8'))
            security_file = "security-test.txt"
            saved_path = default_storage.save(security_file, test_content)
            
            # Test that file is accessible
            self.assertTrue(default_storage.exists(saved_path))
            
            # Test signed URL generation (for private files)
            signed_url = default_storage.url(saved_path)
            self.assertIsNotNone(signed_url)
            
            # Test database permissions
            with connection.cursor() as cursor:
                # Test that we can create tables
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_security (
                        id SERIAL PRIMARY KEY,
                        sensitive_data TEXT
                    )
                """)
                
                # Test that we can insert data
                cursor.execute("""
                    INSERT INTO test_security (sensitive_data)
                    VALUES ('test sensitive data')
                """)
                
                # Test that we can read data
                cursor.execute("SELECT sensitive_data FROM test_security")
                result = cursor.fetchone()
                self.assertEqual(result[0], 'test sensitive data')
                
                # Test that we can delete data
                cursor.execute("DELETE FROM test_security")
                
                # Verify deletion
                cursor.execute("SELECT COUNT(*) FROM test_security")
                count = cursor.fetchone()[0]
                self.assertEqual(count, 0)
                
                # Clean up
                cursor.execute("DROP TABLE IF EXISTS test_security")
            
            # Clean up file
            default_storage.delete(security_file)
            
        except Exception as e:
            self.fail(f"Security and permissions test failed: {e}")

    def test_monitoring_and_logging(self):
        """Test monitoring and logging capabilities."""
        try:
            # Test that operations can be logged
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_monitoring (
                        id SERIAL PRIMARY KEY,
                        operation VARCHAR(100),
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status VARCHAR(50),
                        details TEXT
                    )
                """)
                
                # Log operations
                operations = [
                    ('file_upload', 'success', 'Test file uploaded'),
                    ('database_query', 'success', 'Test query executed'),
                    ('file_download', 'success', 'Test file downloaded'),
                ]
                
                for operation, status, details in operations:
                    cursor.execute("""
                        INSERT INTO test_monitoring (operation, status, details)
                        VALUES (%s, %s, %s)
                    """, [operation, status, details])
                
                # Verify logging
                cursor.execute("SELECT COUNT(*) FROM test_monitoring")
                count = cursor.fetchone()[0]
                self.assertEqual(count, len(operations))
                
                # Test log retrieval
                cursor.execute("""
                    SELECT operation, status, details 
                    FROM test_monitoring 
                    ORDER BY timestamp DESC
                """)
                
                logs = cursor.fetchall()
                self.assertEqual(len(logs), len(operations))
                
                # Clean up
                cursor.execute("DROP TABLE IF EXISTS test_monitoring")
            
        except Exception as e:
            self.fail(f"Monitoring and logging test failed: {e}")
