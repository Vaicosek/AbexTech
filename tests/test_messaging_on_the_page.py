"""Replying happens on the page that lists the conversation.

"Open the messenger" was the last button on the site whose answer to a question
was to send somebody somewhere else — and a second page meant a second copy of
the thread being answered.

What these tests hold down.

THE KEY IS BOUND TO THE THREAD. `message:t:<id>`. A key minted on one
conversation must not post into another; the server checks that, and minting per
thread here is what lets the page satisfy it.

AN UNANSWERED SEND RESUMES ITS KEY, it does not mint a fresh one. A new key would
be one the claim table has never seen, which is exactly the double the claim
exists to prevent — so the box carries the same key back, with the reason in
words rather than a silent 409 on submit.

MARKING READ CARRIES NO KEY, and that is deliberate: the write is `MAX(old,
new)`, idempotent by construction. A single-use key there would be ceremony that
can only fail.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_livescreens as LS  # noqa: E402
import abex_render as R        # noqa: E402
import canvas_web              # noqa: E402

UID, CSRF = "1234", "csrf-token"

THREADS = [
    {"id": 3, "other_name": "Greyhames", "unread": 2, "last_message_id": 91,
     "last_body": "the shipment is short", "last_message_at": 1},
    {"id": 5, "other_name": "Amazonia", "unread": 0, "last_message_id": 44,
     "last_body": "thanks", "last_message_at": 2},
]


class FakeResume:
    """Stands in for `messages_web._resume_key`, recording what it was asked for."""

    def __init__(self, stuck=()):
        self.asked = []
        self.stuck = set(stuck)

    def __call__(self, uid, purpose):
        self.asked.append((uid, purpose))
        if purpose in self.stuck:
            return "K-stuck", ("A message you sent has not been confirmed yet. This "
                               "form carries the same confirmation as that one.")
        return "K-" + purpose.replace(":", "-"), ""


def _blocks(monkeypatch, resume, threads=THREADS, csrf=CSRF):
    import messages_web
    monkeypatch.setattr(messages_web, "_resume_key", resume)
    return LS._reply_blocks(UID, csrf, threads)


def _boxes(monkeypatch, resume, **kw):
    out = []
    for b in _blocks(monkeypatch, resume, **kw):
        out.extend(b.get("reply") or [])
    return out


def test_a_box_per_conversation(monkeypatch):
    boxes = _boxes(monkeypatch, FakeResume())
    assert [b["thread_id"] for b in boxes] == [3, 5]


def test_unread_threads_come_first(monkeypatch):
    threads = [dict(THREADS[1]), dict(THREADS[0])]     # read one listed first
    boxes = _boxes(monkeypatch, FakeResume(), threads=threads)
    assert boxes[0]["thread_id"] == 3, "the unread thread is the one to answer"


def test_each_key_names_its_own_thread(monkeypatch):
    fake = FakeResume()
    boxes = _boxes(monkeypatch, fake)
    assert [p for _u, p in fake.asked] == ["message:t:3", "message:t:5"]
    assert boxes[0]["key"] != boxes[1]["key"]


def test_an_unconfirmed_send_gets_the_same_key_back(monkeypatch):
    fake = FakeResume(stuck={"message:t:3"})
    boxes = {b["thread_id"]: b for b in _boxes(monkeypatch, fake)}
    assert boxes[3]["key"] == "K-stuck"
    assert "has not been confirmed" in boxes[3]["hint"]
    assert boxes[5]["key"] != "K-stuck", "the other thread is unaffected"


def test_mark_read_only_where_there_is_something_unread(monkeypatch):
    boxes = {b["thread_id"]: b for b in _boxes(monkeypatch, FakeResume())}
    assert "rdgo" in R._replybox({"reply": [boxes[3]]})
    assert "rdgo" not in R._replybox({"reply": [boxes[5]]})


def test_the_watermark_sent_is_the_newest_message(monkeypatch):
    boxes = {b["thread_id"]: b for b in _boxes(monkeypatch, FakeResume())}
    assert boxes[3]["newest"] == 91
    assert 'data-newest="91"' in R._replybox({"reply": [boxes[3]]})


def test_no_box_without_a_session_token(monkeypatch):
    assert _boxes(monkeypatch, FakeResume(), csrf="") == []


def test_no_box_without_threads(monkeypatch):
    assert _blocks(monkeypatch, FakeResume(), threads=[]) == []


def test_a_long_inbox_is_capped(monkeypatch):
    many = [dict(THREADS[1], id=100 + i, last_message_id=i) for i in range(30)]
    boxes = _boxes(monkeypatch, FakeResume(), threads=many)
    assert len(boxes) == 8, "eight boxes, not thirty — each one costs a key row"


def test_the_page_no_longer_sends_anyone_to_a_messenger():
    src = Path(HERE.parent / "abex_livescreens.py").read_text(encoding="utf-8")
    body = src[src.index("def messages("):]
    body = body[:body.index("# ── History")]
    # The comment above the code still names the button it replaced, so this
    # looks for the BUTTON — a label inside a `btns` list — not the phrase.
    assert '["Open the messenger"' not in body
    assert '"/messages"' not in body, "no generic trip to a second inbox"
    # What DOES survive is a link to one named conversation. Reading what was
    # said before the reply is the single thing this screen cannot show, so the
    # sender's name goes there — a specific destination, not a second home.
    assert "/messages/t/" in body


def test_the_browser_posts_to_the_routes_that_exist():
    js = canvas_web.CANVAS_JS
    i = js.index("function wireReply")
    tail = js[i:i + 6000]
    assert "/api/messages/send" in tail
    assert "/api/messages/read" in tail
    assert "idempotency_key" in tail
    assert "do not re-send" in tail, "a network error is unknown, not failed"
    src = Path(HERE.parent / "messages_web.py").read_text(encoding="utf-8")
    for route in ("/api/messages/send", "/api/messages/read"):
        assert f'add_post("{route}"' in src


def test_marking_read_carries_no_key():
    js = canvas_web.CANVAS_JS
    i = js.index('post("/api/messages/read"')
    call = js[i:i + 200]
    assert "idempotency_key" not in call, (
        "the watermark write is MAX(old, new); a single-use key there can only fail")


def test_the_textarea_respects_the_servers_own_limit(monkeypatch):
    import messages_web
    boxes = _boxes(monkeypatch, FakeResume())
    assert boxes[0]["max"] == messages_web.BODY_MAX
    assert f'maxlength="{messages_web.BODY_MAX}"' in R._replybox({"reply": [boxes[0]]})
