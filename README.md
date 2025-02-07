# Tested Agentic Chains

Tested Agentic Chains (TAC) combines the methodical approach of tested development with blockchain-inspired interlinking mechanisms, creating a robust framework where AI systems are developed and validated through continuous empirical testing. 

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
4. Be sure you have a valid API key for OpenAI in your system that can be retrieved by `os.getenv('OPENAI_API_KEY')`
## ⚙️ Usage

The framework provides several commands to help with AI-driven development:

### Create and Execute Tasks
TAC assumes that you have a clean git repository in the location from where you run it and you are in your project root directory.

Execute tasks including automated testing using a simple command:

```bash
# Execute a task with specific instructions
tac make "your instructions here"

# Examples:
tac make "add error handling to function parse_config"
tac make "create a test for the parse_config"
tac make "refactor the duplicate code in utils"

# Optional: Specify a different directory (default is current directory)
tac make "your instructions" --dir ./your/code/directory

# Optional: Load from a JSON protoblock file
tac make --json path/to/protoblock.json

# Optional: Disable git operations
tac make "your instructions" --no-git
```
### Voice Interface (Experimental)

TAC now includes an experimental voice interface that allows you to interact with the system using speech:

```bash
tac voice
```

The voice interface allows you to:
- Speak your task instructions naturally
- Get audio feedback from the AI assistant
- Execute the same operations as the text-based interface
- Maintain a conversational flow while coding (coming soon)

> **Note**: The voice interface is currently experimental and may require additional setup for speech recognition and synthesis.

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
