# GitHub Collaboration & Demo-Ready Strategy

To maintain a high-velocity, collaborative development environment that is always ready for demonstration, we follow these core principles.

## 1. Branching Strategy: "Stable Main"
We use a simplified GitHub Flow:
*   **Main Branch**: This branch is **SACRED**. It must always be in a working, deployable, and demoable state.
*   **Feature Branches**: All work happens in branches prefixed with `feature/`, `fix/`, or `task/`.
*   **No Direct Commits**: All changes to `main` must come through a Pull Request (PR).

### Branch Protection Rules (GitHub UI)
*   **Require a pull request before merging**: 1 review required.
*   **Require status checks to pass**: `Demo Readiness & PR Verification` GitHub Action must succeed.
*   **Require conversation resolution**: All comments must be resolved.
*   **Restrict deletions**: Prevent accidental branch deletion.

## 2. "Always Demo-Ready" Principles
*   **Docker Consistency**: Every change must be verified against the `docker-compose.yml`. If a new service or environment variable is added, it MUST be updated in the `.env.template` and Compose file simultaneously.
*   **Automated Verification**: Before merging a PR, the `tests/run_suite.py` must pass at 100% (excluding planned skips like Brave Search).
*   **Mock Data & "Offline" Mode**: 
    - Always provide a `mock_data/` directory with sample RCA JSONs and logs.
    - Agents should have a "Dry Run" or "Mock" mode to demonstrate UI flows without real GCP costs or access.

## 3. Collaboration Workflow
1.  **Issue Creation**: Every task starts with an entry in the `ROADMAP.md` or a GitHub Issue.
2.  **PR Reviews**: Minimum 1 peer review (or AI agent cross-check) for core architectural changes.
3.  **Documentation First**: Updates to agent behavior must be reflected in the `AI_AGENT_DEVELOPMENT_GUIDE_V2.0.md`.

## 4. Demo Check-in Checklist
Before finalizing a feature for a demo:
- [ ] `docker-compose config -q` passes.
- [ ] All new environment variables are added to `.env.template`.
- [ ] Mock data is updated in `mock_data/` to showcase the new feature.
- [ ] The MATS Orchestrator can successfully route a basic query.
- [ ] No hard-coded local paths.
