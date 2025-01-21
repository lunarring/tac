# Test-driven Agentic Chains

Test-driven Agentic Chains (TDAC) combines the methodical approach of test-driven development with blockchain-inspired interlinking mechanisms, creating a robust framework where AI systems are developed and validated through continuous empirical testing while maintaining a secure, transparent record of their evolution and performance.

> **Warning** ⚠️  
> This project is in **alpha**. Interfaces, commands, and features may change without notice. Use at your own risk and carefully test before deploying in production environments.

## What Is It?

Test-driven Agentic Chains (TDAC) extends the principles of continuous testing and auditing into AI development. By structuring tasks as "blocks" validated by a series of automated tests and recorded changes, you can iteratively refine your AI's behavior while maintaining a transparent trail of its evolution. For a detailed technical overview of the system architecture and methodology, please refer to our [whitepaper](docs/whitepaper.md).

## 🚀 Installation

1. **Clone this repository** (or download it) to your local machine:

   ```bash
   git clone git@github.com:lunarring/tdac.git
   cd tdac
   ```

2. Activate your environment (e.g., mine is called 'good'):
   ```bash
   conda activate good
   ```

3. Install via pyproject.toml—either in editable mode for development or standard mode for production:

   Editable (development) mode:
   ```bash
   pip install -e .
   ```

After this, you can run the command from anywhere in your terminal (as long as your environment is activated).

## ⚙️ Usage

The framework provides several commands to help with AI-driven development:

### Generate a Seedblock

Generate a seedblock JSON template from an existing codebase:

```bash
tdac seedblock ./your/code/directory
```

The seedblock command supports several template types:
- `--refactor`: Generate a template focused on code refactoring
- `--test`: Generate a template for adding comprehensive tests
- `--error`: Generate a template for error analysis and fixes
- `--execute`: Process through LLM and execute the seedblock

Examples:
```bash
# Replace DIRECTORY with your target code directory
tdac seedblock --refactor DIRECTORY
tdac seedblock --test DIRECTORY
tdac seedblock --error DIRECTORY
tdac seedblock DIRECTORY  # default template
tdac seedblock --refactor --execute DIRECTORY  # generate and execute
```

### Execute Changes

Execute changes based on a JSON specification:

```bash
tdac json your_protoblock.json
```

The json command supports several flags:
- `--gen-tests`: Only generate the tests without executing the task
- `--gen-task`: Only execute the task without generating tests
- `--run-tests`: Only run the tests without generating tests or executing task

Example protoblock JSON structure:
```json
{
    "seedblock": {
        "instructions": "Add feature X to the system"
    },
    "task": {
        "specification": "Detailed description of what needs to be implemented"
    },
    "test": {
        "specification": "Description of how the new functionality should be tested",
        "data": "Test input data and expected outcomes",
        "replacements": []
    },
    "write_files": [
        "src/module/new_feature.py"
    ],
    "context_files": [
        "src/module/existing.py"
    ],
    "commit_message": "TDAC: Add feature X implementation"
}
```

### Test Management

The framework provides several test-related commands:

```bash
# Run tests
tdac test run [--directory tests]

# List available tests
tdac test list [--directory tests]

# Generate tests (coming soon)
tdac test generate
```

### Gather Code Documentation

The gather command helps collect and document Python files in a directory:

```bash
tdac gather ./src/tdac
```

#### Command Options

- `--header`: Header format for each file (default: "## File: ")
- `--separator`: Separator between sections (default: "\n---\n")
- `--code-fences`: Use code fences in output
- `--exclusions`: Comma-separated directories to exclude (default: .git,__pycache__)

## ⚙️ Configuration

The framework uses a configuration file (`config.yaml`) to control various aspects:

```yaml
logging:
  tdac:
    level: DEBUG
```
(Place config.yaml in the project root or update paths accordingly.)

## ✍️ Contributing

Since this project is alpha, contributions, suggestions, and bug reports are highly encouraged. Ideally get in touch with Johannes, as the project currently is in closed alpha stage.
