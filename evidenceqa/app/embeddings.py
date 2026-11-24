# -*- coding: utf-8 -*-
"""Embedding providers —— 特征哈希（离线）或真实 embedding API。

两种实现，接口一致（都提供 embed(text) -> list[float]）：

    HashingEmbedder   特征哈希，离线、零依赖，本质是词面匹配（上游默认）
    ApiEmbedder       调用 OpenAI 兼容的 /embeddings 接口，真正的语义向量

用环境变量切换，默认 hash，保持上游行为完全不变：

    EMBEDDING_PROVIDER=hash | api
    EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
    EMBEDDING_API_KEY=sk-xxxxxxxx
    EMBEDDING_MODEL=BAAI/bge-m3

切换步骤：
    1. .env 里加上面四行（PROVIDER=api）
    2. 重启服务（uvicorn 只在启动时读一次环境变量）
    3. 重新导入语料（维度变了，旧向量必须重建）
"""

import hashlib
import json
import math
import os
import re
import urllib.request


TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    tokens = TOKEN_PATTERN.findall(text.lower())
    cjk_chars = [
        token for token in tokens if len(token) == 1 and "\u4e00" <= token <= "\u9fff"
    ]
    bigrams = [left + right for left, right in zip(cjk_chars, cjk_chars[1:])]
    return tokens + bigrams


class HashingEmbedder:
    """上游实现，保持原样，一个字都没改。"""

    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            vector[int.from_bytes(digest, "little") % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class ApiEmbedder:
    """调用 OpenAI 兼容的 /embeddings 接口，带内存缓存与批量请求。"""

    def __init__(self) -> None:
        self.base_url = os.getenv("EMBEDDING_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("EMBEDDING_API_KEY", "")
        self.model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
        self.dimensions = 0
        self._cache: dict[str, list[float]] = {}
        if not self.base_url or not self.api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=api，但缺少 EMBEDDING_BASE_URL 或 EMBEDDING_API_KEY"
            )

    def _post(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": texts}
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))

        items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        if not items:
            raise RuntimeError(f"embedding 接口返回为空：{str(data)[:200]}")
        return [_l2_normalize(item["embedding"]) for item in items]

    def embed_many(self, texts: list[str], batch_size: int = 16) -> list[list[float]]:
        results: list[list[float]] = []
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset : offset + batch_size]
            vectors = self._post(batch)
            for text, vector in zip(batch, vectors):
                self._cache[_cache_key(text)] = vector
            results.extend(vectors)
        if results and self.dimensions == 0:
            self.dimensions = len(results[0])
        return results

    def embed(self, text: str) -> list[float]:
        key = _cache_key(text)
        if key not in self._cache:
            self.embed_many([text])
        return self._cache[key]


def _cache_key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def get_embedder():
    """按环境变量返回当前该用的 embedder。"""
    provider = os.getenv("EMBEDDING_PROVIDER", "hash").strip().lower()
    if provider == "api":
        return ApiEmbedder()
    return HashingEmbedder()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))
