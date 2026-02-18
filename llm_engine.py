import os

from llm.openaiintegrator import OpenAiIntegrator

# Initialize globally to maintain conversation history
openai_integrator = OpenAiIntegrator()

def get_bash_command(user_query):
    """
    Directly calls LLM APIs (OpenAI, Gemini, Anthropic) without LangChain.
    """
    # --- 1. OpenAI ---
    if os.environ.get("OPENAI_API_KEY"):
        try:
            return openai_integrator.ai_terminal(user_query)
        except ImportError:
            return "echo ' Error: pip install openai'"
        except Exception as e:
            return f"echo ' OpenAI Error: {str(e)}'"

    # --- 2. Google Gemini ---
    elif os.environ.get("GOOGLE_API_KEY"):
        try:
            return "echo 'Google support pending upgrade...'"
        except ImportError:
            return "echo ' Error: pip install google-generativeai'"
        except Exception as e:
            return f"echo ' Gemini Error: {str(e)}'"

    # --- 3. Anthropic Claude ---
    elif os.environ.get("ANTHROPIC_API_KEY"):
        return "echo 'Anthropic support pending upgrade...'"

    else:
        return "echo 'No API Key found.'"
