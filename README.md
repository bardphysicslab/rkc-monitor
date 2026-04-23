# RKC-Monitor

`RKC-Monitor` is a Bard Box deployment for an ESP32 Wi-Fi node that serves fridge temperature and door state over TCP.

It keeps the Bard Box architecture from the template:

- deployment-specific config
- Pi app orchestration in `raspi/main.py`
- hardware/protocol handling inside a driver
- normalized readings returned to the app and UI

## What This Repo Is

- A real Bard Box deployment repo
- A Raspberry Pi monitor for an ESP32 Bard Box TCP node
- A clean deployment-specific app built on the Bard Box standards

## What This Repo Is Not

- Not the canonical Bard Box standards/spec repo
- Not a generic starter template anymore

Use the separate `bardbox` repo as the standards and reference source for protocol, reading format, driver boundaries, runtime structure, and UI conventions.

## Local Run

```bash
python3 -m venv raspi/venv
source raspi/venv/bin/activate
pip install -r requirements.txt
uvicorn raspi.main:app --reload
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Run Git commands and app launch from repo root.

## Device Contract

The ESP32 node is expected to listen on TCP port `1234` and answer Bard Box-style text commands:

- `INFO`
- `PING`
- `STATUS`
- `HEADER`
- `READ`
- `START`
- `STOP`

Current header:

```text
HDR,v1,temp_c,door_open,door_alarm
```

Current sample:

```text
DAT,<temp_c>,<door_open>,<door_alarm>
```

Door values are interpreted as:

- `1` = `true`
- `0` = `false`

## Repo Layout

```text
bardbox-project-template/
  docs/        deployment-facing notes
  firmware/    starter firmware area for Bard Box nodes
  raspi/       Pi app, drivers, config, templates, static assets
  scripts/     helper scripts for setup, restart, health checks
  tests/       starter test notes
  data/        runtime data directory
```

## Config

Set the ESP32 node IP in:

- `raspi/config/app_config.example.json`

or point `BARDBOX_APP_CONFIG` at a deployment-specific config file.
