**Version:** 1.0\
**Last Updated:** January 20, 2025

## Overview

**TDAC (Test-driven Agentic Chains)** is a structured, automated framework engineered to significantly enhance AI-driven software development by creating a sequence of validated blocks, each representing a discrete, tested, and confirmed improvement to the code. In much the same way that blockchain technology ensures the immutability of prior blocks, TDAC guarantees each new code change is thoroughly tested and validated before linking it to the existing chain.

A **high-level manager** orchestrates this chain of development tasks, preserving both the workflow’s integrity and efficiency. Just as every block in a blockchain references the hash of its predecessor, each stage of TDAC references a known snapshot of the codebase and confirms its correctness with automated tests, ensuring that merging new functionality can only occur when it does not break existing features.

---

## Core Concepts

### Seed Block

In TDAC, the **seed block** is akin to a “genesis block,” anchoring the process at a fixed point:

- **Global Instruction**: An overarching statement describing the core feature or fix to be implemented.
- **Snapshot of the Entire Codebase**: Typically identified by a commit hash, tag, or version, ensuring an unchanging reference point for subsequent work.

### Proto Block

A **proto block** serves as the detailed recipe or blueprint describing how to implement, test, and verify a requested change:

- **Task Specification**: Outlines the new functionality or fixes.
- **Test Specification**: Defines tests (positive and negative scenarios) that ensure the functionality operates correctly.
- **Data Generation**: Specifies any special data or conditions needed for the tests (e.g., BPM settings or note sequences).
- **Context Files**: Lists which code files or modules must be examined or updated by the AI Worker Agent&#x20;

### Merge Block

Once a proto block’s instructions have been executed and validated, the resulting changes form a **merge block**:

- **Code Differences**: All new, modified, or deleted sections of code referencing a known snapshot (commit hash).
- **New or Updated Tests**: Additional tests that verify the updated functionality.

The merge block is the final, certifiable artifact ready to be integrated into the main branch. It includes a cryptographic-like reference (such as a commit hash) and a certified confirmation that neither newly introduced changes nor existing functionality are broken.

---

## Single-Block Flow in TDAC

Below is a step-by-step outline of how TDAC handles **one** block from start to finish:

1. **Seed Block Creation**  
   - Identify the high-level instruction (e.g., “Add feature X”).  
   - Reference the specific codebase state via a commit hash or version tag.

2. **Proto Block Definition**  
   - Spell out **what** must be changed, **why**, and **how** tests should be generated.  
   - Specify relevant **context files** and any required **test data** or conditions.

3. **Execution by the AI Worker Agent**  
   - The agent (e.g., Aider) consumes the proto block, making the requested code changes.  
   - It then creates and executes new test scenarios while ensuring all existing tests still pass.

4. **Merge Block Formation**  
   - When the new and existing tests succeed, package the code differences and updated tests into a merge block.  
   - Link the merge block back to the previous (or seed) state using a commit hash to maintain an immutable history.

5. **Integration**  
   - Integrate the merge block into the main or target branch, thus finalizing one complete TDAC cycle for this block.

At this point, you have a verified increment of development that cannot break existing functionality. Just like adding a new block to a blockchain, once appended, it solidifies that specific step in the project’s history.

---

## Orchestrating Larger Goals

While each **seed → proto → merge** cycle addresses a single incremental improvement, TDAC also supports chaining multiple such cycles together to achieve **much larger or more complex** development goals. The key idea is:

1. **High-Level Plan**  
   - Begin by defining a **high-level, potentially very complex** functionality.  
   - Break down this broad goal into multiple incremental tasks, each with its own seed block and subsequent proto/merge block chain.

2. **Automated Orchestrator**  
   - A **high-level manager** or orchestrator ensures each task is tackled in the correct order.  
   - The orchestrator tracks dependencies: later tasks can reference the output of earlier ones.

3. **Parallel Execution**  
   - Multiple proto blocks can be worked on in parallel, so long as their changes do not conflict or can be merged in a coordinated manner.

4. **Sequential Validation**  
   - After each proto block is fulfilled, a merge block is formed and validated against the entire codebase.  
   - This approach preserves system stability and ensures that partial merges do not introduce regressions.

5. **Iterative Refinement**  
   - If a big feature spans multiple merges, the orchestrator can define checkpoints, each culminating in a merge block.  
   - Together, these merges build up the final functionality incrementally.

By chaining seed blocks and their subsequent proto-to-merge flows, TDAC can methodically develop intricate features or major refactors. Each step is validated by robust testing, ensuring that only correct and stable blocks are added to the codebase, mirroring the trustable, append-only nature of a blockchain.

---

## Advantages of TDAC

1. **Immutable Audit Trail**\
   Each step (seed, proto, merge) references specific commits, creating a transparent “ledger” of changes.

2. **Incremental and Verified Development**\
   Requiring full test suites to pass before integration ensures that each block solidifies the codebase’s integrity.

3. **Modular and Extensible**\
   The framework can accommodate any AI Worker Agent. The block definitions remain consistent, thus reducing friction when agents or tools evolve.

4. **Reduced Risks and Fewer Regressions**\
   Repeated automated testing confirms that newly introduced features don’t interfere with existing functionality.

5. **Parallelized Efforts**\
   Multiple proto blocks can be developed simultaneously, each culminating in its own verified merge block.

