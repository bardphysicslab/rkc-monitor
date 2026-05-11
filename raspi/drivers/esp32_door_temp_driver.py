import socket
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class Esp32NoResponseError(ConnectionError):
    pass


class Esp32ErrorResponse(Exception):
    def __init__(self, raw_error: str):
        super().__init__(raw_error)
        self.raw_error = raw_error


class Esp32DoorTempDriver:
    def __init__(
        self,
        uid: str,
        host: str,
        port: int = 1234,
        timeout_s: float = 1.0,
        name: Optional[str] = None,
        location: Optional[str] = None,
    ):
        self.uid = uid
        self.name = name or uid
        self.location = location
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
                        raise RuntimeError(f"Unexpected INFO response: {line}")
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
            "name": self.name,
            "location": self.location,
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
        return {
            "channels": {
                "temp_c": {
                    "label": "Temperature",
                    "unit": "°C",
                },
                "door_open": {
                    "label": "Door Open",
                    "unit": "boolean",
                },
                "door_alarm": {
                    "label": "Door Alarm",
                    "unit": "boolean",
                },
            },
            "raw_available": False,
        }

    def get_reading(self) -> dict:
        try:
            fields = self._get_header_fields()
            line = self._send_command("READ")

            if line.startswith("ERR "):
                return self._esp32_error_reading(line)

            if not line.startswith("DAT,"):
                raise RuntimeError(f"Unexpected READ response: {line}")

            parsed = self._parse_dat(fields, line)

            return {
                "uid": self.uid,
                "timestamp": self._utc_now(),
                "status": "ok",
                "data": {
                    "temp_c": parsed.get("temp_c"),
                    "door_open": parsed.get("door_open"),
                    "door_alarm": parsed.get("door_alarm"),
                },
                "extended": {
                    **self._node_metadata(),
                },
                "raw": None,
            }

        except Esp32ErrorResponse as exc:
            return self._esp32_error_reading(exc.raw_error)
        except (ConnectionError, TimeoutError, OSError, socket.timeout) as exc:
            return self._node_unavailable_reading(str(exc))
        except Exception as exc:
            return self._driver_error_reading(str(exc))

    def _get_header_fields(self) -> List[str]:
        with self._lock:
            if self._cached_header is None:
                line = self._send_command("HEADER")
                if line.startswith("ERR "):
                    raise Esp32ErrorResponse(line)
                if not line.startswith("HDR,"):
                    raise RuntimeError(f"Unexpected HEADER response: {line}")
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
                writer.close()
                reader.close()

        if not line:
            raise Esp32NoResponseError("No response from ESP32 node")

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
            raise RuntimeError(f"Malformed HEADER response: {line}")

        fields = parts[2:]

        if set(fields) != set(self._expected_fields):
            raise RuntimeError(f"Unexpected HEADER fields: {fields}")

        return fields

    def _parse_dat(self, fields: List[str], line: str) -> Dict[str, Any]:
        parts = [part.strip() for part in line.split(",")]

        if len(parts) != len(fields) + 1 or parts[0] != "DAT":
            raise RuntimeError(f"Malformed DAT response: {line}")

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
        raw = raw_value.strip().lower()

        if raw in ("1", "true"):
            return True

        if raw in ("0", "false"):
            return False

        return None

    def _empty_error_reading(self) -> dict:
        return {
            "uid": self.uid,
            "timestamp": self._utc_now(),
            "status": "error",
            "data": {
                "temp_c": None,
                "door_open": None,
                "door_alarm": None,
            },
        }

    def _node_metadata(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "location": self.location,
            "host": self.host,
            "port": self.port,
        }

    def _esp32_error_reading(self, raw_error: str) -> dict:
        reading = self._empty_error_reading()
        reading["extended"] = {
            **self._node_metadata(),
            "error": self._normalize_esp32_error(raw_error),
            "raw_error": raw_error,
            "node_reachable": True,
        }
        reading["raw"] = raw_error
        return reading

    def _node_unavailable_reading(self, error: str) -> dict:
        reading = self._empty_error_reading()
        reading["extended"] = {
            **self._node_metadata(),
            "error": "node_unavailable",
            "node_reachable": False,
            "detail": error,
        }
        reading["raw"] = None
        return reading

    def _driver_error_reading(self, error: str) -> dict:
        reading = self._empty_error_reading()
        reading["extended"] = {
            **self._node_metadata(),
            "error": "driver_error",
            "node_reachable": True,
            "detail": error,
        }
        reading["raw"] = None
        return reading

    def _normalize_esp32_error(self, raw_error: str) -> str:
        parts = raw_error.strip().split(maxsplit=1)

        if len(parts) == 2 and parts[0] == "ERR":
            return parts[1].strip().lower()

        return "esp32_error"

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
