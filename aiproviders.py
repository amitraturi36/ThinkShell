# ----------------------------
# Config file helpers
# ----------------------------

PROVIDERS = {
    "openai": {
        "label": "OpenAI (GPT-4o/3.5)",
        "cfg_key": "openai_key",
        "env_key": "OPENAI_API_KEY",
    },
    "gemini": {
        "label": "Google Gemini",
        "cfg_key": "gemini_key",
        "env_key": "GOOGLE_API_KEY",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "cfg_key": "anthropic_key",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "none": {
        "label": "Skip (No AI)",
        "cfg_key": None,
        "env_key": None,
    },
}


def get_available_providers_from_config(cfg: dict):
    """Return list of providers that have keys present in config."""
    available = []
    for p, meta in PROVIDERS.items():
        if p == "none":
            continue
        k = (cfg.get(meta["cfg_key"]) or "").strip()
        if k:
            available.append(p)
    return available


# ----------------------------
# Provider selection flows
# ----------------------------

def provider_selection_menu(title: str = "ThinkShell AI Setup") -> str:
    """
    Interactive selection. Returns provider key: openai/gemini/anthropic/none.
    """
    print(f"\n🤖 \033[1m{title}\033[0m")
    print("--------------------------------")
    print("1. OpenAI (GPT-4o/3.5)")
    print("2. Google Gemini")
    print("3. Anthropic Claude")
    print("4. Skip (No AI)")
    print("--------------------------------")
    choice = input("Select Provider [1-4]: ").strip()

    mapping = {"1": "openai", "2": "gemini", "3": "anthropic", "4": "none"}
    provider = mapping.get(choice)
    if not provider:
        print("Invalid choice. Defaulting to Skip (No AI).")
        provider = "none"
    return provider
