from re import Match, Pattern
from typing import Any, NoReturn, TypeAlias

__all__ = [
    "ByteLike",
    "Bytesifiable",
    "ProtocolError",
    "LocalProtocolError",
    "RemoteProtocolError",
    "match_or_raise",
    "validate",
    "validate_and_group",
    "bytesify",
]

# Data off the wire is bytearray: ReceiveBuffer slices without copying.
ByteLike: TypeAlias = bytes | bytearray

# What the event constructors accept and hand to bytesify().
Bytesifiable: TypeAlias = bytes | bytearray | memoryview | str


class ProtocolError(Exception):
    """Exception indicating a violation of the HTTP/1.1 protocol.

    This is an abstract base class, with two concrete subclasses:
    [`LocalProtocolError`][h11_mypyc.LocalProtocolError], which indicates that you
    tried to do something that HTTP/1.1 says is illegal, and
    [`RemoteProtocolError`][h11_mypyc.RemoteProtocolError], which indicates that the
    remote peer tried to do something that HTTP/1.1 says is illegal. See
    [Error handling](#error-handling) for details.

    In addition to the normal [`Exception`][] features, it has one attribute.

    Attributes:
        error_status_hint: A suggestion as to what status code a server might
            use if this error occurred as part of a request.

            For a [`RemoteProtocolError`][h11_mypyc.RemoteProtocolError], this is
            useful as a suggestion for how you might want to respond to a
            misbehaving peer, if you're implementing a server.

            For a [`LocalProtocolError`][h11_mypyc.LocalProtocolError], this can be
            taken as a suggestion for how your peer might have responded to
            *you* if h11-mypyc had allowed you to continue.

            The default is 400 Bad Request, a generic catch-all for protocol
            violations.
    """

    def __init__(self, msg: str, error_status_hint: int = 400) -> None:
        if type(self) is ProtocolError:
            raise TypeError("tried to directly instantiate ProtocolError")
        Exception.__init__(self, msg)
        self.error_status_hint = error_status_hint


# Strategy: there are a number of public APIs where a LocalProtocolError can
# be raised (send(), all the different event constructors, ...), and only one
# public API where RemoteProtocolError can be raised
# (receive_data()). Therefore we always raise LocalProtocolError internally,
# and then receive_data will translate this into a RemoteProtocolError.
#
# Internally:
#   LocalProtocolError is the generic "ProtocolError".
# Externally:
#   LocalProtocolError is for local errors and RemoteProtocolError is for
#   remote errors.
class LocalProtocolError(ProtocolError):
    def _reraise_as_remote_protocol_error(self) -> NoReturn:
        # After catching a LocalProtocolError, use this method to re-raise it
        # as a RemoteProtocolError. This method must be called from inside an
        # except: block.
        #
        # An easy way to get an equivalent RemoteProtocolError is just to
        # modify 'self' in place.
        self.__class__ = RemoteProtocolError  # type: ignore
        # But the re-raising is somewhat non-trivial -- you might think that
        # now that we've modified the in-flight exception object, that just
        # doing 'raise' to re-raise it would be enough. But it turns out that
        # this doesn't work, because Python tracks the exception type
        # (exc_info[0]) separately from the exception object (exc_info[1]),
        # and we only modified the latter. So we really do need to re-raise
        # the new type explicitly.
        # On py3, the traceback is part of the exception object, so our
        # in-place modification preserved it and we can just re-raise:
        raise self


class RemoteProtocolError(ProtocolError):
    pass


def validate(regex: Pattern[bytes], data: ByteLike, msg: str = "malformed data", *format_args: Any) -> None:
    if not regex.fullmatch(data):
        if format_args:
            msg = msg.format(*format_args)
        raise LocalProtocolError(msg)


def match_or_raise(
    regex: Pattern[bytes], data: ByteLike, msg: str = "malformed data", *format_args: Any
) -> Match[bytes]:
    # For callers that want one or two named groups. Reading them off the match
    # avoids the dict that validate_and_group() builds per call.
    match = regex.fullmatch(data)
    if not match:
        if format_args:
            msg = msg.format(*format_args)
        raise LocalProtocolError(msg)
    return match


def validate_and_group(
    regex: Pattern[bytes], data: ByteLike, msg: str = "malformed data", *format_args: Any
) -> dict[str, bytes]:
    match = match_or_raise(regex, data, msg, *format_args)
    # Unmatched optional groups are None; drop them so the return type holds.
    # Callers read optional groups with .get() and a default.
    return {name: value for name, value in match.groupdict().items() if value is not None}


# Sentinel values
#
# - Inherit identity-based comparison and hashing from object
# - Are used as classes, never instantiated: `conn.our_state is IDLE`
#
# Plain base class, not a metaclass: mypyc cannot compile custom metaclasses.
# Error messages spell the names out with __name__ instead of relying on repr.


class Sentinel:
    pass


# Used for methods, request targets, HTTP versions, header names, and header
# values. Accepts ascii-strings, or bytes/bytearray/memoryview/..., and always
# returns bytes.
def bytesify(s: Bytesifiable | int) -> bytes:
    # Fast-path:
    if type(s) is bytes:
        return s
    if isinstance(s, str):
        s = s.encode("ascii")
    if isinstance(s, int):
        raise TypeError("expected bytes-like object, not int")
    return bytes(s)
