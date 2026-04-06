import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.embedding_client import EmbeddingClient
from src.db_manager import DBManager

def main():
    print("Starting Memory System Demo...")
    
    # Initialize components
    embedding_client = EmbeddingClient()
    db_manager = DBManager()

    # --- Simulate a user query ---
    user_query = "OpenClaw 是什么？"

    # Step 1: Get embedding for the query
    query_embedding = embedding_client.get_embedding(user_query)
    if not query_embedding:
        print("Failed to get embedding for query.")
        return

    print(f"Query embedding generated (length: {len(query_embedding)})")

    # Step 2: Store a sample memory (this simulates ingestion)
    sample_memory_content = "OpenClaw 是一个强大的 AI 助手框架，用于构建智能对话系统。"
    sample_metadata = {"source": "user_input", "type": "definition"}

    memory_id = db_manager.insert_memory(sample_memory_content, sample_metadata)
    if memory_id == -1:
        print("Failed to insert memory.")
        return

    # Step 3: Store the embedding for the memory
    db_manager.insert_embedding(memory_id, query_embedding) # Using query embedding for demo
    print(f"Sample memory stored with ID: {memory_id}")

    # Step 4: Retrieve the memory (simulating a retrieval step)
    retrieved_memory = db_manager.get_memory_with_embedding(memory_id)
    if retrieved_memory:
        print("\nRetrieved Memory:")
        print(f"ID: {retrieved_memory['id']}")
        print(f"Content: {retrieved_memory['content']}")
        print(f"Metadata: {retrieved_memory['metadata']}")
    else:
        print("Failed to retrieve memory.")

    db_manager.close()
    print("Memory System Demo completed.")

if __name__ == "__main__":
    main()