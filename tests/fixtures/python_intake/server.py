"""Small source-only example: intake endpoint delegates to local storage."""
from storage import save


def receive(body):
    if not body.get('reference'):
        raise ValueError('reference required')
    return save(body)
