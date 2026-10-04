import shutil
from pathlib import Path

import chromadb


def init_chroma_db(db_dir: str = "./chroma_db"):
    """
    Initialize the Chroma persistent vector database
    If the database directory already exists, delete it and recreate a fresh one
    """
    db_path = Path(db_dir)

    # Check if the database directory exists
    if db_path.exists():
        print(f"Vector database directory {db_path} already exists, deleting...")
        try:
            shutil.rmtree(db_path)
            print("Old vector database directory deleted")
        except Exception as e:
            print(f"Error deleting vector database directory: {e}")
            return None

    try:
        # Create a new Chroma persistent client
        client = chromadb.PersistentClient(path=str(db_path))
        print(f"Chroma vector database initialized successfully, path: {db_path}")
        return client
    except Exception as e:
        print(f"Error initializing Chroma vector database: {e}")
        return None


# Usage example
if __name__ == "__main__":
    client = init_chroma_db()

    if client:
        # Continue with subsequent operations here
        print("Chroma vector database created successfully, you can start using it")
    else:
        print("Failed to create Chroma vector database")
