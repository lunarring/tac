# Trusty Agentic Chains

Trusty Agentic Chains (tac) is a AI-driven coding framework that combines coding agents with empirical verifications (trusty agents). The empirical verifications could for instance take the form of unit tests or simulated runs of the software. The coding agents implement desired changes in a codebase and the trusty agents verify them, yielding a *block* that can be merged into the codebase. Think of it as blockchain for code changes, but actually useful. For a detailed technical overview of the system architecture and methodology, please refer to our [whitepaper](docs/whitepaper.md).

> **Warning** ⚠️  
> This project is in **alpha**. Interfaces, commands, and features may change without notice. Use at your own risk and carefully test before deploying in production environments. 

## 🏗️ Architecture
tac operates through a chain of specialized agents working together:

### Coding Agents
These agents generate and modify code based on your instructions:
- **Aider Agent**: Leverages the aider-chat library for code generation [https://aider.chat/]
- **Native Agent**: Our lightweight in-house implementation for code generation

### Trusty Agents
These agents validate and verify the code changes:
- **Pytest Agent**: Runs software tests and analyzes results to ensure functionality
- **Plausibility Agent**: Evaluates if code changes match the requested functionality
- **Performance Agent**: Benchmarks code and guides performance optimization

The system creates *protoblocks* (specifications for changes and trusty measures) that are to be executed by coding agents and validated by trusty agents before being committed as finalized *blocks* in your codebase. A given task is automatically parcellated into smaller blocks by the orchestrator and executed.

## 🚀 Installation

1. **Clone this repository** (or download it) to your local machine:

   ```bash
   git clone git@github.com:lunarring/tac.git
   cd tac
   ```

2. Activate your environment (e.g. conda):
   ```bash
   conda activate your_env_name
   ```

3. Install via pyproject.toml

   ```bash
   pip install -e .
   ```
   
4. Make sure you have a valid API key for OpenAI in your environment:
   ```bash
   export OPENAI_API_KEY=your_key_here
   ```
   Or add it to your .env file if you prefer

## ⚙️ Usage

Usually, you are running tac from your terminal and are within your project root. You need git to run tac fully, as the plausibility trusty agent requires git diffs. 

### Create and Execute Tasks

Execute tasks including automated testing using a simple command:

```bash
# Execute a task with specific instructions
tac make "your instructions here"

# Examples:
tac make "refactor this spaghetti code into something a human might understand"

# Optional: Specify a different directory (default is current directory)
tac make "your instructions" --dir ./your/code/directory

# Optional: Load from a JSON protoblock file
tac make --json path/to/protoblock.json

# Optional: Choose a specific coding agent
tac make "your instructions" --agent native
```

### Selecting Agents

TAC allows you to choose which agents to use for your tasks:

```bash
# Use the native coding agent
tac make "your task" --agent native

# Use the aider coding agent (default)
tac make "your task" --agent aider

# Disable plausibility testing
tac make "your task" --plausibility-test false

# Set minimum plausibility score
tac make "your task" --minimum-plausibility-score B
```

### Git Integration

TAC will create a new branch with an id (e.g., tac/buxfix/refactor_spaghetti_code) where it will commit all changes IF everything worked out. If not, you'll have to manually switch back to your previous branch. 

### Voice Interface (Experimental)

TAC now includes an experimental voice interface that allows you to interact with the system using speech:

```bash
tac voice
```

> **Note**: The voice interface is currently experimental and only works without the orchestrator. It may require additional setup for speech recognition and synthesis. 

### View Blocks and Logs

View blocks and execution logs interactively:

```bash
tac view
```

This command provides an interactive interface to:
- View execution logs with test results and changes
- Relive the glory (or horror) of your AI's coding journey

### Test Management

The framework provides several test-related commands:

```bash
# Run tests (because trust, but verify)
tac test run [--directory tests]

# List available tests
tac test list [--directory tests]

```

### Performance Optimization

Optimize specific functions in your codebase using the Performance Trusty Agent:

```bash
# Optimize a specific function
tac optimize function_name
```

### Code Summarization

TAC can analyze and summarize your codebase to help AI agents better understand it:

```bash
# Gather and summarize Python files
tac gather ./src/tac --summarize

# View file summaries
tac gather ./src/tac
```

## ⚙️ Configuration

The framework uses a built-in configuration system with sensible defaults that can be overridden via command-line arguments:

```bash
# Example: Override configuration values
tac make "your task" --plausibility-test false --max-retries 5
```

### Configuration System

TAC uses a hierarchical configuration system (in `src/tac/core/config.py`) with several categories:

- **GeneralConfig**: Core settings like agent type, orchestration, and testing parameters
  ```python
  agent_type: str = "native"           # Which coding agent to use
  use_orchestrator: bool = True        # Whether to use the task orchestrator
  plausibility_test: bool = True       # Enable/disable plausibility testing
  minimum_plausibility_score: str = "B" # Minimum grade for plausibility
  max_retries_block: int = 4           # Maximum retry attempts for blocks
  max_retries_protoblock: int = 4      # Maximum retry attempts for protoblocks
  ```

- **GitConfig**: Version control settings
  ```python
  enabled: bool = True                 # Enable/disable git integration
  auto_commit_if_success: bool = True  # Auto-commit successful changes
  auto_push_if_success: bool = True    # Auto-push successful changes
  ```

- **LLMConfig**: Language model settings for different strength levels
  ```python
  provider: str = "openai"             # LLM provider (openai, anthropic)
  model: str = "o3-mini"               # Model name
  ```

- **AiderConfig**: Settings specific to the Aider coding agent
  ```python
  model: str = "openai/o3-mini"        # Model used by Aider
  reasoning_effort: str = "high"       # Reasoning level for Aider
  ```

### Command-line Options

Key configuration options include:
- `--agent`: Choose between "aider" or "native" coding agents
- `--plausibility-test`: Enable/disable plausibility testing
- `--max-retries`: Maximum number of retry attempts
- `--git-enabled`: Enable/disable git integration
- `--model`: Specify the LLM model to use
- `--minimum-plausibility-score`: Set the minimum grade (A-F) for plausibility tests
- `--use-orchestrator`: Enable/disable the task orchestrator
- `--reasoning-effort`: Set reasoning effort level (low, medium, high)

All configuration options are documented in the command help:
```bash
tac --help
```

sk" --model gpt-4
```

## ✍️ Contributing

Since this project is alpha, contributions, suggestions, and bug reports are highly encouraged. Ideally get in touch with Johannes, as the project is currently in closed alpha stage. We promise to read your pull requests...
