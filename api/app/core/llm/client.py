"""LLM 调用客户端：基于用户的模型配置调用 OpenAI 兼容接口。

封装 embedding / chat / 多模态 / rerank 调用，供解析、检索、问答复用。
"""
import httpx

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    """一个 provider 配置对应一个 client（base_url + api_key + model）。"""

    def __init__(self, base_url: str, api_key: str, model_name: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def embed(
        self, texts: list[str], dimensions: int | None = None
    ) -> list[list[float]]:
        """文本批量向量化。返回与输入等长的向量列表。

        dimensions 控制输出维度（默认取 settings.embedding_dims），
        与 ES 索引维度保持一致；支持指定维度的 provider（如智谱 embedding-3）会按此裁剪。
        """
        dims = dimensions or settings.embedding_dims
        payload: dict = {
            "model": self.model_name,
            "input": texts,
            "dimensions": dims,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        # OpenAI 兼容：data.data[i].embedding，按 index 排序
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]

    async def embed_one(self, text: str, dimensions: int | None = None) -> list[float]:
        vecs = await self.embed([text], dimensions=dimensions)
        return vecs[0]

    async def chat(
        self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 2048
    ) -> str:
        """非流式对话，返回完整文本。"""
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def vision(
        self, prompt: str, image_b64: str, mime: str = "image/jpeg", max_tokens: int = 1024
    ) -> str:
        """多模态看图：传入提示词 + base64 图片，返回模型描述文本。"""
        data_url = f"data:{mime};base64,{image_b64}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[tuple[int, float]]:
        """重排，返回 [(原始索引, 相关性分数), ...]，按分数降序。"""
        payload = {"model": self.model_name, "query": query, "documents": documents}
        if top_n:
            payload["top_n"] = top_n
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/rerank", headers=self._headers, json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results", [])
        return [
            (r["index"], r.get("relevance_score", 0.0))
            for r in sorted(
                results, key=lambda x: x.get("relevance_score", 0.0), reverse=True
            )
        ]
