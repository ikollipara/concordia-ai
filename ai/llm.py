"""
Project:     Concordia AI
Name:        ai/llm.py
Author:      Ian Kollipara <ian.kollipara@cune.edu>
Date:        2025-08-15
Description: Wrapper for interactions with LLMs
"""

from __future__ import annotations

import time
import typing as t

import openai
import tiktoken
from django import conf


def get_model():
    model = getattr(conf.settings, "LLM_MODEL", "Stub")

    if model == "Stub":
        return Stub()

    if model == "OpenAI":
        return OpenAI()


class Message(t.TypedDict):
    """A helper type representing a structured LLM Message."""

    role: t.Literal["user", "system", "assistant"]
    content: str


class LLMAdapter:
    def make_response(
        self, context: str, history: list[Message], prompt: str
    ) -> t.Generator[str, None, None]:
        """Generate a response based on the context, history, and prompt."""

        raise NotImplementedError()


class Stub(LLMAdapter):
    def make_response(self, context, history, prompt):
        time.sleep(1)
        yield "Hello "
        time.sleep(2)
        yield "World!"


class OpenAI(LLMAdapter):
    @property
    def max_tokens(self) -> int:
        """Max tokens allowed."""

        return getattr(conf.settings, "OPENAI_MAX_TOKENS", 8_000)

    @property
    def model(self) -> str:
        """Model to query."""

        return getattr(conf.settings, "OPENAI_MODEL", "gpt-4.1-mini")

    @property
    def api_key(self) -> str:
        """API Key for Open AI."""

        if hasattr(conf.settings, "OPENAI_KEY"):
            return conf.settings.OPENAI_KEY

        raise ValueError("Missing OPENAI_KEY in settings!")

    def _count_token(self, messages: list[Message]):
        """Count the tokens for the given messages."""

        encoding = tiktoken.get_encoding("cli100k_base")

        # Avg. Overhead for a message
        tokens_per_message = 3
        # The startup token amount
        priming = 3

        return sum(
            (tokens_per_message + len(encoding.encode(m["content"])) for m in messages)
            + priming
        )

    def _truncate_history(self, context: str, history: list[Message], prompt: str):
        """Truncate the history to fit within the token limit."""

        system_msg = Message(role="system", content=context)
        user_msg = Message(role="user", content=prompt)

        trimmed_history = history[:]

        # We utilize the fact Python stores a reference here
        # to mutate the messages list in the following while loop
        messages = [system_msg] + trimmed_history + [user_msg]

        while self._count_token(messages) >= self.max_tokens:
            if len(trimmed_history) == 0:
                return []

            trimmed_history.pop(0)

        return trimmed_history

    def make_response(self, context, history, prompt):
        client = openai.Client(
            api_key=self.api_key,
            timeout=60 * 4,  # 4 Minutes
        )
        system_msg = Message(role="system", content=context)
        user_msg = Message(role="user", content=prompt)

        trimmed_history = self._truncate_history(context, history, prompt)

        for choice in client.chat.completions.create(
            messages=[system_msg, *trimmed_history, user_msg],
            model=self.model,
            stream=True,
        ):
            delta = choice.choices[0].delta
            if delta and delta.content:
                yield delta.content
