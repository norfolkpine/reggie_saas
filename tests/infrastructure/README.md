# Infrastructure Tests

This directory contains comprehensive tests for the infrastructure components of the Reggie SaaS application.

## Overview

The infrastructure tests verify the functionality and reliability of:

- **Google Cloud Storage (GCS)** - File storage, upload/download, signed URLs
- **Cloud SQL Proxy** - Database connectivity, queries, transactions
- **Integration** - End-to-end workflows, service communication
- **Performance** - Load testing, response times
- **Security** - Access permissions, data integrity

## Test Structure

```
tests/infrastructure/
├── __init__.py                 # Package initialization
├── test_gcs_storage.py         # GCS storage tests
├── test_cloudsql.py           # Cloud SQL tests
├── test_integration.py        # End-to-end integration tests
├── test_utils.py              # Test utilities and helpers
├── run_tests.py               # Test runner script
└── README.md                  # This file
```

## Test Categories

### 1. GCS Storage Tests (`test_gcs_storage.py`)

**TestGCSStorageInfrastructure:**
- Service account key validation
- Credentials creation and authentication
- Storage configuration validation
- Bucket access permissions
- File upload/download operations
- Signed URL generation
- File deletion operations
- Error handling for various scenarios

**TestGCSStorageIntegration:**
- Django FileField integration
- URL generation for different file types
- Large file handling
- Concurrent access scenarios

### 2. Cloud SQL Tests (`test_cloudsql.py`)

**TestCloudSQLInfrastructure:**
- Connection string parsing
- Database connectivity establishment
- Basic CRUD operations
- Transaction handling
- Connection pooling
- Error handling
- Performance testing
- Environment variable validation
- Migration capabilities
- Proxy connectivity

**TestCloudSQLIntegration:**
- Django ORM operations
- Bulk operations
- Transaction handling
- Query performance
- Migration integration
- Connection resilience

### 3. Integration Tests (`test_integration.py`)

**TestInfrastructureIntegration:**
- Complete file upload workflow
- Service communication consistency
- Error handling across services
- Performance under load
- Environment variable validation
- Health check endpoints
- Data consistency across restarts
- Backup and restore workflow
- Security and permissions
- Monitoring and logging

## Running Tests

### Prerequisites

1. **Environment Variables:**
   ```bash
   export GCS_STORAGE_SA_KEY_BASE64="your_base64_encoded_service_account_key"
   export GCS_BUCKET_NAME="your-gcs-bucket-name"
   export DATABASE_URL="postgresql://user:pass@host:port/db"
   ```

2. **Dependencies:**
   ```bash
   pip install pytest pytest-django google-cloud-storage google-auth psycopg2
   ```

### Running All Tests

```bash
# Using the test runner script
python tests/infrastructure/run_tests.py

# Using pytest directly
pytest tests/infrastructure/

# Using Django test runner
python manage.py test tests.infrastructure
```

### Running Specific Test Categories

```bash
# GCS tests only
python tests/infrastructure/run_tests.py --gcs-only

# Cloud SQL tests only
python tests/infrastructure/run_tests.py --cloudsql-only

# Integration tests only
python tests/infrastructure/run_tests.py --integration-only
```

### Running Individual Test Files

```bash
# GCS storage tests
pytest tests/infrastructure/test_gcs_storage.py -v

# Cloud SQL tests
pytest tests/infrastructure/test_cloudsql.py -v

# Integration tests
pytest tests/infrastructure/test_integration.py -v
```

### Running Specific Test Methods

```bash
# Test GCS file upload
pytest tests/infrastructure/test_gcs_storage.py::TestGCSStorageInfrastructure::test_gcs_file_upload_download -v

# Test Cloud SQL connection
pytest tests/infrastructure/test_cloudsql.py::TestCloudSQLInfrastructure::test_database_connection_establishment -v

# Test integration workflow
pytest tests/infrastructure/test_integration.py::TestInfrastructureIntegration::test_complete_file_upload_workflow -v
```

## Test Configuration

### Environment Setup

The tests automatically detect the environment and configure themselves accordingly:

- **Development**: Uses local file storage and database
- **Test**: Uses test database and mocked storage (when possible)
- **Production**: Uses actual GCS and Cloud SQL (requires proper credentials)

### Test Database

Tests use a separate test database (`test_bh_opie`) to avoid affecting development data.

### Mocking

Some tests use mocks to avoid external dependencies:
- `MockGCSStorage` - For testing without actual GCS access
- `MockCloudSQLConnection` - For testing without actual database access

## Test Utilities

### InfrastructureTestMixin

Provides common utilities for infrastructure tests:
- `create_test_file()` - Create test files in storage
- `create_test_table()` - Create test tables in database
- `assert_gcs_configured()` - Assert GCS configuration
- `assert_database_configured()` - Assert database configuration
- `assert_environment_variables()` - Assert required env vars

### Decorators

- `@mock_gcs_storage` - Mock GCS storage for testing
- `@mock_cloudsql_connection` - Mock Cloud SQL connection
- `@skip_if_no_gcs` - Skip test if GCS not configured
- `@skip_if_no_cloudsql` - Skip test if Cloud SQL not configured

### Test Data Generators

- `TestDataGenerator.generate_file_content()` - Generate test file content
- `TestDataGenerator.generate_test_files()` - Generate multiple test files
- `TestDataGenerator.generate_database_records()` - Generate test database records

## Continuous Integration

### GitHub Actions

The tests are designed to run in GitHub Actions with proper environment setup:

```yaml
- name: Run Infrastructure Tests
  run: |
    python tests/infrastructure/run_tests.py --verbose
  env:
    GCS_STORAGE_SA_KEY_BASE64: ${{ secrets.GCS_STORAGE_SA_KEY_BASE64 }}
    GCS_BUCKET_NAME: ${{ secrets.GCS_BUCKET_NAME }}
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

### Local Development

For local development, you can run tests with mocked services:

```bash
# Run tests with mocks (no external dependencies)
pytest tests/infrastructure/ -m "not integration"

# Run tests with real services (requires credentials)
pytest tests/infrastructure/ -m "integration"
```

## Troubleshooting

### Common Issues

1. **Missing Environment Variables**
   ```
   Error: Missing required environment variables: GCS_STORAGE_SA_KEY_BASE64
   ```
   Solution: Set the required environment variables

2. **Database Connection Failed**
   ```
   Error: Database connection establishment failed
   ```
   Solution: Check DATABASE_URL and ensure database is accessible

3. **GCS Authentication Failed**
   ```
   Error: GCS credentials creation failed
   ```
   Solution: Verify GCS_STORAGE_SA_KEY_BASE64 is valid base64-encoded JSON

4. **Permission Denied**
   ```
   Error: Permission denied
   ```
   Solution: Check service account permissions for GCS and Cloud SQL

### Debug Mode

Run tests with debug output:

```bash
pytest tests/infrastructure/ -v -s --tb=long
```

### Test Isolation

Each test is isolated and cleans up after itself:
- Test files are automatically deleted
- Test database tables are dropped
- No side effects on other tests

## Contributing

When adding new infrastructure tests:

1. Follow the existing test structure
2. Use appropriate test mixins and utilities
3. Add proper cleanup in tearDown methods
4. Include both positive and negative test cases
5. Add docstrings explaining what each test verifies
6. Update this README if adding new test categories

## Performance Considerations

- Tests are designed to run quickly (< 30 seconds total)
- Use mocks when possible to avoid external dependencies
- Clean up resources immediately after use
- Use connection pooling for database tests
- Batch operations when testing performance
