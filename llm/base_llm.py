from abc import ABC, abstractmethod


class BaseLLM(ABC):
    def __init__(self):
        self.LLM_RESPONSE_ID = None

    @abstractmethod
    def call_llm(self, event: str) -> dict:
        pass

    @abstractmethod
    def summarize_and_reset(self,system_prompt:str,os_info:dict[str, str]):
        pass

    @abstractmethod
    def init_ai_terminal(self, system_prompt: str, os_info: dict[str, str]) -> None:
        pass

    @abstractmethod
    def load_state(self)->None:
        pass

    @abstractmethod
    def upload_file_to_llm(self, path: str)-> str | None:
        pass
