from llm.decision_cache import DecisionCache


def get_bash_command(user_query: str) -> str:
    """
    Directly calls LLM APIs (OpenAI, Gemini, Anthropic) without LangChain.
    """
    decision = DecisionCache.get()
    if decision is None:
        raise RuntimeError(
            "Not able to initiate Thinkshell, setup is incomplete, please complete the setup and try again."
        )
    try:
        return decision.ai_terminal(user_query)
    except Exception as e:
        msg = str(e).replace('"', "'")
        return f'echo "[ThinkShell Error] {msg}." >&2'
