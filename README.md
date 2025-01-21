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

### Create Blocks

Generate and execute new blocks for different purposes:

```bash
# Generate and execute a test-focused block
tdac block --test ./your/code/directory

# Generate and execute a refactoring block
tdac block --refactor ./your/code/directory

# Generate and execute an error analysis block
tdac block --error ./your/code/directory

# Generate and execute a custom block with specific instructions
tdac block --instructions "Add error handling to all functions" ./your/code/directory
```

Each block type focuses on a different aspect:
- `--test`: Creates a block focused on generating tests for the codebase
- `--refactor`: Creates a block for analyzing and improving code structure and quality
- `--error`: Creates a block for error analysis and handling improvements
- `--instructions`: Creates a block from custom task instructions

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

### View Logs

View execution logs interactively:

```bash
tdac log
```

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
