import json
from typing import Optional

from queues import ActionMessageEntry, TraceMessageEntry


def parse_to_action(payload: str) -> Optional['ActionMessageEntry']:
    try:
        obj = json.loads(payload)
        action_message_entry = ActionMessageEntry(id=obj['id'],
                                                  action=obj['action'],
                                                  value=obj['value'])
    except Exception:
        return None
    return action_message_entry


def parse_from_trace(trace_message_entry: TraceMessageEntry) -> str:
    return json.dumps({
        'id': trace_message_entry.id,
        'filename': trace_message_entry.filename,
        'lineno': trace_message_entry.lineno,
        'cb_rts': trace_message_entry.cb_rts
    })

