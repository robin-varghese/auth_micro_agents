# GitHub Collaboration & Demo-Ready Strategy

To maintain a high-velocity, collaborative development environment that is always ready for demonstration, we follow these core principles.

## 1. Branching Strategy: "Stable Main"
We use a simplified GitHub Flow:
*   **Main Branch**: This branch is **SACRED**. It must always be in a working, deployable, and demoable state.
*   **Feature Branches**: All work happens in branches prefixed with `feature/`, `fix/`, or `task/`.
*   **No Direct Commits**: All changes to `main` must come through a Pull Request (PR).

## 2. "Always Demo-Ready" Principles
*   **Docker Consistency**: Every change must be verified against the `docker-compose.yml`. If a new service or environment variable is added, it MUST be updated in the `.env.template` and Compose file simultaneously.
*   **Automated Verification**: Before merging a PR, the `tests/run_suite.py` must pass at 100% (excluding planned skips like Brave Search).
*   **Seeded Data**: Always provide or script the creation of dummy data (e.g., GCP project mockups, local storage samples) so the system works even in restricted environments.

## 3. Collaboration Workflow
1.  **Issue Creation**: Every task starts with an entry in the `ROADMAP.md` or a GitHub Issue.
2.  **PR Reviews**: Minimum 1 peer review (or AI agent cross-check) for core architectural changes.
3.  **Documentation First**: Updates to agent behavior must be reflected in the `AI_AGENT_DEVELOPMENT_GUIDE.md`.

## 4. Demo Check-in Checklist
Before finalizing a feature for a demo:
- [ ] `docker-compose down && docker-compose up -d` works.
- [ ] All environment variables are in `.env.template`.
- [ ] The MATS Orchestrator can successfully route a basic query.
- [ ] No hard-coded local paths that break in other environments.
