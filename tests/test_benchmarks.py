import pytest
from h11_mypyc import (
    CLIENT,
    DONE,
    NEED_DATA,
    SERVER,
    Connection,
    Data,
    EndOfMessage,
    Request,
    Response,
)
from h11_mypyc._headers import Headers, get_comma_header, normalize_and_validate
from h11_mypyc._readers import _decode_header_lines
from h11_mypyc._receivebuffer import ReceiveBuffer

# A realistic browser request header set. Realistic data matters here: header
# validation cost depends on value length and on how many values contain
# separators, so synthetic b"a: b" pairs would flatter the benchmark.
BROWSER_HEADERS: list[tuple[bytes, bytes]] = [
    (b"Host", b"example.com"),
    (b"User-Agent", b"Mozilla/5.0 (X11; Linux x86_64; rv:45.0) Gecko/20100101 Firefox/45.0"),
    (b"Accept", b"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    (b"Accept-Language", b"en-US,en;q=0.5"),
    (b"Accept-Encoding", b"gzip, deflate, br"),
    (b"DNT", b"1"),
    (b"Cookie", b"ID=" + b"A" * 200),
    (b"Connection", b"keep-alive"),
]

RESPONSE_HEADERS: list[tuple[bytes, bytes]] = [
    (b"Cache-Control", b"private, max-age=0"),
    (b"Content-Encoding", b"gzip"),
    (b"Content-Type", b"text/html; charset=UTF-8"),
    (b"Date", b"Fri, 20 May 2016 09:23:41 GMT"),
    (b"Expires", b"-1"),
    (b"Server", b"gws"),
    (b"X-Frame-Options", b"SAMEORIGIN"),
    (b"X-XSS-Protection", b"1; mode=block"),
]

TYPICAL_HEADER_COUNT = 8
TYPICAL_BODY_SIZE = 1024

HEADER_COUNTS = [
    pytest.param(3, id="3headers"),
    pytest.param(TYPICAL_HEADER_COUNT, id="8headers"),
    pytest.param(24, id="24headers"),
]

BODY_SIZES = [
    pytest.param(0, id="nobody"),
    pytest.param(TYPICAL_BODY_SIZE, id="1KiB"),
    pytest.param(64 * 1024, id="64KiB"),
]


def _sized_headers(count: int) -> list[tuple[bytes, bytes]]:
    """A header list of exactly `count` pairs, Host first so Requests stay legal."""
    out = list(BROWSER_HEADERS[:count])
    while len(out) < count:
        i = len(out)
        out.append((b"X-Custom-%d" % i, b"value-%d; q=0.5, other" % i))
    return out


def _raw_request(count: int) -> bytes:
    lines = [b"%s: %s" % pair for pair in _sized_headers(count)]
    return b"GET /path/to/thing HTTP/1.1\r\n" + b"\r\n".join(lines) + b"\r\n\r\n"


def _response_headers(body_length: int) -> list[tuple[bytes, bytes]]:
    return [*RESPONSE_HEADERS, (b"Content-Length", b"%d" % body_length)]


def _drain_request(conn: Connection) -> None:
    while type(conn.next_event()) is not EndOfMessage:
        pass


@pytest.fixture(scope="session", params=HEADER_COUNTS)
def header_pairs(request: pytest.FixtureRequest) -> list[tuple[bytes, bytes]]:
    return _sized_headers(request.param)


@pytest.fixture(scope="session", params=HEADER_COUNTS)
def header_lines(request: pytest.FixtureRequest) -> list[bytes]:
    """Raw `name: value` lines, as the reader sees them off the wire."""
    return [b"%s: %s" % pair for pair in _sized_headers(request.param)]


@pytest.fixture(scope="session", params=HEADER_COUNTS)
def raw_request(request: pytest.FixtureRequest) -> bytes:
    return _raw_request(request.param)


@pytest.fixture(scope="session")
def typical_request() -> bytes:
    return _raw_request(TYPICAL_HEADER_COUNT)


@pytest.fixture(scope="session", params=BODY_SIZES)
def body(request: pytest.FixtureRequest) -> bytes:
    return b"x" * request.param


@pytest.fixture(scope="session")
def typical_body() -> bytes:
    return b"x" * TYPICAL_BODY_SIZE


@pytest.fixture(scope="session")
def normalized_headers() -> Headers:
    return normalize_and_validate(BROWSER_HEADERS)


@pytest.fixture(scope="session")
def raw_response(body: bytes) -> bytes:
    lines = [b"%s: %s" % pair for pair in _response_headers(len(body))]
    return b"HTTP/1.1 200 OK\r\n" + b"\r\n".join(lines) + b"\r\n\r\n" + body


class TestHotSpots:
    """Individual functions the profiler singled out."""

    @pytest.mark.benchmark
    def test_decode_header_lines(self, header_lines: list[bytes]) -> None:
        """Receive path: a regex per header line, plus obs-fold handling."""
        decoded = list(_decode_header_lines(header_lines))
        assert len(decoded) == len(header_lines)

    @pytest.mark.benchmark
    def test_normalize_and_validate(self, header_pairs: list[tuple[bytes, bytes]]) -> None:
        """Send path: bytesify, syntax validation and lowercasing, per header."""
        headers = normalize_and_validate(header_pairs)
        assert len(headers) == len(header_pairs)

    @pytest.mark.benchmark
    def test_normalize_and_validate_parsed(self, header_pairs: list[tuple[bytes, bytes]]) -> None:
        """The _parsed=True path, which skips validation already done on the wire.

        The gap against test_normalize_and_validate is what validation costs.
        """
        lowered = [(name.lower(), value) for name, value in header_pairs]
        headers = normalize_and_validate(lowered, _parsed=True)
        assert len(headers) == len(header_pairs)

    @pytest.mark.benchmark
    def test_get_comma_header_hit(self, normalized_headers: Headers) -> None:
        """A lookup that finds something: full scan, then split and strip."""
        assert get_comma_header(normalized_headers, b"connection") == [b"keep-alive"]

    @pytest.mark.benchmark
    def test_get_comma_header_miss(self, normalized_headers: Headers) -> None:
        """A lookup that finds nothing -- half of the 10 per round-trip look like this."""
        assert get_comma_header(normalized_headers, b"transfer-encoding") == []

    @pytest.mark.benchmark
    def test_receivebuffer_extract_lines(self, raw_request: bytes) -> None:
        """Splitting the header block out of the receive buffer."""
        buf = ReceiveBuffer()
        buf += raw_request
        lines = buf.maybe_extract_lines()
        assert lines is not None


class TestPipelineHalves:
    """Reading and writing measured apart, to tell which side moved."""

    @pytest.mark.benchmark
    def test_parse_request(self, raw_request: bytes) -> None:
        conn = Connection(SERVER)
        conn.receive_data(raw_request)
        assert type(conn.next_event()) is Request

    @pytest.mark.benchmark
    def test_send_response(self, typical_request: bytes, typical_body: bytes) -> None:
        conn = Connection(SERVER)
        conn.receive_data(typical_request)
        _drain_request(conn)
        written = conn.send(Response(status_code=200, headers=_response_headers(len(typical_body))))
        assert written is not None and written.startswith(b"HTTP/1.1 200")


class TestPipeline:
    """Whole request/response cycles."""

    @pytest.mark.benchmark
    def test_server_roundtrip(self, raw_request: bytes, typical_body: bytes) -> None:
        """Header count is the axis: parse a request, then write a full response."""
        conn = Connection(SERVER)
        conn.receive_data(raw_request)
        _drain_request(conn)
        conn.send(Response(status_code=200, headers=_response_headers(len(typical_body))))
        conn.send(Data(data=typical_body))
        conn.send(EndOfMessage())
        assert conn.our_state is DONE

    @pytest.mark.benchmark
    def test_server_roundtrip_body(self, typical_request: bytes, body: bytes) -> None:
        """Body size is the axis, so this measures framing and buffer copies."""
        conn = Connection(SERVER)
        conn.receive_data(typical_request)
        _drain_request(conn)
        conn.send(Response(status_code=200, headers=_response_headers(len(body))))
        conn.send(Data(data=body))
        conn.send(EndOfMessage())
        assert conn.our_state is DONE

    @pytest.mark.benchmark
    def test_server_roundtrip_chunked(self, typical_request: bytes, body: bytes) -> None:
        """Chunked framing rather than Content-Length: a different writer path."""
        conn = Connection(SERVER)
        conn.receive_data(typical_request)
        _drain_request(conn)
        conn.send(Response(status_code=200, headers=[*RESPONSE_HEADERS, (b"Transfer-Encoding", b"chunked")]))
        conn.send(Data(data=body))
        conn.send(EndOfMessage())
        assert conn.our_state is DONE

    @pytest.mark.benchmark
    def test_server_roundtrip_keepalive(self, typical_request: bytes, typical_body: bytes) -> None:
        """Ten round-trips on one connection, as a keep-alive server does.

        Amortizes connection setup away and exercises start_next_cycle().
        """
        conn = Connection(SERVER)
        headers = _response_headers(len(typical_body))
        for _ in range(10):
            conn.receive_data(typical_request)
            _drain_request(conn)
            conn.send(Response(status_code=200, headers=headers))
            conn.send(Data(data=typical_body))
            conn.send(EndOfMessage())
            conn.start_next_cycle()
        assert conn.our_state is not DONE

    @pytest.mark.benchmark
    def test_client_roundtrip(self, raw_response: bytes, body: bytes) -> None:
        """The client half: serialize a request, then parse a whole response."""
        conn = Connection(CLIENT)
        conn.send(Request(method="GET", target="/path/to/thing", headers=BROWSER_HEADERS))
        conn.send(EndOfMessage())
        conn.receive_data(raw_response)
        received = 0
        while True:
            event = conn.next_event()
            if event is NEED_DATA or type(event) is EndOfMessage:
                break
            if type(event) is Data:
                received += len(event.data)
        assert received == len(body)
