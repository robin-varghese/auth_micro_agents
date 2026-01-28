# Agent Observability

> **Note:** The standalone observability stack defined in this directory is **DEPRECATED**.
> The Phoenix observability service is now fully integrated into the main `finopti-platform` Docker stack.

## Accessing Observability

*   **UI:** [http://localhost:6006](http://localhost:6006)
*   **Trace Endpoint (Internal):** `http://phoenix:4317`
*   **Project Name:** `finoptiagents-MATS`

## Troubleshooting

If you need to debug trace connectivity, you can run the provided script *after updating the ports in the script to match the main platform (6006/4317)*:

```bash
python3 troubleshoot_observability.py
```
