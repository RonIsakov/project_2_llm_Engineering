import os
from typing import Optional

from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from schemas import GeneratedProgram

# Load variables from a local .env file (see .env.example).
load_dotenv()

DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
API_KEY = os.getenv("AZURE_OPENAI_API_KEY")

if not API_KEY or not ENDPOINT:
    raise RuntimeError(
        "Missing Azure OpenAI configuration. Copy .env.example to .env and set "
        "AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT."
    )

llm = AzureChatOpenAI(
    azure_deployment=DEPLOYMENT_NAME,
    azure_endpoint=ENDPOINT,
    api_version=API_VERSION,
    api_key=API_KEY,
    temperature=0,
)

_program_llm = llm.with_structured_output(GeneratedProgram)


def generate_program(prompt: str, system: Optional[str] = None) -> str:
    """Invoke the LLM with structured output; returns the program source."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    result: GeneratedProgram = _program_llm.invoke(messages)
    return result.code.strip()
