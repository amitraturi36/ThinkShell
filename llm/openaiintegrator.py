import json
import os

from openai import OpenAI

from llm.base_llm import BaseLLM


class OpenAiIntegrator(BaseLLM):
    LLM_RESPONSE_ID = None
    RESPONSE_SCHEMA = {
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
    def __init__(self):
        key = self._get_openai_key()
        if key:
            self.client = OpenAI(api_key=key)
        else:
            self.client = OpenAI()


    DEFAULT_MODEL =  os.environ.get("OPENAI_MODEL", "gpt-5-nano")

    @staticmethod
    def _get_openai_key() -> str | None:
        # Support both env var names used in this repo.
        return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAIAPIKEY")

    def call_llm(self, event: str) -> dict:
        response = self.client.responses.create(
            model=self.DEFAULT_MODEL,
            previous_response_id=self.LLM_RESPONSE_ID,
            input=event,
            reasoning={"effort": "minimal"},
            text={"format": self.RESPONSE_SCHEMA}
        )

        self.LLM_RESPONSE_ID = response.id
        return json.loads(response.output_text)

    def summarize_and_reset(self,system_prompt:str,os_info:dict[str, str]):
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
            input=f"SESSION SUMMARY: {summary_text}\nOperating System: {json.dumps(os_info)}"
        )

        self.LLM_RESPONSE_ID = new_resp.id

    def init_ai_terminal(self,system_prompt:str,os_info:dict[str, str]) -> None:
        response = self.client.responses.create(
            model=self.DEFAULT_MODEL,
            instructions=system_prompt,
            input=f"OS_INFO: {json.dumps(os_info)}"
        )

        self.LLM_RESPONSE_ID = response.id
