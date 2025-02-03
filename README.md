# Tested Agentic Chains

Tested Agentic Chains (TAC) combines the methodical approach of tested development with blockchain-inspired interlinking mechanisms, creating a robust framework where AI systems are developed and validated through continuous empirical testing while maintaining a secure, transparent record of their evolution and performance.

> **Warning** ⚠️  
> This project is in **alpha**. Interfaces, commands, and features may change without notice. Use at your own risk and carefully test before deploying in production environments.

## What Is It?

Tested Agentic Chains (TAC) extends the principles of continuous testing and auditing into AI development. By structuring tasks as "blocks" validated by a series of automated tests and recorded changes, you can iteratively refine your AI's behavior while maintaining a transparent trail of its evolution. For a detailed technical overview of the system architecture and methodology, please refer to our [whitepaper](docs/whitepaper.md).

## 🚀 Installation

1. **Clone this repository** (or download it) to your local machine:

   ```bash
   git clone git@github.com:lunarring/tac.git
   cd tac
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

### Create Blocks

Generate and execute new blocks for different purposes:

```bash
# Generate and execute a test-focused block
tac run --test ./your/code/directory

# Generate and execute a refactoring block
tac run --refactor ./your/code/directory

# Generate and execute an error analysis block
tac run --error ./your/code/directory

# Generate and execute a custom block with specific instructions
tac run --instructions "Add error handling to all functions" ./your/code/directory
```

Each block type focuses on a different aspect:
- `--test`: Creates a block focused on generating tests for the codebase
- `--refactor`: Creates a block for analyzing and improving code structure and quality
- `--error`: Creates a block for error analysis and handling improvements
- `--instructions`: Creates a block from custom task instructions

### View Blocks and Logs

View blocks and execution logs interactively:

```bash
tac view
```

This command provides an interactive interface to:
- Browse and inspect protoblocks with their versions and specifications
- View execution logs with test results and changes
- See block details including task specifications, test data, and file changes

### Test Management

The framework provides several test-related commands:

```bash
# Run tests
tac test run [--directory tests]

# List available tests
tac test list [--directory tests]

# Generate tests (coming soon)
tac test generate
```

### Gather Code Documentation

The gather command helps collect and document Python files in a directory:

```bash
tac gather ./src/tac
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
  tac:
    level: DEBUG
```
(Place config.yaml in the project root or update paths accordingly.)

## ✍️ Contributing

Since this project is alpha, contributions, suggestions, and bug reports are highly encouraged. Ideally get in touch with Johannes, as the project currently is in closed alpha stage.