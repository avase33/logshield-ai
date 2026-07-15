from logshield.parsing.masking import mask, extract_variables
from logshield.parsing.drain import DrainParser


def test_mask_replaces_variables():
    line = "2023-08-01T12:04:11Z connection to 10.0.4.7:8080 failed after 3 retries (err=0x1F)"
    t = mask(line)
    assert "<TIMESTAMP>" in t
    assert "<IP>:<PORT>" in t
    assert "<HEX>" in t
    assert "10.0.4.7" not in t and "8080" not in t


def test_mask_is_stable_across_variable_changes():
    a = mask('10.0.0.1 - - [2023-08-01T12:00:00] "GET /api/v1/users/42 HTTP/1.1" 200 512')
    b = mask('10.9.9.9 - - [2023-08-01T13:11:22] "GET /api/v1/users/99 HTTP/1.1" 200 4096')
    assert a == b   # same template despite different IPs/ids/sizes


def test_extract_variables():
    v = extract_variables("user from 10.0.0.5 at 2023-08-01T00:00:00 took 45ms")
    assert v.get("IP") == ["10.0.0.5"]
    assert "TIMESTAMP" in v
    assert "DURATION" in v


def test_drain_groups_similar_lines():
    d = DrainParser(sim_threshold=0.4)
    r1 = d.add(mask("connection to 10.0.0.1 failed after 3 retries"))
    r2 = d.add(mask("connection to 10.0.0.9 failed after 8 retries"))
    assert r1.is_new is True
    assert r2.is_new is False          # merged into the same template
    assert r1.template_id == r2.template_id or r2.matched_count == 2


def test_drain_new_template_is_new():
    d = DrainParser()
    d.add("user login succeeded for account <NUM>")
    r = d.add("kernel panic unable to handle <HEX>")
    assert r.is_new is True
