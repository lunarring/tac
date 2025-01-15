# Test Chain

An Automated, Test-Driven AI Coding Framework

## Overview

Test Chain is a framework that automates the test-driven development process using AI. It takes a test-first approach where tests are generated before implementing the solution, ensuring robust and well-tested code.

## Installation

```bash
pip install -e .
```

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

## Usage

1. Create a YAML file describing your coding task:

```yaml
project:
  project_dir: "./my_project"

block:
  function_name: "caesar_cipher"
  file_path: "cipher.py"
  task_description: "Implement a Caesar cipher encryption function that takes a text string and shift value as input."
  test_specification: "Test the caesar_cipher function with various inputs including empty string, single character, multiple words, and different shift values."
  test_data_generation: |
    test_cases = [
      ("hello", 3, "khoor"),
      ("xyz", 1, "yza"),
      ("", 5, ""),
      ("Hello, World!", 1, "Ifmmp, Xpsme!")
    ]
```

2. Run the test chain:

```bash
test-chain examples/caesar_cipher.yaml
```

Additional options:
- `--dry-run`: Validate the YAML file without executing
- `--skip-tests`: Skip running tests after implementation
- `--test-only`: Only run the tests without implementing

## How it Works

1. The framework reads a block definition from a YAML file
2. It generates tests based on the test specification
3. An AI agent (currently using Aider) implements the solution
4. Tests are run to verify the implementation
5. If tests fail, the process retries with a new implementation

## Configuration

The framework uses a configuration file (`src/test_chain/core/config.yaml`) to control various aspects:

```yaml
agents:
  programming:
    type: aider
    max_retries: 3
```

## License

MIT License
