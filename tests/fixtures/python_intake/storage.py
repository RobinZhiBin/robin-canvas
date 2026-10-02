"""Append-only process memory; restarting the process loses the records."""
records = []


def save(body):
    records.append(dict(body))
    return {'position': len(records)}
