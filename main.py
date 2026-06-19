# Name: Noam Kyram
# ID: 322568718
# Email: noam.kyram@post.runi.ac.il
#
# Name: Ron Isakov
# ID: 212195432
# Email: ron.isakov@post.runi.ac.il


import json
import os
import importlib.util

from langgraph.graph import StateGraph, END
from openai import BadRequestError

from schemas import GraphState
from oai_client import llm, generate_program
from utils import parse_query_input, run_pq, PQ_TIMEOUT_SECONDS
from prompts import load_prompt

CONTENT_FILTER_PREFIX = "[CONTENT_FILTER] "


# ---- Node 1: GetQueryDetails ----
def get_query_details(state: GraphState) -> GraphState:
    print("** Entering GetQueryDetails Tool **")

    query_name, data_files = parse_query_input("query_input.txt")

    # Read the query text
    with open(f"{query_name}.txt", "r", encoding="utf-8") as f:
        query_text = f.read().strip()

    # Build data file descriptions string
    descriptions = ""
    for filename, desc in data_files:
        descriptions += f"File: {filename}\n{desc}\n\n"

    # Derive validation file and function names
    validate_module_path = query_name.replace("-", "_") + "_validate.py"
    validate_function_name = query_name.replace("-", "_") + "_answer"

    return {
        "query_name": query_name,
        "query_text": query_text,
        "data_file_descriptions": descriptions.strip(),
        "validate_module_path": validate_module_path,
        "validate_function_name": validate_function_name,
        "current_program": "",
        "attempt": 0,
        "last_success": False,
        "last_output": None,
        "last_error": "",
        "last_reflection": "",
    }


# ---- Node 2: GenQueryProgram ----
def gen_query_program(state: GraphState) -> GraphState:
    print("** Entering GenQueryProgram Tool **")

    prompt = load_prompt("gen_program").format(
        query_text=state["query_text"],
        data_file_descriptions=state["data_file_descriptions"],
    )

    try:
        program = generate_program(prompt)
    except BadRequestError as e:
        return {
            **state,
            "current_program": "",
            "attempt": 1,
            "last_success": False,
            "last_output": None,
            "last_error": f"{CONTENT_FILTER_PREFIX}GenQueryProgram blocked: {e}",
            "last_reflection": "",
        }

    return {
        **state,
        "current_program": program,
        "attempt": 1,
    }


# ---- Node 3: ExecuteProgram ----
def execute_program(state: GraphState) -> GraphState:
    print("** Entering ExecuteProgram Tool **")

    # If gen/regen was blocked by the content filter, there's no fresh program to run.
    # Pass the failure through so routing sends us to ReflectOnErr.
    if state.get("last_error", "").startswith(CONTENT_FILTER_PREFIX):
        return state

    query_name = state["query_name"]
    program_path = f"{query_name}.py"

    # Write the current program to file
    with open(program_path, "w", encoding="utf-8") as f:
        f.write(state["current_program"])

    # Run PQ as subprocess
    stdout, stderr, returncode = run_pq(program_path)

    # Check for timeout
    if returncode is None:
        return {
            **state,
            "last_success": False,
            "last_output": None,
            "last_error": f"PQ timed out after {PQ_TIMEOUT_SECONDS} seconds — likely an infinite loop or extremely inefficient code.",
        }

    # Check for runtime errors
    if returncode != 0:
        return {
            **state,
            "last_success": False,
            "last_output": None,
            "last_error": f"Runtime error (exit code {returncode}):\n{stderr.strip()}",
        }

    # Check for empty output
    if not stdout.strip():
        return {
            **state,
            "last_success": False,
            "last_output": None,
            "last_error": "Program produced no output. Expected a JSON object printed to stdout.",
        }

    # Try to parse JSON
    try:
        answer_dict = json.loads(stdout.strip())
    except json.JSONDecodeError as e:
        return {
            **state,
            "last_success": False,
            "last_output": None,
            "last_error": f"Program output is not valid JSON:\n{stdout.strip()}\nError: {e}",
        }

    # Output must be a JSON object (dict), not a list/string/number/null
    if not isinstance(answer_dict, dict):
        return {
            **state,
            "last_success": False,
            "last_output": None,
            "last_error": (
                f"Program output is valid JSON but is not a JSON object (got {type(answer_dict).__name__}). "
                f"Expected a dict with the fields specified in the query.\nProduced: {stdout.strip()}"
            ),
        }

    # Reject empty dict {}
    if len(answer_dict) == 0:
        return {
            **state,
            "last_success": False,
            "last_output": None,
            "last_error": "Program output is an empty JSON object ({}). Expected a dict with the fields specified in the query.",
        }

    # Run validation function
    try:
        module_name = query_name.replace("-", "_") + "_validate"
        function_name = query_name.replace("-", "_") + "_answer"
        file_path = f"{module_name}.py"

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        validate_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validate_module)
        validate_fn = getattr(validate_module, function_name)

        is_correct = validate_fn(answer_dict)
    except Exception as e:
        return {
            **state,
            "last_success": False,
            "last_output": answer_dict,
            "last_error": f"Validation function raised an exception:\n{e}",
        }

    if is_correct:
        return {
            **state,
            "last_success": True,
            "last_output": answer_dict,
            "last_error": "",
        }
    else:
        return {
            **state,
            "last_success": False,
            "last_output": answer_dict,
            "last_error": f"Validation failed: program ran successfully but produced incorrect answer.\nProduced: {json.dumps(answer_dict)}",
        }


# ---- Node 4: Chk4rErr ----
def chk4r_err(state: GraphState) -> GraphState:
    print("** Entering Chk4rErr Tool **")
    return state


def route_after_check(state: GraphState) -> str:
    if state["last_success"]:
        return "finalize"
    if state["attempt"] >= 5:
        return "finalize"
    return "retry"


# ---- Node 5: ReflectOnErr ----
def reflect_on_err(state: GraphState) -> GraphState:
    print("** Entering ReflectOnErr Tool **")

    prompt = load_prompt("reflect").format(
        query_text=state["query_text"],
        data_file_descriptions=state["data_file_descriptions"],
        current_program=state["current_program"],
        last_error=state["last_error"],
    )

    try:
        response = llm.invoke([
            {"role": "system", "content": "You are an expert Python programmer and debugger."},
            {"role": "user", "content": prompt}
        ])
        reflection = response.content
    except BadRequestError:
        reflection = (
            "The previous LLM call was blocked by Azure OpenAI's content filter. "
            "For the next regeneration, rephrase the task using strictly neutral, technical "
            "CSV/pandas terminology. Refer to the data only via column names and computations; "
            "avoid any wording from the original query that could resemble sensitive subject matter."
        )

    return {
        **state,
        "last_reflection": reflection,
    }


# ---- Node 6: ReGenQueryPgm ----
def regen_query_pgm(state: GraphState) -> GraphState:
    print("** Entering ReGenQueryPgm Tool **")

    prompt = load_prompt("regen_program").format(
        query_text=state["query_text"],
        data_file_descriptions=state["data_file_descriptions"],
        current_program=state["current_program"],
        last_error=state["last_error"],
        last_reflection=state["last_reflection"],
    )

    try:
        program = generate_program(prompt, system="You are an expert Python programmer and debugger.")
    except BadRequestError as e:
        return {
            **state,
            "attempt": state["attempt"] + 1,
            "last_success": False,
            "last_output": None,
            "last_error": f"{CONTENT_FILTER_PREFIX}ReGenQueryPgm blocked: {e}",
        }

    return {
        **state,
        "current_program": program,
        "attempt": state["attempt"] + 1,
    }


# ---- Node 7: Finalize ----
def finalize(state: GraphState) -> GraphState:
    print("** Entering Finalize Tool **")

    query_name = state["query_name"]

    # 1. Write the last program (always)
    with open(f"{query_name}.py", "w", encoding="utf-8") as f:
        f.write(state["current_program"])

    if state["last_success"]:
        # 2. Write answer
        answer_json = json.dumps(state["last_output"])
        with open(f"{query_name}_answer.txt", "w", encoding="utf-8") as f:
            f.write(answer_json)
        # 3. Empty errors
        with open(f"{query_name}_errors.txt", "w", encoding="utf-8") as f:
            pass
        # 4. Empty reflection
        with open(f"{query_name}_reflect.txt", "w", encoding="utf-8") as f:
            pass
        # Print answer to console
        print(f"Successfully generated program that computed solution. Solution in {query_name}_answer.txt")
        print(f"Answer is {answer_json}")
    else:
        # 2. Empty answer
        with open(f"{query_name}_answer.txt", "w", encoding="utf-8") as f:
            pass
        # 3. Write last error
        with open(f"{query_name}_errors.txt", "w", encoding="utf-8") as f:
            f.write(state["last_error"])
        # 4. Write last reflection
        with open(f"{query_name}_reflect.txt", "w", encoding="utf-8") as f:
            f.write(state["last_reflection"])
        # Print failure to console
        print(f"Failed to generate correct program after {state['attempt']} attempts.")

    return state


# ---- Build the Graph ----
graph = StateGraph(GraphState)

graph.add_node("GetQueryDetails", get_query_details)
graph.add_node("GenQueryProgram", gen_query_program)
graph.add_node("ExecuteProgram", execute_program)
graph.add_node("Chk4rErr", chk4r_err)
graph.add_node("ReflectOnErr", reflect_on_err)
graph.add_node("ReGenQueryPgm", regen_query_pgm)
graph.add_node("Finalize", finalize)

graph.set_entry_point("GetQueryDetails")
graph.add_edge("GetQueryDetails", "GenQueryProgram")
graph.add_edge("GenQueryProgram", "ExecuteProgram")
graph.add_edge("ExecuteProgram", "Chk4rErr")
graph.add_conditional_edges("Chk4rErr", route_after_check, {
    "retry": "ReflectOnErr",
    "finalize": "Finalize",
})
graph.add_edge("ReflectOnErr", "ReGenQueryPgm")
graph.add_edge("ReGenQueryPgm", "ExecuteProgram")
graph.add_edge("Finalize", END)

app = graph.compile()

# ---- Run ----
app.invoke({"attempt": 0})
