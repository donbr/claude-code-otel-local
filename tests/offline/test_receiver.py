from tests.claude.conftest import Receiver


def test_receiver_repr_hides_bodies():
    # pytest prints the Receiver on assertion failure; bodies hold identifiers such as user.email.
    r = Receiver(base="http://127.0.0.1:1", bodies=[b"user.email secret-value"], paths=["/v1/logs"])
    assert "secret-value" not in repr(r)
