## Description

Provide a clear and concise summary of the changes introduced in this pull request.

- **Type of Change**: [ ] Feature (`feat`) | [ ] Bug Fix (`fix`) | [ ] Refactor (`refactor`) | [ ] Documentation (`doc`) | [ ] Tests (`test`)
- **Related Issue**: Fixes #(issue)

## Architectural & Code Quality Verification

Please check all items that apply:

- [ ] **DCO Sign-off**: All commits have been signed off with `git commit -s` under the Developer Certificate of Origin.
- [ ] **Tests Passing**: Verified with `make test`.
- [ ] **Linting & Formatting**: Clean run with `make lint` (Ruff / isort compliant).
- [ ] **Architecture**: Adheres to high cohesion and low coupling (ABCs / factory patterns).
- [ ] **Single Source of Truth**: Shared constants and configs are centralized in `assets/configs/`.
- [ ] **Frontend Security**: Zero `innerHTML` usage; DOM mutations utilize safe DOM APIs (`textContent`, `createElement`).
- [ ] **No Secrets**: Verified that no API keys or local `.env` values are exposed.

## Summary of Changes

<!-- Bullet list of specific modifications -->
- 
- 
