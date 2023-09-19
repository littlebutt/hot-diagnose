import json

from queues import TraceMessageEntry


def parse_from_trace(trace_message_entry: TraceMessageEntry) -> str:
    return json.dumps({
        'id': trace_message_entry.id,
        'filename': trace_message_entry.filename,
        'lineno': trace_message_entry.lineno,
        'classname': trace_message_entry.classsname,
        'cb_rts': trace_message_entry.cb_rts
    })

