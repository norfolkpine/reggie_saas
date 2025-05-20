import os
import re


def update_imports_in_file(file_path):
    """Update import statements in a single file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        print(f"Skipping {file_path} - not UTF-8 encoded")
        return False

    # Patterns to match different import styles
    patterns = [
        (r"from\s+docs(?:\s+import|\s*\.)", "from apps.docs"),  # from apps.docs or from apps.docs
        (r"import\s+docs(?:\s+as|\s*$)", "import apps.docs"),  # import docs or import apps.docs
        (r"from\s+docs\.", "from apps.docs."),  # from apps.docssomething
        (r"from\s+apps\.docs\.models\s+import", "from apps.docs.models import"),  # Clean up any double apps
        (r"from\s+apps\.docs\.factories\s+import", "from apps.docs.factories import"),  # Clean up any double apps
        (r"from\s+core\s+import", "from apps.docs import"),  # from apps.docs import
        (r"from\s+core\.", "from apps.docs."),  # from apps.docs.something
        (r"from\s+impress(?:\s+import|\s*\.)", "from bh_reggie"),  # from bh_reggie or from bh_reggie
        (r"import\s+impress(?:\s+as|\s*$)", "import bh_reggie"),  # import impress or import bh_reggie
        (r"from\s+impress\.", "from bh_reggie."),  # from bh_reggiesomething
        (
            r"DJANGO_SETTINGS_MODULE\s*=\s*[\"']impress\.settings[\"']",
            "DJANGO_SETTINGS_MODULE = 'bh_reggie.settings'",
        ),  # settings module
        (r"ROOT_URLCONF\s*=\s*[\"']impress\.urls[\"']", "ROOT_URLCONF = 'bh_reggie.urls'"),  # urls module
        (
            r"WSGI_APPLICATION\s*=\s*[\"']impress\.wsgi\.application[\"']",
            "WSGI_APPLICATION = 'bh_reggie.wsgi.application'",
        ),  # wsgi application
        (r"app\s*=\s*Celery\([\"']impress[\"']\)", "app = Celery('bh_reggie')"),  # celery app name
        (
            r"SESSION_COOKIE_NAME\s*=\s*[\"']impress_sessionid[\"']",
            "SESSION_COOKIE_NAME = 'bh_reggie_sessionid'",
        ),  # session cookie name
        (
            r"LANGUAGE_COOKIE_NAME\s*=\s*[\"']impress_language[\"']",
            "LANGUAGE_COOKIE_NAME = 'bh_reggie_language'",
        ),  # language cookie name
    ]

    new_content = content
    for pattern, replacement in patterns:
        new_content = re.sub(pattern, replacement, new_content)

    # Only write if changes were made
    if new_content != content:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated imports in {file_path}")
        return True
    return False


def should_process_directory(directory):
    """Check if a directory should be processed."""
    # Skip virtual environment directories
    if any(part in directory for part in ["venv", "env", ".venv", ".env", "__pycache__", ".git"]):
        return False
    return True


def process_directory(directory):
    """Process all Python files in a directory and its subdirectories."""
    updated_files = 0
    for root, dirs, files in os.walk(directory):
        # Skip directories that shouldn't be processed
        dirs[:] = [d for d in dirs if should_process_directory(os.path.join(root, d))]

        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                if update_imports_in_file(file_path):
                    updated_files += 1
    return updated_files


if __name__ == "__main__":
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Process all Python files in the project
    updated_count = process_directory(current_dir)
    print(f"\nUpdated imports in {updated_count} files")
