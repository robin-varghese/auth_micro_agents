# Task: Integrate Arize Phoenix Observability

- [ ] Setup Observability Infrastructure <!-- id: 0 -->
    - [ ] Create `finopti-platform/agent-observability/` (if not exists) and copy plan/task files <!-- id: 1 -->
    - [ ] Update `finopti-platform/docker-compose.yml` to add `phoenix` service and configure `orchestrator` <!-- id: 2 -->
- [ ] Instrument Orchestrator Agent <!-- id: 3 -->
    - [ ] Update `mats-agents/mats-orchestrator/requirements.txt` with Phoenix dependencies <!-- id: 4 -->
    - [ ] Update `mats-agents/mats-orchestrator/agent.py` to initialize tracing <!-- id: 5 -->
- [ ] Verification <!-- id: 6 -->
    - [ ] Build and start services <!-- id: 7 -->
    - [ ] Verify Phoenix UI availability <!-- id: 8 -->
    - [ ] Send test request and verify traces <!-- id: 9 -->
