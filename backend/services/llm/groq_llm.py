from groq import Groq
from typing import Generator
from config import GROQ_API_KEY
from services.llm.base import BaseLLM


class GroqLLM(BaseLLM):
    AVAILABLE_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]

    def __init__(self, model: str = "openai/gpt-oss-120b"):
        self._model = model
        self._client = Groq(api_key=GROQ_API_KEY)

    @property
    def model_name(self) -> str:
        return self._model

    def chat_stream(self, system_prompt: str, messages: list[dict]) -> Generator[str, None, None]:
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system_prompt}, *messages],
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta