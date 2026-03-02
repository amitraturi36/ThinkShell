from __future__ import annotations

import os
import uuid
from threading import RLock
from typing import Optional

from llm.Decision import Decision
from llm.openaiintegrator import OpenAiIntegrator


class DecisionCache:
    _lock = RLock()
    _instance: Optional[Decision] = None

    @classmethod
    def get(cls) -> Decision | None:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls._setup_environment()
                if cls._instance is not None:
                    cls._instance.init_ai_terminal()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    @staticmethod
    def _setup_environment() -> Decision | None:
        """
        Detects available provider and initializes Decision engine.
        Raises clear errors instead of returning shell strings.
        """
        DecisionCache.set_uuid()
        # --- 1. OpenAI ---
        if os.environ.get("OPENAI_API_KEY"):
            try:
                base_llm = OpenAiIntegrator()
                return Decision(base_llm)
            except ImportError as e:
                raise RuntimeError(
                    "OpenAI dependency missing. Install with: pip install openai"
                ) from e
            except Exception as e:
                raise RuntimeError(f"OpenAI initialization failed: {e}") from e

        # --- 2. Google Gemini ---
        elif os.environ.get("GOOGLE_API_KEY"):
            raise NotImplementedError(
                "Google Gemini support not implemented yet."
            )

        # --- 3. Anthropic Claude ---
        elif os.environ.get("ANTHROPIC_API_KEY"):
            raise NotImplementedError(
                "Anthropic support not implemented yet."
            )

        else:
            raise EnvironmentError(
                "No LLM API key found. Set OPENAI_API_KEY (or others)."
            )
    @staticmethod
    def set_uuid() -> None:
        DecisionCache._uuid = uuid.uuid4()