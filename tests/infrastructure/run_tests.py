#!/usr/bin/env python3
"""
Infrastructure test runner script.

This script provides a convenient way to run infrastructure tests
with proper setup and configuration.

Usage:
    python tests/infrastructure/run_tests.py
    python tests/infrastructure/run_tests.py --gcs-only
    python tests/infrastructure/run_tests.py --cloudsql-only
    python tests/infrastructure/run_tests.py --integration-only
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bh_opie.settings')
os.environ.setdefault('DJANGO_CONFIGURATION', 'Test')

# Configure Django
from configurations import importer
importer.install()

from django.conf import settings


def check_environment():
    """Check if required environment variables are set."""
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
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these variables before running tests.")
        return False
    
    print("✅ All required environment variables are set")
    return True


def check_dependencies():
    """Check if required dependencies are installed."""
    required_packages = [
        'django',
        'google-cloud-storage',
        'google-auth',
        'psycopg2',
        'pytest',
        'pytest-django',
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("Please install them with: pip install " + " ".join(missing_packages))
        return False
    
    print("✅ All required dependencies are installed")
    return True


def run_tests(test_pattern=None, verbose=False):
    """Run infrastructure tests."""
    test_dir = Path(__file__).parent
    
    # Build pytest command
    cmd = ['python', '-m', 'pytest']
    
    if verbose:
        cmd.append('-v')
    
    if test_pattern:
        cmd.append(test_pattern)
    else:
        cmd.append(str(test_dir))
    
    # Add pytest options
    cmd.extend([
        '--tb=short',
        '--strict-markers',
        '--disable-warnings',
    ])
    
    print(f"Running command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, cwd=project_root)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Run infrastructure tests')
    parser.add_argument('--gcs-only', action='store_true', 
                       help='Run only GCS storage tests')
    parser.add_argument('--cloudsql-only', action='store_true',
                       help='Run only Cloud SQL tests')
    parser.add_argument('--integration-only', action='store_true',
                       help='Run only integration tests')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    parser.add_argument('--check-env', action='store_true',
                       help='Check environment and dependencies only')
    
    args = parser.parse_args()
    
    print("🧪 Infrastructure Test Runner")
    print("=" * 50)
    
    # Check environment and dependencies
    if not check_environment():
        return 1
    
    if not check_dependencies():
        return 1
    
    if args.check_env:
        print("✅ Environment check complete")
        return 0
    
    # Determine test pattern
    test_pattern = None
    if args.gcs_only:
        test_pattern = "tests/infrastructure/test_gcs_storage.py"
    elif args.cloudsql_only:
        test_pattern = "tests/infrastructure/test_cloudsql.py"
    elif args.integration_only:
        test_pattern = "tests/infrastructure/test_integration.py"
    
    # Run tests
    print("\n🚀 Running infrastructure tests...")
    success = run_tests(test_pattern, args.verbose)
    
    if success:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
