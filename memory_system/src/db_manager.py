import sqlite3
import json

class DBManager:
    def __init__(self, db_path="memory_system.sqlite"):
        self.db_path = db_path
        self.conn = None
        self.connect()
        self.create_tables()
        print(f"DBManager initialized with database: {self.db_path}")

    def connect(self):
        """Establishes a connection to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Access columns by name
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")
            self.conn = None

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def create_tables(self):
        """Creates the necessary tables for storing memories and their embeddings."""
        if not self.conn:
            print("Cannot create tables: No database connection.")
            return

        cursor = self.conn.cursor()
        # Table for storing memory items (text content, metadata)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Table for storing embeddings, linked to memories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                memory_id INTEGER PRIMARY KEY,
                vector BLOB NOT NULL, -- Storing as BLOB for efficiency
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        """)
        self.conn.commit()
        print("Tables 'memories' and 'embeddings' checked/created.")

    def insert_memory(self, content: str, metadata: dict = None) -> int:
        """Inserts a new memory into the 'memories' table and returns its ID."""
        if not self.conn:
            print("Cannot insert memory: No database connection.")
            return -1

        cursor = self.conn.cursor()
        metadata_json = json.dumps(metadata) if metadata else "{}"
        cursor.execute("INSERT INTO memories (content, metadata) VALUES (?, ?)", (content, metadata_json))
        self.conn.commit()
        print(f"Memory inserted with ID: {cursor.lastrowid}")
        return cursor.lastrowid

    def insert_embedding(self, memory_id: int, vector: list[float]):
        """Inserts an embedding vector for a given memory ID."""
        if not self.conn:
            print("Cannot insert embedding: No database connection.")
            return

        cursor = self.conn.cursor()
        # Convert list of floats to a JSON string or bytes for BLOB storage
        # For simplicity, let's store as JSON string first, then consider numpy bytes for efficiency later.
        vector_blob = json.dumps(vector).encode('utf-8')
        try:
            cursor.execute("INSERT INTO embeddings (memory_id, vector) VALUES (?, ?)", (memory_id, vector_blob))
            self.conn.commit()
            print(f"Embedding inserted for memory ID: {memory_id}")
        except sqlite3.IntegrityError:
            print(f"Embedding for memory ID {memory_id} already exists. Consider an update operation.")
        except Exception as e:
            print(f"Error inserting embedding: {e}")

    def get_memory_with_embedding(self, memory_id: int) -> dict:
        """Retrieves a memory and its embedding by memory ID."""
        if not self.conn:
            print("Cannot retrieve memory: No database connection.")
            return None

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT m.id, m.content, m.metadata, e.vector
            FROM memories m
            LEFT JOIN embeddings e ON m.id = e.memory_id
            WHERE m.id = ?
        """, (memory_id,))
        row = cursor.fetchone()
        if row:
            memory_data = dict(row)
            if memory_data['metadata']:
                memory_data['metadata'] = json.loads(memory_data['metadata'])
            if memory_data['vector']:
                memory_data['vector'] = json.loads(memory_data['vector'].decode('utf-8')) # Decode BLOB back to list
            return memory_data
        return None

if __name__ == "__main__":
    # Example Usage:
    db_manager = DBManager(db_path="test_memory_system.sqlite")

    # Insert a new memory
    mem_id = db_manager.insert_memory("这是一个关于OpenClaw的记忆。", {"source": "user_input", "tags": ["AI", "OpenClaw"]})

    # Simulate an embedding vector
    sample_vector = [0.1] * 768  # Replace with actual embedding from EmbeddingClient

    # Insert the embedding for the new memory
    if mem_id != -1:
        db_manager.insert_embedding(mem_id, sample_vector)

    # Retrieve the memory and its embedding
    retrieved_memory = db_manager.get_memory_with_embedding(mem_id)
    if retrieved_memory:
        print("\nRetrieved Memory:")
        print(f"ID: {retrieved_memory['id']}")
        print(f"Content: {retrieved_memory['content']}")
        print(f"Metadata: {retrieved_memory['metadata']}")
        print(f"Vector (first 5 dims): {retrieved_memory['vector'][:5]}...")
    else:
        print("Memory not found.")

    db_manager.close()
    print("Database connection closed.")
