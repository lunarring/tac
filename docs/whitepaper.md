**Version:** 1.1\
**Last Updated:** February 24, 2025

## Overview

**Test-linked Agentic Chains (tac)** is a framework to fully automate AI-driven software creation. The core idea is to create *blocks* that can be attached to any existing codebase. A block consists of a *code diff* plus *hope*. We define hope as some form of empiric testing that the code changes a) do not break the existing codebase b) fulfil the promised function. Empirical tests can for instance be unit tests that have to be passed, or a code review by a simulated senior software engineer. 

To create a block, we need a protoblock which carries a standardized set of instructions and files that have read or write access. The block executor then turns this protoblock into a block and runs all required tests. Under the hood, tac allows to use modular coding agents, at the moment we support aider and a native agent. 

Larger requested developments thus are automatically parcellated into multiple protoblocks, which are subsequently executed and stacked upon each others.


---

## Core Concepts

### Proto Block

A **proto block** serves as the detailed recipe or blueprint describing how to implement, test, and verify a requested block. The proto block is automatically generated based on the seed instructions. 

- **Task Specification**: Outlines the new functionality or fixes.
- **Test Specification**: Defines tests (positive and negative scenarios) that ensure the functionality operates correctly.
- **Data Generation**: Specifies any special data or conditions needed for the tests (e.g., BPM settings or note sequences).
- **Write/Context Files**: Lists which code files or modules must be examined or updated by the AI Worker Agent&#x20;

### Block

Once a protoblock's has been executed (including validation), the resulting changes form a **block**:

- **Code Differences**: All new, modified, or deleted sections of code referencing a known snapshot (commit hash).
- **New or Updated Tests**: Additional tests that verify the updated functionality.
- **Code review test**: passed codereview with given passmark (e.g. grade "B" from a simulated senior software engineer)

The block is the final, certifiable artifact ready to be integrated into the main branch. It includes a cryptographic-like reference (such as a commit hash) and a certified confirmation that neither newly introduced changes nor existing functionality are broken.

---

## Advantages of tac

1. **Immutable Audit Trail**\
   Each step (seed, proto block, block) references specific commits, creating a transparent "ledger" of changes.

2. **Incremental and Verified Development**\
   Requiring full test suites to pass before integration ensures that each block solidifies the codebase's integrity.

3. **Modular and Extensible**\
   The framework can accommodate any AI Worker Agent. The block definitions remain consistent, thus reducing friction when agents or tools evolve.

4. **Reduced Risks and Fewer Regressions**\
   Repeated automated testing confirms that newly introduced features don't interfere with existing functionality.

5. **Parallelized Efforts**\
   Multiple proto blocks can be developed simultaneously, each culminating in its own verified block.

