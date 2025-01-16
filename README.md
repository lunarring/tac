# Test Chain

An Automated, Test-Driven AI Coding Framework

## Overview

Test Chain is a framework that automates the test-driven development process using AI. It takes a test-first approach where tests are generated before implementing the solution, ensuring robust and well-tested code.

## Usage

The framework provides two main commands: `block` and `gather`.

### Block Command

The block command helps create and test new code implementations based on a YAML specification.

1. Create a YAML file describing your coding task (e.g., `examples/caesar_cipher.yaml`):

```yaml
project:
  project_dir: "./block_test"

block:
  function_name: "caesar_cipher"
  file_path: "main.py"
  task_description: "Implement a Python function caesar_cipher(text, shift) that returns a new string where each alphabetic character in 'text' is shifted by 'shift' positions in the alphabet."
  test_specification: |
    Test cases include:
    1) Simple shift: 'abc' with shift=1 => 'bcd'
    2) Wraparound: 'xyz' with shift=2 => 'zab'
    3) Mixed case: 'AbZ' with shift=1 => 'BcA'
    4) Non-alpha: 'Hello, World!' with shift=5 => 'Mjqqt, Btwqi!'
```

2. Run the test chain:

```bash
python src/test_chain/cli/main.py block examples/caesar_cipher.yaml
```

### Gather Command

The gather command helps collect and document Python files in a directory. This is particularly useful for copying the entire file structure to a powerful O(1)-like model:

```bash
python src/test_chain/cli/main.py gather ./src/test_chain
```

### Command Options

Block command options:
- `--dry-run`: Validate the YAML file without executing
- `--skip-tests`: Skip running tests after implementation
- `--test-only`: Only run the tests without implementing

Gather command options:
- `--header`: Header format for each file (default: "## File: ")
- `--separator`: Separator between sections (default: "\n---\n")
- `--code-fences`: Use code fences in output
- `--exclusions`: Comma-separated directories to exclude (default: .git,__pycache__)

## Project Structure

```
test_chain/
├── src/
│   └── test_chain/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── block.py
│       │   ├── executor.py
│       │   └── config.yaml
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── aider_agent.py
│       └── cli/
│           ├── __init__.py
│           └── main.py
├── tests/
│   ├── __init__.py
│   ├── test_block.py
│   ├── test_executor.py
│   └── test_agents.py
├── examples/
│   └── caesar_cipher.yaml
├── pyproject.toml
├── setup.cfg
├── README.md
└── requirements.txt
```

## Configuration

The framework uses a configuration file (`config.yaml`) to control various aspects:

```yaml
agents:
  programming:
    type: aider
    max_retries: 3
```
