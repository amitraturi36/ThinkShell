import json
import os


from openai import OpenAI

from llm.base_llm import BaseLLM
from llm.session import ThinkShellSession

class OpenAiIntegrator(BaseLLM):
    openai_session_key = "openai_response_id"
    RESPONSE_SCHEMA = {
        "format": {
            "type": "json_schema",
            "name": "agent_decision",
            "schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["INSPECT", "EXECUTE", "REVIEW", "ASK", "UPLOAD", "BLOCK"]
                    },
                    "commands": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "reason": {
                        "type": ["string", "null"]
                    }
                },
                "required": ["action", "commands", "reason"],
                "additionalProperties": False
            }
        }
    }

    def __init__(self):
        self.LLM_RESPONSE_ID = None
        key = self._get_openai_key()
        if key:
            self.client = OpenAI(api_key=key)
        else:
            self.client = OpenAI()

        self.session = ThinkShellSession()
        self.LLM_RESPONSE_ID = self.session.get("openai", "response_id")

    DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-nano")

    @staticmethod
    def _get_openai_key() -> str | None:
        # Support both env var names used in this repo.
        return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAIAPIKEY")

    def call_llm(self, event: str) -> dict:
        response = self.client.responses.create(
            model=self.DEFAULT_MODEL,
            previous_response_id=self.LLM_RESPONSE_ID,
            input=event,
            text=self.RESPONSE_SCHEMA,
            truncation="disabled"
        )
        self.LLM_RESPONSE_ID = response.id
        self._save_state()
        return json.loads(response.output_text)

    def load_state(self):
        self.LLM_RESPONSE_ID = self.session.get("openai", "response_id")

    def _save_state(self):
        self.session.set("openai", "response_id", self.LLM_RESPONSE_ID)

    def summarize_and_reset(self, system_prompt: str, os_info: dict[str, str]):
        summary_resp = self.client.responses.create(
            model=self.DEFAULT_MODEL,
            previous_response_id=self.LLM_RESPONSE_ID,
            input="Summarize the session so far for future continuation.",
        )
        summary_text = summary_resp.output_text
        # Start a fresh conversation WITH that summary
        new_resp = self.client.responses.create(
            model=self.DEFAULT_MODEL,
            instructions=system_prompt,
            input=f"SESSION SUMMARY: {summary_text}\nOS_INFO: {json.dumps(os_info)}"
        )

        self.LLM_RESPONSE_ID = new_resp.id
        self._save_state()

    def init_ai_terminal(self, system_prompt: str, os_info: dict[str, str]) -> None:
        if self.LLM_RESPONSE_ID:
            return
        response = self.client.responses.create(
            model=self.DEFAULT_MODEL,
            instructions=system_prompt,
            input=f"OS_INFO: {json.dumps(os_info)}"
        )

        self.LLM_RESPONSE_ID = response.id
        self._save_state()

    def upload_file_to_llm(self, path: str) -> str | None:
        try:
            with open(path, "rb") as f:
                # Using files.create as it is the standard way to upload files and get a file ID
                file_object = self.client.files.create(
                    file=f,
                    purpose="assistants"
                )
            return file_object.id
        except Exception as e:
            raise RuntimeError(f"Upload failed for {path}: {e}")
