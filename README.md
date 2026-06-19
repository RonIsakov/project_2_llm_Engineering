# LLM Program Generator & Self-Repair Loop

> Turn a plain-English data question into a working pandas program — and let an LLM debug it for you.

## Overview

This project takes a natural-language query over a set of CSV files and asks an LLM
(Azure OpenAI `gpt-4.1-mini`) to write a Python program that answers it. The program is
executed in a subprocess, its JSON output is validated, and if anything goes wrong the
LLM **reflects** on the error and **regenerates** a corrected program. The whole loop is
orchestrated as a [LangGraph](https://langchain-ai.github.io/langgraph/) state machine
and retries up to five times before giving up.

## Features

- **Natural language → code** — generates a runnable pandas program from a query.
- **Self-repair loop** — on failure, reflects on the error and regenerates (up to 5 attempts).
- **Two-stage validation** — checks the output is a non-empty JSON object, then runs a
  user-supplied validation function to confirm the answer is correct.
- **Safe execution** — each generated program runs as a subprocess with a 60-second timeout.
- **Structured output** — code is returned through a Pydantic schema, not free-form text.
- **Graph orchestration** — the flow is an explicit 7-node LangGraph `StateGraph`.

## Tech Stack

- **Python**
- **LangGraph** `0.2.55` — state-machine orchestration
- **LangChain (Azure OpenAI)** `langchain-openai 0.2.0` + **openai** `1.51.0` — LLM access (`gpt-4.1-mini`)
- **Pydantic** — structured LLM output
- **pandas** `2.2.0` — data processing inside generated programs

## Project Structure

```
hw_2/
├── main.py             # LangGraph state machine: the generate → run → validate → reflect loop
├── oai_client.py       # Azure OpenAI client + generate_program() helper
├── schemas.py          # GraphState (TypedDict) and GeneratedProgram (Pydantic) schemas
├── utils.py            # parse_query_input() and run_pq() subprocess runner (60s timeout)
├── prompts/            # Prompt templates loaded by load_prompt()
│   ├── gen_program.txt   #   initial code generation
│   ├── reflect.txt       #   error analysis
│   └── regen_program.txt #   code regeneration
├── requirements.txt
└── top-spender.*       # Worked example (generated program, answer, logs)
```

## Installation

Run from inside the `hw_2/` directory:

```bash
pip install -r requirements.txt
```

## Configuration

The Azure OpenAI connection is read from environment variables (loaded from a `.env`
file via [python-dotenv](https://pypi.org/project/python-dotenv/)). Copy the template and
fill in your own values:

```bash
cp .env.example .env
```

```env
AZURE_OPENAI_API_KEY=your-azure-openai-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-08-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
```

`AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT` are required; the version and
deployment fall back to sensible defaults if omitted.


## Usage

The tool reads its task from a small set of input files in the working directory. For a
query named `<query_name>` you provide:

1. **`query_input.txt`** — the query name and the data files with descriptions:

   ```
   query_name: top-spender
   data_file: customers.csv
   Columns: CustomerID, FirstName, LastName, City
   data_file: orders.csv
   Columns: CustomerID, ProductID, Quantity, Status
   data_file: products.csv
   Columns: ProductID, Price
   ```

2. **`<query_name>.txt`** — the natural-language query, e.g.
   *"Find the customer who spent the most on delivered orders."*

3. **`<query_name>_validate.py`** — a validation function named `<query_name>_answer`
   (dashes become underscores) that returns `True` for a correct answer:

   ```python
   def top_spender_answer(answer_dict) -> bool:
       return answer_dict.get("LastName") == "Levi"
   ```

4. The **CSV data files** referenced in `query_input.txt`.

Then run:

```bash
python main.py
```

### Outputs

When it finishes, the following files are written for `<query_name>`:

| File | Contents |
| --- | --- |
| `<query_name>.py` | The last program the LLM generated |
| `<query_name>_answer.txt` | The final JSON answer (empty on failure) |
| `<query_name>_errors.txt` | The last error (empty on success) |
| `<query_name>_reflect.txt` | The last reflection notes (empty on success) |

### Example

The included `top-spender` example produces:

```json
{"FirstName": "Oren", "LastName": "Levi", "City": "Haifa", "TotalSpent": 572.47}
```

## How It Works

The graph runs the following nodes, looping on failure until the answer validates or the
attempt limit (5) is reached:

```
GetQueryDetails → GenQueryProgram → ExecuteProgram → Chk4rErr
                                         ▲                │
                                         │           success / limit
                                         │                ▼
                            ReGenQueryPgm ← ReflectOnErr   Finalize
                                         (retry on failure)
```

1. **GetQueryDetails** — parse `query_input.txt` and read the query text.
2. **GenQueryProgram** — ask the LLM to write the first program.
3. **ExecuteProgram** — run it, then validate output shape and correctness.
4. **Chk4rErr** — route to `Finalize` on success or after 5 attempts, otherwise retry.
5. **ReflectOnErr** — ask the LLM what went wrong.
6. **ReGenQueryPgm** — regenerate a fixed program using the error + reflection.
7. **Finalize** — write the program, answer, error, and reflection files.
