import json
import logging
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "service": record.name,
            "event": record.getMessage(),
        }
        for key in (
            "request_id",
            "run_id",
            "dataset",
            "method",
            "path",
            "status",
            "duration_ms",
            "asset_count",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__
            traceback = record.exc_info[2]
            locations = []
            while traceback:
                locations.append({"file": traceback.tb_frame.f_code.co_filename, "line": traceback.tb_lineno})
                traceback = traceback.tb_next
            payload["trace_locations"] = locations
        return json.dumps(payload)


def configure():
    logger = logging.getLogger("data_police")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
