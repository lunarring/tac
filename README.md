# Test Chain

An Automated, Test-Driven AI Coding Framework

## Overview

Test Chain is a framework that automates the test-driven development process using AI. It takes a test-first approach where tests are generated before implementing the solution, ensuring robust and well-tested code.

## Usage

The framework provides two main commands: `block` and `gather`.

### Block Command

The block command helps create and test new code implementations based on a YAML specification.

1. Create a YAML file describing your coding task (e.g., `examples/laplace_filter.yaml`):

```yaml
project:
  project_dir: "./laplace_test"

block:
  function_name: "laplace_filter"
  file_path: "main.py"
  task_description: "Implement a Laplacian filter function that takes a numpy array image as input and returns the filtered image."
  test_specification: "Test the laplace_filter function with various inputs including zero arrays, simple patterns, and edge cases."
  test_data_generation: |
    import numpy as np
    test_cases = [
      (np.zeros((3, 3)), np.zeros((3, 3))),
      (np.eye(3), np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]])),
      (np.ones((4, 4)), np.zeros((4, 4)))
    ]
```

2. Run the test chain:

```bash
python -m test_chain.cli.main block examples/laplace_filter.yaml
```

### Gather Command

The gather command helps collect and document Python files in a directory:

```bash
python -m test_chain.cli.main gather ./src/test_chain
```

Example output from gather:
```
## File: src/test_chain/core/block.py
Contains core Block class implementation...

---
## File: src/test_chain/agents/base.py
Base agent interface definition...
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
