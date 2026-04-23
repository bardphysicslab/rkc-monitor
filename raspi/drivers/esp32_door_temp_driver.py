import socket
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class Esp32DoorTempDriver:
    def __init__(self, uid: str, host: str, port: int = 1234, timeout_s: float = 2.0):
        self.uid = uid
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self._cached_info: Optional[Dict[str, Any]] = None
        self._cached_header: Optional[List[str]] = None
        self._expected_fields = ["temp_c", "door_open", "door_alarm"]

    def get_info(self) -> dict:
        try:
            with self._lock:
                if self._cached_info is None:
                    line = self._send_command("INFO")
                    if not line.startswith("OK INFO"):
                        raise RuntimeError("Unexpected INFO response")
                    self._cached_info = self._parse_info(line)
                info = dict(self._cached_info)
        except Exception:
            info = {
                "uid": self.uid,
                "firmware": None,
                "sensors": None,
            }
        return {
            "uid": info.get("uid", self.uid),
            "source_type": "esp32_door_temp_node",
            "transport": "tcp",
            "protocol": "bardbox",
            "firmware": info.get("firmware"),
            "info_raw": {
                "host": self.host,
                "port": self.port,
                "sensors": info.get("sensors"),
            },
        }

    def get_capabilities(self) -> dict:
        channels = {}
        for field in self._expected_fields:
            if field == "temp_c":
                channels[field] = {"label": "Temperature", "unit": "°C"}
            elif field == "door_open":
                channels[field] = {"label": "Door Open", "unit": "boolean"}
            elif field == "door_alarm":
                channels[field] = {"label": "Door Alarm", "unit": "boolean"}
            else:
                channels[field] = {"label": field, "unit": "unknown"}
        return {
            "channels": channels,
            "raw_available": False,
        }

    def get_reading(self) -> dict:
        fields = self._get_header_fields()
        line = self._send_command("READ")
        if line.startswith("ERR "):
            return {
                "uid": self.uid,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "error",
                "data": {
                    "temp_c": None,
                    "door_open": None,
                    "door_alarm": None,
                },
                "extended": {
                    "error": line,
                    "host": self.host,
                    "port": self.port,
                },
                "raw": None,
            }
        if not line.startswith("DAT,"):
            raise RuntimeError("Unexpected READ response")

        parsed = self._parse_dat(fields, line)
        return {
            "uid": self.uid,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "ok",
            "data": {
                "temp_c": parsed.get("temp_c"),
                "door_open": parsed.get("door_open"),
                "door_alarm": parsed.get("door_alarm"),
            },
            "extended": {
                "host": self.host,
                "port": self.port,
            },
            "raw": None,
        }

    def _get_header_fields(self) -> List[str]:
        with self._lock:
            if self._cached_header is None:
                line = self._send_command("HEADER")
                if not line.startswith("HDR,"):
                    raise RuntimeError("Unexpected HEADER response")
                self._cached_header = self._parse_header(line)
            return list(self._cached_header)

    def _send_command(self, command: str) -> str:
        with socket.create_connection((self.host, self.port), timeout=self.timeout_s) as sock:
            sock.settimeout(self.timeout_s)
            writer = sock.makefile("w", encoding="utf-8", newline="\n")
            reader = sock.makefile("r", encoding="utf-8", newline="\n")
            try:
                writer.write(command + "\n")
                writer.flush()
                line = reader.readline()
            finally:
                reader.close()
                writer.close()

        if not line:
            raise RuntimeError("No response from ESP32 node")
        return line.strip()

    def _parse_info(self, line: str) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "uid": self.uid,
            "firmware": None,
            "sensors": None,
        }
        for part in line.split()[2:]:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if key == "uid":
                info["uid"] = value
            elif key == "fw":
                info["firmware"] = value
            elif key == "sensors":
                info["sensors"] = value
        return info

    def _parse_header(self, line: str) -> List[str]:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3 or parts[0] != "HDR" or parts[1] != "v1":
            raise RuntimeError("Malformed HEADER response")
        fields = parts[2:]
        if fields != self._expected_fields:
            raise RuntimeError("Unexpected HEADER fields")
        return fields

    def _parse_dat(self, fields: List[str], line: str) -> Dict[str, Any]:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != len(fields) + 1 or parts[0] != "DAT":
            raise RuntimeError("Malformed DAT response")

        values: Dict[str, Any] = {}
        for field, raw_value in zip(fields, parts[1:]):
            if field == "temp_c":
                values[field] = float(raw_value)
            elif field in ("door_open", "door_alarm"):
                values[field] = self._parse_bool(raw_value)
            else:
                values[field] = raw_value
        return values

    def _parse_bool(self, raw_value: str) -> Optional[bool]:
        if raw_value == "1":
            return True
        if raw_value == "0":
            return False
        if raw_value.lower() in ("true", "false"):
            return raw_value.lower() == "true"
        return None
