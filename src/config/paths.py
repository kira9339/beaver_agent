from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Configuration file paths
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE_FILE = PROJECT_ROOT / ".env.example"

# Source code directory
SRC_DIR = PROJECT_ROOT / "src"
CONFIG_DIR = SRC_DIR / "config"

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

# Tests directory
TESTS_DIR = PROJECT_ROOT / "tests"

# Docs directory
DOCS_DIR = PROJECT_ROOT / "docs"

# Scripts directory
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Database file paths (default)
DEFAULT_DB_PATH = PROJECT_ROOT / "beaver_assistant.db"
TEST_DB_PATH = PROJECT_ROOT / "beaver_assistant_test.db"
CHROMA_DB_PATH = PROJECT_ROOT / "chroma_db"

# Debug info
if __name__ == "__main__":
    print("=== Project Paths Configuration ===")
    print(f"Project root: {PROJECT_ROOT}")
    print(f".env file: {ENV_FILE}")
    print(f"Source code directory: {SRC_DIR}")
    print(f"Configuration directory: {CONFIG_DIR}")
    print(f"Data directory: {DATA_DIR}")
    print(f"Logs directory: {LOGS_DIR}")
    print(f"Tests directory: {TESTS_DIR}")
