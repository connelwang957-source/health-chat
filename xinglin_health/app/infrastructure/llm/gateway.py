"""LLM 网关（infrastructure）：封装 langchain-openai ChatOpenAI。

厂商切换 = 改 .env 的 LLM_BASE_URL / LLM_MODEL / LLM_API_KEY，业务层零改动。
密钥仅在本层可见（13.3）。
"""

import logging
from functools import lru_cache

from pydantic import BaseModel

from app.infrastructure.config import get_settings

logger = logging.getLogger(__name__)


class LLMGateway:
    def __init__(self, base_url: str, api_key: str, model: str,
                 temperature: float = 0.3, max_tokens: int = 800):
        self.base_url, self.api_key, self.model = base_url, api_key, model
        self.temperature, self.max_tokens = temperature, max_tokens
        self._chat = None

    @property
    def available(self) -> bool:
        """是否配置了 API Key（不做网络探测，避免健康检查产生调用费用）。"""
        return bool(self.api_key)

    def _ensure_chat(self):
        if self._chat is None:
            from langchain_openai import ChatOpenAI
            self._chat = ChatOpenAI(
                model=self.model, api_key=self.api_key, base_url=self.base_url,
                temperature=self.temperature, max_tokens=self.max_tokens,
                timeout=60)
        return self._chat

    def generate(self, messages) -> str:
        """messages: langchain 消息列表或 [(role, text)]。"""
        resp = self._ensure_chat().invoke(messages)
        return resp.content

    def structured(self, system_prompt: str, user_input: str, schema: type[BaseModel]):
        """结构化输出（意图识别等）。schema 为 pydantic 模型。"""
        chat = self._ensure_chat().with_structured_output(schema)
        return chat.invoke([("system", system_prompt), ("human", user_input)])


@lru_cache
def get_llm_gateway() -> LLMGateway:
    s = get_settings()
    return LLMGateway(s.llm_base_url, s.llm_api_key, s.llm_model,
                      s.llm_temperature, s.llm_max_tokens)
