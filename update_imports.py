import os
import re


def update_imports_in_file(file_path):
    """Update import statements in a single file."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Patterns to match different import styles
    patterns = [
        (r"from\s+docs(?:\s+import|\s*\.)", "from apps.docs"),  # from docs import or from docs.
        (r"import\s+docs(?:\s+as|\s*$)", "import apps.docs"),  # import docs or import docs as
        (r"from\s+docs\.", "from apps.docs."),  # from docs.something
        (r"from\s+apps\.docs\.models\s+import", "from apps.docs.models import"),  # Clean up any double apps
        (r"from\s+apps\.docs\.factories\s+import", "from apps.docs.factories import"),  # Clean up any double apps
        (r"from\s+core\s+import", "from apps.docs import"),  # from core import
        (r"from\s+core\.", "from apps.docs."),  # from core.something
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


def process_directory(directory):
    """Process all Python files in a directory and its subdirectories."""
    updated_files = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                if update_imports_in_file(file_path):
                    updated_files += 1
    return updated_files


if __name__ == "__main__":
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Path to the tests directory
    tests_dir = os.path.join(current_dir, "apps", "docs", "tests")

    # Ensure the directory exists
    if not os.path.exists(tests_dir):
        print(f"Directory {tests_dir} does not exist!")
        exit(1)

    # Process all files
    updated_count = process_directory(tests_dir)
    print(f"\nUpdated imports in {updated_count} files")
