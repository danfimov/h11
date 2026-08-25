import re

import pytest
from h11_mypyc._abnf import field_name, field_value
from h11_mypyc._events import Request
from h11_mypyc._headers import (
    get_comma_header,
    has_expect_100_continue,
    normalize_and_validate,
    set_comma_header,
)
from h11_mypyc._util import LocalProtocolError


def test_normalize_and_validate() -> None:
    assert normalize_and_validate([("foo", "bar")]) == [(b"foo", b"bar")]
    assert normalize_and_validate([(b"foo", b"bar")]) == [(b"foo", b"bar")]

    # no leading/trailing whitespace in names
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([(b"foo ", "bar")])
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([(b" foo", "bar")])

    # no weird characters in names
    with pytest.raises(LocalProtocolError) as excinfo:
        normalize_and_validate([(b"foo bar", b"baz")])
    assert "foo bar" in str(excinfo.value)
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([(b"foo\x00bar", b"baz")])
    # Not even 8-bit characters:
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([(b"foo\xffbar", b"baz")])
    # And not even the control characters we allow in values:
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([(b"foo\x01bar", b"baz")])

    # no return or NUL characters in values
    with pytest.raises(LocalProtocolError) as excinfo:
        normalize_and_validate([("foo", "bar\rbaz")])
    assert "bar\\rbaz" in str(excinfo.value)
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("foo", "bar\nbaz")])
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("foo", "bar\x00baz")])
    # no leading/trailing whitespace
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("foo", "barbaz  ")])
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("foo", "  barbaz")])
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("foo", "barbaz\t")])
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("foo", "\tbarbaz")])

    # content-length
    assert normalize_and_validate([("Content-Length", "1")]) == [(b"content-length", b"1")]
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("Content-Length", "asdf")])
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("Content-Length", "1x")])
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("Content-Length", "1"), ("Content-Length", "2")])
    assert normalize_and_validate([("Content-Length", "0"), ("Content-Length", "0")]) == [(b"content-length", b"0")]
    assert normalize_and_validate([("Content-Length", "0 , 0")]) == [(b"content-length", b"0")]
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("Content-Length", "1"), ("Content-Length", "1"), ("Content-Length", "2")])
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("Content-Length", "1 , 1,2")])
    with pytest.raises(LocalProtocolError):
        normalize_and_validate([("Content-Length", "1" * 21)])  # 1 billion TB

    # transfer-encoding
    assert normalize_and_validate([("Transfer-Encoding", "chunked")]) == [(b"transfer-encoding", b"chunked")]
    assert normalize_and_validate([("Transfer-Encoding", "cHuNkEd")]) == [(b"transfer-encoding", b"chunked")]
    with pytest.raises(LocalProtocolError) as excinfo:
        normalize_and_validate([("Transfer-Encoding", "gzip")])
    assert excinfo.value.error_status_hint == 501  # Not Implemented
    with pytest.raises(LocalProtocolError) as excinfo:
        normalize_and_validate([("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "gzip")])
    assert excinfo.value.error_status_hint == 501  # Not Implemented


def test_get_set_comma_header() -> None:
    headers = normalize_and_validate(
        [
            ("Connection", "close"),
            ("whatever", "something"),
            ("connectiON", "fOo,, , BAR"),
        ]
    )

    assert get_comma_header(headers, b"connection") == [b"close", b"foo", b"bar"]

    headers = set_comma_header(headers, b"newthing", [b"a", b"b"])

    with pytest.raises(LocalProtocolError):
        set_comma_header(headers, b"newthing", [b"  a", b"b"])

    assert headers == [
        (b"connection", b"close"),
        (b"whatever", b"something"),
        (b"connection", b"fOo,, , BAR"),
        (b"newthing", b"a"),
        (b"newthing", b"b"),
    ]

    headers = set_comma_header(headers, b"whatever", [b"different thing"])

    assert headers == [
        (b"connection", b"close"),
        (b"connection", b"fOo,, , BAR"),
        (b"newthing", b"a"),
        (b"newthing", b"b"),
        (b"whatever", b"different thing"),
    ]


def test_has_100_continue() -> None:
    assert has_expect_100_continue(
        Request(
            method="GET",
            target="/",
            headers=[("Host", "example.com"), ("Expect", "100-continue")],
        )
    )
    assert not has_expect_100_continue(Request(method="GET", target="/", headers=[("Host", "example.com")]))
    # Case insensitive
    assert has_expect_100_continue(
        Request(
            method="GET",
            target="/",
            headers=[("Host", "example.com"), ("Expect", "100-Continue")],
        )
    )
    # Doesn't work in HTTP/1.0
    assert not has_expect_100_continue(
        Request(
            method="GET",
            target="/",
            headers=[("Host", "example.com"), ("Expect", "100-continue")],
            http_version="1.0",
        )
    )


def test_field_validation_matches_abnf() -> None:
    # normalize_and_validate checks header names and values with byte-class
    # tests rather than the ABNF regexes, for speed. This pins the two
    # together: if _abnf.field_name / field_value ever change, or the fast
    # path drifts, the sets of accepted byte strings must still be identical.
    name_re = re.compile(field_name.encode("ascii"))
    value_re = re.compile(field_value.encode("ascii"))

    def accepted(name: bytes, value: bytes) -> bool:
        try:
            normalize_and_validate([(name, value)])
        except LocalProtocolError:
            return False
        return True

    candidates = [bytes([i]) for i in range(256)]
    candidates += [bytes([i, j]) for i in range(256) for j in range(0, 256, 7)]
    candidates += [b"", b"abc", b"a b", b"a  b", b"a\tb", b" ab", b"ab ", b"\tab", b"ab\t"]

    for candidate in candidates:
        assert accepted(candidate, b"ok") == bool(name_re.fullmatch(candidate)), f"header name {candidate!r}"
        assert accepted(b"x-test", candidate) == bool(value_re.fullmatch(candidate)), f"header value {candidate!r}"
