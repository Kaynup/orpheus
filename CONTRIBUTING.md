# Contributing to Orpheus

Thank you for your interest in contributing to **Orpheus**! You are welcome to do community contributions, bug fixes, feature enhancements, and documentation improvements.

To ensure the project remains high-quality, architecturally cohesive, and legally protected for the entire open-source community, all contributors are expected to follow these guidelines.

---

## 1. Code of Conduct

* Be respectful, constructive, and collaborative in all discussions, issues, and pull requests.
* Focus on technical merit, architecture, code quality, and maintainability.
* Harassment, derogatory comments, and disruptive behavior will not be tolerated.

---

## 2. Intellectual Property & Developer Certificate of Origin (DCO)

Orpheus is open-source software licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. 

To maintain clean copyright provenance and ensure nobody submits third-party proprietary or infringing code, Orpheus requires all commits to be signed off in accordance with the **Developer Certificate of Origin (DCO)**.

### The DCO Text (Version 1.1)

```text
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it; and

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

### How to Sign Off Your Commits

Simply append `-s` to your git commit command:

```bash
git commit -s -m "feat(retrieval): add reciprocal rank fusion support"
```

This automatically attaches a trailer to your commit message:
```text
Signed-off-by: Your Name <your.email@example.com>
```

---

## 3. Architectural Principles

All code contributions must adhere to Orpheus's core architecture:

1. **High Cohesion & Low Coupling**:
   - Subsystems (ingestion, retrieval, generation, evaluation) must be decoupled behind Abstract Base Classes (ABCs) and Protocols (`app/pipeline/base.py`).
   - Use composition and dependency injection rather than tightly coupling components.
   - Use factory patterns (`app/pipeline/factory.py`) to resolve and instantiate sub-pipelines.
2. **Single Source of Truth (SSOT)**:
   - Never duplicate configuration constants, prompt templates, stopwords, or refusal strings across modules.
   - Store static JSON assets in `assets/configs/` and expose them via dedicated modules (e.g. `app/generation/assets.py`).
3. **Deterministic Offline Fallbacks**:
   - Live external APIs (LiteLLM) must be isolated behind strategy interfaces so the system remains fully testable without network access.

---

## 4. Code Quality & Standards

### Python
* **Formatting & Linting**: Enforced with **Ruff**.
  * Run `make lint` before submitting a PR.
  * Run `make format` to auto-format code.
* **Import Sorting (`isort`)**:
  * Standard library module imports first (`import re`, `import time`).
  * Third-party library imports second (`import litellm`, `from flask import Flask`).
  * First-party local imports last (`from app.config import config`).
* **Line Length**: Strictly within 120 characters (`E501`).
* **Trailing Whitespace**: Zero trailing whitespace on blank lines (`W293`).
* **Type Annotations**: Provide static type hints for public functions and class methods.

### Frontend (Web UI)
* **Safe DOM Manipulation Only**:
  * **Never** use `innerHTML`, `outerHTML`, or raw HTML string injection.
  * Construct and modify DOM nodes strictly with safe APIs: `document.createElement()`, `textContent`, `appendChild()`, `replaceChildren()`, and `dataset` attributes.
* **Minimalist UI & Tooltips**:
  * Keep dashboard cards, tables, and stepper ribbons compact, clean, and signal-dense.
  * Avoid prose walls or multi-sentence theoretical descriptions in the main viewport. Place formulas and explanations behind interactive `ⓘ` (`info-btn`) tooltip buttons.
  * Avoid emoji prefixes in technical section headers and table column titles.

---

## 5. Development & Testing Workflow

### Setup

```bash
# Clone the repository
git clone https://github.com/your-username/Orpheus-RAG.git
cd Orpheus-RAG

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
make install
```

### Running Tests & Verification

Before submitting changes, ensure all verification checks pass:

```bash
# Run unit and integration tests
make test

# Run code linter
make lint

# Run evaluation benchmark
make eval
```

---

## 6. Pull Request (PR) Checklist

When opening a Pull Request, verify the following:

- [ ] Branch is created from `main` with a descriptive name (`feat/my-feature`, `fix/issue-id`).
- [ ] Every commit includes a DCO sign-off (`git commit -s`).
- [ ] All tests pass cleanly (`make test`).
- [ ] Code passes Ruff linting with zero warnings (`make lint`).
- [ ] No API keys, credentials, or sensitive files are included.
- [ ] Documentation and inline docstrings are updated for any modified public APIs.
