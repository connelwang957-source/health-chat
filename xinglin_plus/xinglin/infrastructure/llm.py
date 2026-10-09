"""基础设施层：对话大模型工厂 + LLM 端口适配器（对应文档 §5.2 的 `xinglin/infrastructure/llm.py`）。

两种形态，各司其职：

- ``create_llm()``：LangChain ChatOpenAI（Runnable），供应用层写 LCEL 链时用；
- ``OpenAILlm``：实现领域端口 ``LLM``，供领域服务（NL2Cypher / 生成 / 意图 / ReAct）注入。

密钥只在本层可见（需求 13.3）；``trust_env=False`` 绕过系统代理（国内 API 必需）。
"""

import httpx
from langchain_openai import ChatOpenAI
from openai import OpenAI

from xinglin.config import LLM_TRUST_ENV, NL2CYPHER_LLM_CONFIG, RAG_LLM_CONFIG
from xinglin.domain.ports import LLM

REQUEST_TIMEOUT = 60


def create_llm(temperature: float = 0.7):
    """创建 DeepSeek 对话模型（OpenAI 兼容接口，LangChain Runnable）。"""
    return ChatOpenAI(
        model=RAG_LLM_CONFIG["model"],
        api_key=RAG_LLM_CONFIG["api_key"],
        base_url=RAG_LLM_CONFIG["base_url"],
        temperature=temperature,
        max_tokens=RAG_LLM_CONFIG["max_tokens"],
        http_client=httpx.Client(trust_env=LLM_TRUST_ENV, timeout=REQUEST_TIMEOUT),
    )


class OpenAILlm(LLM):
    """LLM 端口适配器：基于 OpenAI 兼容接口（DeepSeek / Qwen 等），供领域层注入。"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, temperature: float = 0.0,
                 max_tokens: int = 2048, trust_env: bool = LLM_TRUST_ENV):
        self._api_key = (api_key if api_key is not None
                         else NL2CYPHER_LLM_CONFIG["api_key"])
        self._base_url = base_url or NL2CYPHER_LLM_CONFIG["base_url"]
        self._model = model or NL2CYPHER_LLM_CONFIG["model"]
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = OpenAI(
            api_key=self._api_key or "EMPTY",       # 空 Key 时不报错，由 available 判定
            base_url=self._base_url,
            http_client=httpx.Client(trust_env=trust_env, timeout=REQUEST_TIMEOUT),
        )

    # -- 端口契约 -----------------------------------------------------------
    @property
    def available(self) -> bool:
        """配置齐全即视为可用（**不做网络探测**，避免健康检查产生费用）。"""
        return bool(self._api_key)

    def complete(self, system: str, user: str,
                 temperature: float = 0.0, max_tokens: int = 2048) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature or self._temperature,
            max_tokens=max_tokens or self._max_tokens,
        )
        return resp.choices[0].message.content or ""


__all__ = ["OpenAILlm", "create_llm", "REQUEST_TIMEOUT"]
