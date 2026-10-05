from google import genai
from google.genai import types
from typing import Generator
from config import GOOGLE_API_KEY
from services.llm.base import BaseLLM


class GeminiLLM(BaseLLM):
    AVAILABLE_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]

    def __init__(self, model: str = "gemini-2.5-flash"):
        self._model = model
        self._client = genai.Client(api_key=GOOGLE_API_KEY)

    @property
    def model_name(self) -> str:
        return self._model

    def chat_stream(self, system_prompt: str, messages: list[dict]) -> Generator[str, None, None]:
        # Gemini는 assistant → model 로 role명이 다름
        contents = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
        ]
        for chunk in self._client.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        ):
            if chunk.text:
                yield chunk.text