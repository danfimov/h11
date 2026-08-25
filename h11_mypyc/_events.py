# High level events that make up HTTP/1.1 conversations. Loosely inspired by
# the corresponding events in hyper-h2:
#
#     http://python-hyper.org/h2/en/stable/api.html#events
#
# Don't subclass these. Stuff will break -- @final says so to mypyc too,
# which lets it call methods directly instead of through a vtable.

import re
from dataclasses import dataclass
from typing import Any, final

from h11_mypyc._abnf import method, request_target
from h11_mypyc._headers import Headers, normalize_and_validate
from h11_mypyc._util import Bytesifiable, LocalProtocolError, bytesify, validate

# Everything in __all__ gets re-exported as part of the h11 public API.
__all__ = [
    "Event",
    "Request",
    "InformationalResponse",
    "Response",
    "Data",
    "EndOfMessage",
    "ConnectionClosed",
]

method_re = re.compile(method.encode("ascii"))
request_target_re = re.compile(request_target.encode("ascii"))


class Event:
    """
    Base class for h11-mypyc events.
    """

    __slots__ = ()


@final
@dataclass(init=False, frozen=True, slots=True)
class Request(Event):
    """The beginning of an HTTP request.

    Attributes:
        method: An HTTP method, e.g. `b"GET"` or `b"POST"`. Always a byte
            string. Native strings containing only ascii characters and
            [bytes-like objects](https://docs.python.org/3/glossary.html#term-bytes-like-object) are automatically
            converted to byte strings.
        target: The target of an HTTP request, e.g. `b"/index.html"`, or one
            of the more exotic formats described in
            [RFC 7230, section 5.3](https://tools.ietf.org/html/rfc7230#section-5.3).
            Always a byte string. Native strings containing only ascii
            characters and [bytes-like objects](https://docs.python.org/3/glossary.html#term-bytes-like-object) are
            automatically converted to byte strings.
        headers: Request headers, represented as a list of (name, value)
            pairs. See [the header normalization rules](#headers-format) for
            details.
        http_version: The HTTP protocol version, represented as a byte string
            like `b"1.1"`. See
            [the HTTP version normalization rules](#http-version-format) for
            details.
    """

    method: bytes
    headers: Headers
    target: bytes
    http_version: bytes

    def __init__(
        self,
        *,
        method: Bytesifiable,
        headers: Headers | list[tuple[bytes, bytes]] | list[tuple[str, str]],
        target: Bytesifiable,
        http_version: Bytesifiable = b"1.1",
        _parsed: bool = False,
    ) -> None:
        if isinstance(headers, Headers):
            object.__setattr__(self, "headers", headers)
        else:
            object.__setattr__(self, "headers", normalize_and_validate(headers, _parsed=_parsed))
        if not _parsed:
            object.__setattr__(self, "method", bytesify(method))
            object.__setattr__(self, "target", bytesify(target))
            object.__setattr__(self, "http_version", bytesify(http_version))
        else:
            object.__setattr__(self, "method", method)
            object.__setattr__(self, "target", target)
            object.__setattr__(self, "http_version", http_version)

        # "A server MUST respond with a 400 (Bad Request) status code to any
        # HTTP/1.1 request message that lacks a Host header field and to any
        # request message that contains more than one Host header field or a
        # Host header field with an invalid field-value."
        # -- https://tools.ietf.org/html/rfc7230#section-5.4
        host_count = 0
        for name, value in self.headers:
            if name == b"host":
                host_count += 1
        if self.http_version == b"1.1" and host_count == 0:
            raise LocalProtocolError("Missing mandatory Host: header")
        if host_count > 1:
            raise LocalProtocolError("Found multiple Host: headers")

        validate(method_re, self.method, "Illegal method characters")
        validate(request_target_re, self.target, "Illegal target characters")

    # This is an unhashable type.
    __hash__ = None  # type: ignore


@dataclass(init=False, frozen=True, slots=True)
class _ResponseBase(Event):
    headers: Headers
    http_version: bytes
    reason: bytes
    status_code: int

    def __init__(
        self,
        *,
        headers: Headers | list[tuple[bytes, bytes]] | list[tuple[str, str]],
        # Not `int`: validated below to raise LocalProtocolError, which a
        # compiled signature would pre-empt with TypeError.
        status_code: Any,
        http_version: Bytesifiable = b"1.1",
        reason: Bytesifiable = b"",
        _parsed: bool = False,
    ) -> None:
        if isinstance(headers, Headers):
            object.__setattr__(self, "headers", headers)
        else:
            object.__setattr__(self, "headers", normalize_and_validate(headers, _parsed=_parsed))
        if not _parsed:
            object.__setattr__(self, "reason", bytesify(reason))
            object.__setattr__(self, "http_version", bytesify(http_version))
            if not isinstance(status_code, int):
                raise LocalProtocolError("status code must be integer")
            # Because IntEnum objects are instances of int, but aren't
            # duck-compatible (sigh), see gh-72.
            object.__setattr__(self, "status_code", int(status_code))
        else:
            object.__setattr__(self, "reason", reason)
            object.__setattr__(self, "http_version", http_version)
            object.__setattr__(self, "status_code", status_code)

        self.__post_init__()

    def __post_init__(self) -> None:
        pass

    # This is an unhashable type.
    __hash__ = None  # type: ignore


@final
@dataclass(init=False, frozen=True, slots=True)
class InformationalResponse(_ResponseBase):
    """An HTTP informational response.

    Attributes:
        status_code: The status code of this response, as an integer. For
            an [`InformationalResponse`][h11_mypyc.InformationalResponse], this is
            always in the range [100, 200).
        headers: Request headers, represented as a list of (name, value)
            pairs. See [the header normalization rules](#headers-format) for
            details.
        http_version: The HTTP protocol version, represented as a byte string
            like `b"1.1"`. See
            [the HTTP version normalization rules](#http-version-format) for
            details.
        reason: The reason phrase of this response, as a byte string. For
            example: `b"OK"`, or `b"Not Found"`.
    """

    def __post_init__(self) -> None:
        if not (100 <= self.status_code < 200):
            raise LocalProtocolError(
                f"InformationalResponse status_code should be in range [100, 200), not {self.status_code}"
            )

    # This is an unhashable type.
    __hash__ = None


@final
@dataclass(init=False, frozen=True, slots=True)
class Response(_ResponseBase):
    """The beginning of an HTTP response.

    Attributes:
        status_code: The status code of this response, as an integer. For a
            [`Response`][h11_mypyc.Response], this is always in the range
            [200, 1000).
        headers: Request headers, represented as a list of (name, value)
            pairs. See [the header normalization rules](#headers-format) for
            details.
        http_version: The HTTP protocol version, represented as a byte string
            like `b"1.1"`. See
            [the HTTP version normalization rules](#http-version-format) for
            details.
        reason: The reason phrase of this response, as a byte string. For
            example: `b"OK"`, or `b"Not Found"`.
    """

    def __post_init__(self) -> None:
        if not (200 <= self.status_code < 1000):
            raise LocalProtocolError(f"Response status_code should be in range [200, 1000), not {self.status_code}")

    # This is an unhashable type.
    __hash__ = None


@final
@dataclass(init=False, frozen=True, slots=True)
class Data(Event):
    """Part of an HTTP message body.

    Attributes:
        data:
            A [bytes-like object](https://docs.python.org/3/glossary.html#term-bytes-like-object)
            containing part of a message body. Or, if using the
            `combine=False` argument to
            [`Connection.send()`][h11_mypyc.Connection.send], then any object that
            your socket writing code knows what to do with, and for which
            calling [`len()`][len] returns the number of bytes that will be
            written -- see [Support for `sendfile()`](#sendfile) for details.
        chunk_start: A marker that indicates whether this data object is from
            the start of a chunked transfer encoding chunk. This field is
            ignored when a `Data` event is provided to
            [`Connection.send()`][h11_mypyc.Connection.send]: it is only valid on
            events emitted from
            [`Connection.next_event()`][h11_mypyc.Connection.next_event]. You
            probably shouldn't use this attribute at all; see
            [Chunked Transfer Encoding Delimiters](#chunk-delimiters-are-bad)
            for details.
        chunk_end: A marker that indicates whether this data object is the
            last for a given chunked transfer encoding chunk. This field is
            ignored when a `Data` event is provided to
            [`Connection.send()`][h11_mypyc.Connection.send]: it is only valid on
            events emitted from
            [`Connection.next_event()`][h11_mypyc.Connection.next_event]. You
            probably shouldn't use this attribute at all; see
            [Chunked Transfer Encoding Delimiters](#chunk-delimiters-are-bad)
            for details.
    """

    # Untyped on purpose: send_with_data_passthrough accepts an arbitrary
    # placeholder object here for sendfile (see the "sendfile" docs), and a narrower
    # annotation would be enforced at runtime and reject it.
    data: Any
    chunk_start: bool
    chunk_end: bool

    def __init__(self, data: Any, chunk_start: bool = False, chunk_end: bool = False) -> None:
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "chunk_start", chunk_start)
        object.__setattr__(self, "chunk_end", chunk_end)

    # This is an unhashable type.
    __hash__ = None  # type: ignore


# XX FIXME: "A recipient MUST ignore (or consider as an error) any fields that
# are forbidden to be sent in a trailer, since processing them as if they were
# present in the header section might bypass external security filters."
# https://svn.tools.ietf.org/svn/wg/httpbis/specs/rfc7230.html#chunked.trailer.part
# Unfortunately, the list of forbidden fields is long and vague :-/
@final
@dataclass(init=False, frozen=True, slots=True)
class EndOfMessage(Event):
    """The end of an HTTP message.

    Attributes:
        headers: Any trailing headers attached to this message, represented as
            a list of (name, value) pairs; defaults to `[]`. See
            [the header normalization rules](#headers-format) for details.

            Must be empty unless `Transfer-Encoding: chunked` is in use.
    """

    headers: Headers

    def __init__(
        self,
        *,
        headers: Headers | list[tuple[bytes, bytes]] | list[tuple[str, str]] | None = None,
        _parsed: bool = False,
    ) -> None:
        if headers is None:
            headers = Headers([])
        elif not isinstance(headers, Headers):
            headers = normalize_and_validate(headers, _parsed=_parsed)

        object.__setattr__(self, "headers", headers)

    # This is an unhashable type.
    __hash__ = None  # type: ignore


@final
@dataclass(frozen=True, slots=True)
class ConnectionClosed(Event):
    """This event indicates that the sender has closed their outgoing
    connection.

    Note that this does not necessarily mean that they can't *receive* further
    data, because TCP connections are composed of two one-way channels which
    can be closed independently. See [Closing connections](#closing) for
    details.

    This event has no fields.
    """

    pass
