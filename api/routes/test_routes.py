from api.routes.status import status_ping


def test_status_ping():
    assert status_ping() == {"ping": "pong"}
