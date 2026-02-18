import time
import uuid
from gateway.app.services.uuid7 import generate_uuid7

def test_uuid7_is_valid_uuid():
    u = uuid.UUID(generate_uuid7())
    assert u.version == 7

def test_uuid7_byte_ordering_increases():
    a = uuid.UUID(generate_uuid7())
    time.sleep(0.002)
    b = uuid.UUID(generate_uuid7())
    assert a.bytes < b.bytes
