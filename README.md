# Trusty Agentic Chains (tac)

Trusty Agentic Chains (tac) is a AI-driven coding framework that leverages *coding agents* with *trusty agents*. *Coding agents* implement desired changes in a codebase and *trusty agents* generate trust assurances, by means of empirical verifications. For instance, a trusty agent could run unit tests or even execute the software and look at it carefully. If one of the trusty agents protests, the analyzed issue goes back to the coding agents until they fix it for real. We coin the result of each successful operation as a *block*, and a block consists of code changes and trust assurances and is ready to be merged into the codebase. Thus you can think of tac as a blockchain for code changes, but actually useful. For a detailed technical overview of the system architecture and methodology, please refer to our [whitepaper](docs/whitepaper.md).

> **Warning** ⚠️  
> This project is in **alpha**. Interfaces, commands, and features may change without notice. Use at your own risk and do not use in production environments. 

## 🏗️ Architecture
![Block Execution Process](docs/block_execution.png)
### Coding Agents
These agents generate and modify code based on your instructions:
- **Aider Agent**: Leverages the aider-chat library for code generation [https://aider.chat/]
- **Native Agent**: Our lightweight in-house implementation for code generation

### Trusty Agents
These agents validate and verify the code changes:
- **Pytest Agent**: Runs software tests and analyzes results to ensure functionality
- **Plausibility Agent**: Evaluates if code changes match the requested functionality
- **Performance Agent**: Benchmarks code and guides performance optimization
- **(coming soon):** visual agent, able to look at graphics
- **(more trusty agents coming soon...)**

### Block execution flow
* **Block**: A valid block is defined as a change in code (diff) and trust assurances (e.g. passing unit tests)
* **ProtoBlock**: Standardized specification for a coding task, containing task description, test specifications, and files to modify
* **BlockExecutor**: Executes the changes specified in a ProtoBlock and validates them with trusty agents
* **BlockBuilder**: Transforms a ProtoBlock into a finalized Block by implementing the requested changes and obtaining the trust assurances
* **ProtoBlockGenerator**: Creates structured ProtoBlocks from high-level task instructions
* **BlockProcessor**: Runs in a loop to execute ProtoBlocks, handling retries
* **MultiBlockOrchestrator**: Splits complex tasks into smaller, manageable chunks that can be executed sequentially
tac operates through a chain of specialized agents working together:

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



# Optional: Choose a specific coding agent
tac make "your instructions" 
```


### Git Integration

tac will create a new branch with an id (e.g., tac/buxfix/refactor_spaghetti_code) where it will commit all changes, provideded everything worked out. If not, you'll have to manually switch back to your previous branch. 

If you don't want to use the git integration or want to use tac outside of a git repo, tac will automatically switch to a FakeGitManager that emulates git in temp directories under the hood.

### Performance Optimization

Optimize specific functions in your codebase using the Performance Trusty Agent:

```bash
# Optimize a specific function
tac optimize function_name
```


### Voice Interface (Experimental)

tac now includes an experimental voice interface that allows you to interact with the system using speech:

```bash
tac voice
```

> **Note**: The voice interface is currently experimental and only works without the orchestrator. It may require additional setup for speech recognition and synthesis. 

### View Blocks and Logs

View execution logs interactively:

```bash
tac view
```

This command provides an interactive interface to:
- Browse and read log files from previous tac executions
- Search for specific text within logs
- Jump to section headings for easier navigation



### Test Management

The framework provides several test-related commands:

```bash
# Run tests (because trust, but verify)
tac test run [--directory tests]

# List available tests
tac test list [--directory tests]

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

TAC uses a hierarchical configuration system (in `src/tac/core/config.py`) with several categories.



### Command-line Options

TAC provides a comprehensive set of command-line options for customizing behavior. Here are the key options available for the main `make` command:

- `--use-orchestrator`: Enable/disable the task orchestrator for complex tasks (default: false)
- `--confirm-multiblock-execution`: Prompt for confirmation before executing multi-block tasks (default: true)
- `--coding-agent`: Choose between "aider" or "native" coding agents (default: native)
- `--reasoning-effort`: Set reasoning effort level ("low", "medium", "high") (default: medium)
- `--minimum-plausibility-score`: Set the minimum grade (A-F) for plausibility tests (default: B)

- `--max-retries-block-creation`: Maximum number of retry attempts for block creation (default: 4)
- `--max-retries-protoblock-creation`: Maximum number of retry attempts for protoblock creation (default: 4)
- `--total-timeout`: Maximum total execution time in seconds (default: 600)
- `--no-git`: Disable all git operations (branch checks, commits, etc.)
- `--log-level`: Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

Each command (`make`, `gather`, `test`, `optimize`, `view`, `voice`) has its own specific options. For a complete list of options for any command:

```bash
tac <command> --help
```

For example:
```bash
# See all options for the make command
tac make --help

# See all options for the gather command
tac gather --help

# Enable the orchestrator
tac make "your task" --use-orchestrator

# Disable the orchestrator
tac make "your task" --no-use-orchestrator
```

## ✍️ Contributing

Since this project is alpha, contributions, suggestions, and bug reports are highly encouraged. Ideally get in touch with Johannes, as the project is currently in closed alpha stage. We promise to read your pull requests...
