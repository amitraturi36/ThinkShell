import os


def get_bash_command(user_query):
    """
    Directly calls LLM APIs (OpenAI, Gemini, Anthropic) without LangChain.
    """

    system_prompt = """
    You are a Linux/Mac Bash Agent.
    Convert the user's request into a single, valid executable command.
    RULES:
    - Output ONLY the command. No markdown, no quotes, no explanations.
    - If request is 'list files', output: ls -la
    - If dangerous, output: echo "Action blocked"
    """

    # --- 1. OpenAI ---
    if os.environ.get("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            client = OpenAI() # Uses env var OPENAI_API_KEY automatically

            response = client.chat.completions.create(
                model="gpt-4o", # or gpt-3.5-turbo
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0
            )
            return response.choices[0].message.content.strip()
        except ImportError:
            return "echo ' Error: pip install openai'"
        except Exception as e:
            return f"echo ' OpenAI Error: {str(e)}'"

    # --- 2. Google Gemini ---
    elif os.environ.get("GOOGLE_API_KEY"):
        try:
            import google.generativeai as genai

            genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
            model = genai.GenerativeModel('gemini-pro')

            # Gemini doesn't have system prompts in the same way, so we append context
            full_prompt = f"{system_prompt}\nUser Request: {user_query}"

            response = model.generate_content(full_prompt)
            return response.text.strip()
        except ImportError:
            return "echo ' Error: pip install google-generativeai'"
        except Exception as e:
            return f"echo ' Gemini Error: {str(e)}'"

    # --- 3. Anthropic Claude ---
    elif os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic() # Uses env var ANTHROPIC_API_KEY

            response = client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_query}
                ]
            )
            return response.content[0].text.strip()
        except ImportError:
            return "echo ' Error: pip install anthropic'"
        except Exception as e:
            return f"echo ' Anthropic Error: {str(e)}'"

    else:
        return "echo ' No API Key found. Run with --openai_key etc.'"
