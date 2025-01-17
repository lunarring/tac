# Test-driven Agentic Chains

Test-driven Agentic Chains combines the methodical approach of test-driven development with blockchain-inspired interlinking mechanisms, creating a robust framework where AI systems are developed and validated through continuous empirical testing while maintaining a secure, transparent record of their evolution and performance.

> **Warning** ⚠️  
> This project is in **alpha**. Interfaces, commands, and features may change without notice. Use at your own risk and carefully test before deploying in production environments.

## What Is It?

Test-driven Agentic Chains (TDAC) extends the principles of continuous testing and auditing into AI development. By structuring tasks as "blocks" validated by a series of automated tests and recorded changes, you can iteratively refine your AI's behavior while maintaining a transparent trail of its evolution.

## 🚀 Installation

1. **Clone this repository** (or download it) to your local machine:

   ```bash
   git clone git@github.com:lunarring/TDAC.git
   cd TDAC
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

After this, you can run the tdac command from anywhere in your terminal (as long as your environment is activated).

## ⚙️ Usage

The framework provides two main commands: `yaml` and `gather`.

### YAML Command (this currently executes one block)

The yaml command helps create and test new code implementations based on a YAML specification.

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
   tdac yaml examples/caesar_cipher.yaml
   ```

#### Command Options (YAML / Block)

- `--dry-run`: Validate the YAML file without executing
- `--skip-tests`: Skip running tests after implementation
- `--test-only`: Only run the tests without implementing

### Gather Command

The gather command helps collect and document Python files in a directory. This can be especially useful for auditing or for feeding code of a whole repository into a more powerful model.

```bash
tdac gather ./src/tdac
```

#### Command Options (Gather)

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
