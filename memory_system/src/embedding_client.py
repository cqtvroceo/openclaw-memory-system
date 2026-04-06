from __future__ import annotations

import json

import requests


class EmbeddingClient:
    def __init__(
        self,
        api_base: str = "http://127.0.0.1:11435/v1",
        model_name: str = "nomic-embed-text-v1.5.f16.gguf",
    ) -> None:
        self.api_base = api_base
        self.model_name = model_name
        self.session = requests.Session()
        print(
            f"EmbeddingClient initialized with API base: {self.api_base} and model: {self.model_name}"
        )

    def get_embedding(self, text: str) -> list[float]:
        """Send text to the local embedding model and return the embedding vector."""
        url = f"{self.api_base}/embeddings"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": self.model_name,
            "input": text,
        }
        try:
            response = self.session.post(url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            data = response.json()
            if "data" in data and len(data["data"]) > 0 and "embedding" in data["data"][0]:
                print(f"Successfully got embedding for text: '{text[:30]}...'")
                return data["data"][0]["embedding"]
            print(
                f"Error: Unexpected response format from embedding service for text: '{text[:30]}...'"
            )
            return []
        except requests.exceptions.ConnectionError as e:
            print(
                f"Connection Error: Could not connect to the embedding service at {self.api_base}. "
                f"Is the service running? Error: {e}"
            )
            return []
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            return []
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return []


if __name__ == "__main__":
    client = EmbeddingClient()

    test_text = "这是一个测试文本，用于生成嵌入向量。"
    embedding = client.get_embedding(test_text)
    if embedding:
        print(f"Embedding length: {len(embedding)}")
        print(f"First 5 dimensions of embedding: {embedding[:5]}")
    else:
        print("Failed to get embedding.")

    test_text_2 = "OpenClaw是一个强大的AI助手框架。"
    embedding_2 = client.get_embedding(test_text_2)
    if embedding_2:
        print(f"Embedding 2 length: {len(embedding_2)}")
        print(f"First 5 dimensions of embedding 2: {embedding_2[:5]}")
    else:
        print("Failed to get embedding 2.")
