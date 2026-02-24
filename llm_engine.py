import os

from llm import Decision
from llm.Decision import Decision
from llm.openaiintegrator import OpenAiIntegrator


_decision_instance = None


def get_bash_command(user_query: str) -> str:
    """
    Directly calls LLM APIs (OpenAI, Gemini, Anthropic) without LangChain.
    """
    decision = _get_or_create_decision()
    try:
        return decision.ai_terminal(user_query)
    except Exception as e :
        print(f"echo 'Sorry for the inconvenience Thinkshell broke with Error: {e}'")

def _get_or_create_decision() -> Decision:
    """
    Lazy initialization to avoid reloading LLM client each call.
    """
    global _decision_instance

    if _decision_instance is None:
        _decision_instance = _setup_environment()

    return _decision_instance


def _setup_environment() -> Decision:
    """
    Detects available provider and initializes Decision engine.
    Raises clear errors instead of returning shell strings.
    """

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
