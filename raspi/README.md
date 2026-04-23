# Raspberry Pi App

This is the deployment-facing Pi app layer for RKC-Monitor.

Rules for customization:

- keep ESP32 Bard Box TCP protocol parsing inside drivers
- keep deployment identity in config
- keep `main.py` as the orchestrator
- return normalized readings only from drivers

The included app is configured for an ESP32 Bard Box node that serves:

- `temp_c`
- `door_open`
- `door_alarm`

Set the node IP in `raspi/config/app_config.example.json` or in an external
config file referenced by `BARDBOX_APP_CONFIG`.
