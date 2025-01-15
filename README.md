# Test Chain Approach

![Test Chain Logo](test_chain.png)

> An Automated, Test-Driven AI Coding Framework

## High Level Summary

The Test Chain Approach is a structured, automated framework designed to enhance AI-driven software development through a sequence of interconnected, test-driven tasks. At its core, this methodology ensures that every modification or implementation within the codebase is meticulously validated against predefined tests before advancing to subsequent steps. This process is orchestrated by a high-level manager that oversees the entire chain, ensuring the workflow remains intact and efficient.

Each step in the Test Chain consists of a distinct block that encompasses three tightly correlated elements. First, there is a clear and precise command or instruction that specifies the exact change or implementation required in the existing codebase. This instruction serves as the directive for the coding agent, guiding the necessary modifications. Second, the block includes a detailed description of how to generate the corresponding tests. These tests are designed to validate the specified change, encompassing both positive cases that should pass and negative cases that should fail. Third, the block outlines the generation or sourcing of test data, ensuring that there is appropriate data to effectively evaluate the tests. This includes defining scenarios that should lead to both successful and failed outcomes, thereby providing comprehensive coverage for the changes being made.

The Worker Agent, which can be any modular AI coding framework such as Aider, is responsible for executing these tasks. The agent generates the required tests based on the provided specifications and implements the necessary code changes as per the instructions. By maintaining modularity, the framework allows for easy integration or swapping of different AI agents without disrupting the overall workflow. This ensures flexibility and scalability, enabling the system to adapt to various project requirements and evolving development environments.

A crucial aspect of the Test Chain Approach is the enforcement that progression through the chain is contingent upon the successful fulfillment of each test. This means that the framework will only move to the next block once the current tests have been run and passed, ensuring that each step builds upon a solid and verified foundation. If a test fails, the system can incorporate mechanisms for retrying the task, refining the instructions, or escalating the issue to supervisory layers for further analysis and resolution.

## Getting Started

### Prerequisites
- Python 3.8+
- pip

### Installation
```bash
pip install -r requirements.txt
```

## Usage
```bash
python main.py
```

## Project Structure
```
.
├── main.py          # Entry point for the application
├── agent.py         # Worker agent implementation (includes AiderAgent)
├── block.py         # Block class definition for task encapsulation
├── executor.py      # Test chain executor with test running capabilities
├── config.yaml      # Configuration settings for the framework
└── tests/           # Test suite directory
```

## Core Components

### Block
The `Block` class is the fundamental unit of work in the Test Chain. Each block contains:
- Function name to be implemented/modified
- File path where changes will be made
- Task description
- Test specification
- Test data generation instructions

### BlockExecutor
The executor manages the execution of individual blocks:
- Handles test running and validation
- Creates and manages worker agents
- Loads configuration settings
- Provides test results and execution status

### Agent
The framework supports modular agent implementation:
- Currently uses Aider as the default agent
- Can be extended to support other AI coding frameworks
- Handles code modifications and test implementation

## Configuration
The framework uses `config.yaml` for customizable settings:
- Test execution parameters
- Agent configurations
- Framework behavior settings

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.
