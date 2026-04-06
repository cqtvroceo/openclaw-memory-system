from __future__ import annotations

import json
from typing import Iterable, Optional

import requests

from .config import DEFAULT_EMBED_BASE_URL, DEFAULT_EMBED_MODEL


class EmbeddingClient:
    def __init__(
        self,
        api_base: str = DEFAULT_EMBED_BASE_URL,
        model_name: str = DEFAULT_EMBED_MODEL,
        timeout: int = 60,
        batch_size: int = 4,
    ):
        self.api_base = api_base.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self.batch_size = max(1, batch_size)
        self.session = requests.Session()

    @property
    def available(self) -> bool:
        return self.is_available()

    def is_available(self) -> bool:
        try:
            resp = self.session.get(f"{self.api_base}/models", timeout=min(self.timeout, 5))
            resp.raise_for_status()
            return True
        except Exception:
            try:
                return bool(self.get_embedding("ping"))
            except Exception:
                return False

    def get_embedding(self, text: str) -> list[float]:
        payload = {"model": self.model_name, "input": text}
        try:
            response = self.session.post(
                f"{self.api_base}/embeddings",
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if "data" in data and len(data["data"]) > 0 and "embedding" in data["data"][0]:
                return data["data"][0]["embedding"]
            print(f"Error: Unexpected response format from embedding service for text: '{text[:30]}...'")
            return []
        except requests.exceptions.ConnectionError as e:
            print(f"Connection Error: Could not connect to the embedding service at {self.api_base}. Is the service running? Error: {e}")
            return []
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", "?")
            body = getattr(e.response, "text", str(e))
            print(f"HTTP Error: {status} - {body}")
            return []
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return []

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        return [vec for vec in self.embed_texts(list(texts)) if vec]

    def embed_or_none(self, texts: Iterable[str]) -> list[list[float]] | None:
        results = self.embed_texts(list(texts))
        if not any(results):
            return None
        return [vec for vec in results if vec]

    def _post_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        payload = {"model": self.model_name, "input": texts}
        response = self.session.post(
            f"{self.api_base}/embeddings",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        data.sort(key=lambda item: item.get("index", 0))
        embeddings = [item.get("embedding") for item in data]
        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"Unexpected batch embedding response length. expected={len(texts)} got={len(embeddings)}"
            )
        return embeddings

    def _truncate_text(self, text: str, max_tokens: int = 512) -> str:
        """智能截断文本，保留关键信息"""
        # 优先保留开头和结尾的上下文
        words = text.split()
        if len(words) <= max_tokens:
            return text

        # 截取前1/3和后1/3
        start_words = words[:max_tokens // 3]
        end_words = words[-max_tokens // 3:]

        return " ".join(start_words + ["..."] + end_words)

    def embed_texts(self, texts: list[str]) -> list[Optional[list[float]]]:
        if not texts:
            return []

        results: list[Optional[list[float]]] = []
        for start in range(0, len(texts), self.batch_size):
            chunk = texts[start : start + self.batch_size]

            # 对每个文本进行智能截断
            truncated_chunk = [
                self._truncate_text(text) if len(text.split()) > 512 else text
                for text in chunk
            ]

            try:
                # 尝试批量embedding
                batch_results = self._post_batch(truncated_chunk)
                results.extend(batch_results)
                continue
            except Exception as e:
                print(f"[!] Batch embedding warning: {e}")

                # 对于批量失败的情况，逐个处理
                for text in truncated_chunk:
                    vec = self.get_embedding(text)
                    results.append(vec or None)

        return results
