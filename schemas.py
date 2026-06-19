from typing import TypedDict, Optional
from pydantic import BaseModel, Field


class GraphState(TypedDict):
    # Set once by GetQueryDetails
    query_name: str
    query_text: str
    data_file_descriptions: str
    validate_module_path: str
    validate_function_name: str
    # Updated each attempt
    current_program: str
    attempt: int
    last_success: bool
    last_output: Optional[dict]
    last_error: str
    last_reflection: str


class GeneratedProgram(BaseModel):
    """Structured response for code-generation LLM calls."""
    code: str = Field(description="A complete, runnable Python program.")
