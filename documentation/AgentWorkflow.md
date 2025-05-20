# Reggie Workflows UI Guide

## Terminology & UX Mapping

Reggie uses the term **Workflow** in the user interface (UI) to describe what is technically implemented as an **Agent** under the hood. This abstraction is designed to simplify the experience for non-technical users while retaining the full power of autonomous agents.

---

## 🧭 What Users See

* **Create a Workflow**: Entry point in the UI.
* **Workflow Settings**: Title, description, inputs, outputs, and goals.
* **Instructions**: User-defined prompts or task guidance.
* **Expected Output**: Description of the format or result the workflow should produce.

### Tooltip / Helper Text Example

> "Each workflow is powered by an AI Agent that follows your instructions to deliver consistent, automated results."

---

## ⚙️ What Happens Under the Hood

Creating a Workflow creates a Reggie Agent with:

* Custom instruction (`AgentInstruction`)
* Expected output (`AgentExpectedOutput`)
* Linked knowledge base and memory (`AgentKnowledge`, `AgentMemory`)
* Model selection (`ModelProvider`)
* Optional toolchain (e.g., web search, blockchain lookup)

These are managed by the `AgentBuilder` class and persisted in the `DjangoAgent` model.

---

## 🔍 Advanced User View

Power users can access additional agent configuration:

* Model and provider used
* Tool access (e.g. SlackTools, SeleniumReader)
* Memory & session table references
* Debug and markdown settings

### UI Label: `View Agent Details`

This section can expose:

* Agent architecture
* Invocation logs / recent runs
* Embedded knowledge tables

---

## 💡 Naming Summary

| UI Label      | Backend Mapping      |
| ------------- | -------------------- |
| Workflow      | Agent                |
| Instructions  | AgentInstruction     |
| Output Format | AgentExpectedOutput  |
| Knowledge     | PgVector table       |
| Execution     | AgentBuilder.build() |

---

## 📚 Benefits of This Pattern

* Easier onboarding for non-technical teams.
* Future-proofed for agent chaining, tool orchestration, or RAG workflows.
* Aligns with industry patterns (e.g. Harvey.ai's "Workflows").
