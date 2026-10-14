from mailops import worker


def test_build_message_sets_headers():
    msg = worker.build_message("a@b.c", "hola", "cuerpo")
    assert msg["To"] == "a@b.c"
    assert msg["From"] == worker.FROM_ADDR
    assert msg.get_content().strip() == "cuerpo"


def test_retry_until_cap():
    assert worker.next_status(0) == "queued"
    assert worker.next_status(1) == "queued"
    assert worker.next_status(2) == "failed"  # cap is 3