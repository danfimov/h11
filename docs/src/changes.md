# History of changes

## H11 MyPyc 0.17.0 (2026-08-25)

First release of the fork. Everything below is relative to upstream h11 0.16.0;
the protocol behaviour is unchanged, and the whole upstream test suite passes against both the interpreted and the compiled build.

### Compiled builds

- The package is compiled with [mypyc](https://mypyc.readthedocs.io/). On the
  benchmark suite this is worth about **1.9x** (27,700 → 52,900 requests/sec on the reference machine).
- Both a compiled wheel and a pure-Python `py3-none-any` wheel are published.
  Installers pick the compiled build when a wheel matches the interpreter and
  fall back to the pure one otherwise, so PyPy and platforms without a wheel
  keep working. No configuration is needed on the consuming side.
- Building from an sdist produces the pure-Python build unless `H11_MYPYC=1` is set, so a missing compiler never breaks an install.

### Backwards-incompatible changes

- **The import name is `h11_mypyc`, not `h11`.** The distribution deliberately
  does not ship an `h11/` directory: two distributions writing to the same
  directory overwrite each other silently, and uninstalling either one takes
  the other's files with it. Under the new name the fork and upstream h11 can be installed side by side.
- `PRODUCT_ID` is now `python-h11-mypyc/<version>` rather than
  `python-h11/<version>`, so the fork does not report itself as upstream in `User-Agent:` and `Server:` headers.
- The sentinels (`NEED_DATA`, `PAUSED`, `IDLE`, ...) are no longer instances of
  themselves: `type(h11_mypyc.NEED_DATA) is h11_mypyc.NEED_DATA` is now false.
  That property came from a custom metaclass, which mypyc cannot compile.
  `is` comparisons, dict keys and `Type[Sentinel]` annotations are unaffected.
- `Headers` no longer inherits from `collections.abc.Sequence`; it is registered
  as a virtual subclass instead, so `isinstance(headers, Sequence)` still holds.
  A compiled class inheriting an ABC shares the base's `isinstance` cache, which
  silently corrupts `isinstance` in both directions across the process.
- `Event` no longer inherits from `abc.ABC`, and the event classes use
  `@dataclass(slots=True)` rather than a hand-written `__slots__`. The events are
  still frozen, still without `__dict__`, and still work with
  `dataclasses.fields()` and `dataclasses.replace()`.
- Several annotations were widened to match what the code has always accepted at
  runtime, because mypyc turns annotations into runtime checks:
  `Data.data` and `Response.status_code` are now `Any` (to keep the documented
  sendfile pass-through and the `LocalProtocolError` for a non-integer status
  code), and the event constructors accept any bytes-like object.
- `validate()` no longer returns the match groups; use `match_or_raise()` or
  `validate_and_group()` for those.
- Requires Python 3.10 or newer.

### Performance

Most of the work below helps the pure-Python build too, which is about 17% faster than upstream on the same benchmark:

- Header names and values are checked with byte-class tests instead of regexes.
  The equivalence to the ABNF patterns is pinned by a differential test.
- `_obsolete_line_fold()` no longer runs a regex on every header line; obs-fold continuations are detected from the first byte.
- Header parsing no longer builds a dict per header line just to read two fields out of it.
- Sentinel and event classes are `@final`, which lets mypyc call their methods directly rather than through a vtable.

### Miscellaneous internal changes

- Packaging metadata moved from `setup.py` to `pyproject.toml`; `setup.py` remains only to declare the mypyc extension modules.
- Added a benchmark suite (`tests/test_benchmarks.py`, run with `make bench-py`) covering header parsing, the state machine and whole request/response cycles.

## H11 0.16.0 (2025-04-23)

### Security fix

Reject certain malformed `Transfer-Encoding: chunked` bodies that were previously accepted. These could have enabled request-smuggling attacks when an h11-based HTTP server was placed behind a load balancer with a matching bug in its `chunked` handling.

Advisory with more details: https://github.com/python-hyper/h11/security/advisories/GHSA-vqfr-h8mv-ghfj

Reported by: Jeppe Bonde Weikop

## H11 0.15.0 (2025-04-23)

### Bugfixes

- Reject Content-Lengths >= 1 zettabyte (1 billion terabytes) early, [without attempting to parse the integer](https://docs.python.org/3/library/stdtypes.html#integer-string-conversion-length-limitation) ([#181](https://github.com/python-hyper/h11/issues/181))

### Miscellaneous internal changes

- Remove the `tests` folder from wheel files. This reduces the zipped file size by 20KB (about 30%). ([#158](https://github.com/python-hyper/h11/issues/158))

## H11 0.14.0 (2022-09-25)

### Features

- Allow additional trailing whitespace in chunk headers for additional
  compatibility with existing servers. ([#133](https://github.com/python-hyper/h11/issues/133))
- Improve the type hints for Sentinel types, which should make it
  easier to type hint h11 usage. ([#151](https://github.com/python-hyper/h11/pull/151) & [#144](https://github.com/python-hyper/h11/pull/144)))

### Deprecations and Removals

- Python 3.6 support is removed. h11 now requires Python>=3.7
  including PyPy 3.  Users running `pip install h11` on Python 2 will
  automatically get the last Python 2-compatible version. ([#138](https://github.com/python-hyper/h11/issues/138))

## v0.13.0 (2022-01-19)

### Features

- Clarify that the Headers class is a Sequence and inherit from the
  collections Sequence abstract base class to also indicate this (and
  gain the mixin methods). See also #104. ([#112](https://github.com/python-hyper/h11/issues/112))
- Switch event classes to dataclasses for easier typing and slightly
  improved performance. ([#124](https://github.com/python-hyper/h11/issues/124))
- Shorten traceback of protocol errors for easier readability ([#132](https://github.com/python-hyper/h11/pull/132)).
- Add typing including a PEP 561 marker for usage by type checkers
  ([#135](https://github.com/python-hyper/h11/pull/135)).
- Expand the allowed status codes to [0, 999] from [0, 600] ([#134](https://github.com/python-hyper/h11/issues/134)).

### Backwards **in**compatible changes

- Ensure request method is a valid token ([#141](https://github.com/python-hyper/h11/pull/141)).

## v0.12.0 (2021-01-01)

### Features

- Added support for servers with broken line endings.

  After this change h11 accepts both `\r\n` and `\n` as a headers
  delimiter. ([#7](https://github.com/python-hyper/h11/issues/7))
- Add early detection of invalid http data when request line starts
  with binary ([#122](https://github.com/python-hyper/h11/issues/122))

### Deprecations and Removals

- Python 2.7 and PyPy 2 support is removed. h11 now requires
  Python>=3.6 including PyPy 3.  Users running `pip install h11` on
  Python 2 will automatically get the last Python 2-compatible
  version. ([#114](https://github.com/python-hyper/h11/issues/114))

## v0.11.0 (2020-10-05)

New features:

- h11 now stores and makes available the raw header name as
  received. In addition h11 will write out header names with the same
  casing as passed to it. This allows compatibility with systems that
  expect titlecased header names. See [#31](https://github.com/python-hyper/h11/issues/31).
- Multiple content length headers are now merged into a single header
  if all the values are equal, if any are unequal a LocalProtocol
  error is raised (as before). See [#92](https://github.com/python-hyper/h11/issues/92).

Backwards **in**compatible changes:

- Headers added by h11, rather than passed to it, now have titlecased
  names. Whilst this should help compatibility it replaces the
  previous lowercased header names.

## v0.10.0 (2020-08-14)

Other changes:

- Drop support for Python 3.4.
- Support Python 3.8.
- Make error messages returned by match failures less ambiguous ([#98](https://github.com/python-hyper/h11/issues/98)).

## v0.9.0 (2019-05-15)

Bug fixes:

- Allow a broader range of characters in header values. This violates
  the RFC, but is apparently required for compatibility with
  real-world code, like Google Analytics cookies ([#57](https://github.com/python-hyper/h11/issues/57), [#58](https://github.com/python-hyper/h11/issues/58)).
- Validate incoming and outgoing request paths for invalid
  characters. This prevents a variety of potential security issues
  that have affected other HTTP clients. ([#69](https://github.com/python-hyper/h11/pull/69)).
- Force status codes to be integers, thereby allowing stdlib
  HTTPStatus IntEnums to be used when constructing responses ([#72](https://github.com/python-hyper/h11/issues/72)).

Other changes:

- Make all sentinel values inspectable by IDEs, and split
  `SEND_BODY_DONE` into `SEND_BODY`, and `DONE` ([#75](https://github.com/python-hyper/h11/pull/75)).
- Drop support for Python 3.3.
- LocalProtocolError raised in start_next_cycle now shows states for
  more informative errors ([#80](https://github.com/python-hyper/h11/issues/80)).

## v0.8.1 (2018-04-14)

Bug fixes:

- Always return headers as `bytes` objects ([#60](https://github.com/python-hyper/h11/issues/60))

Other changes:

- Added proper license notices to the Javascript used in our
  documentation ([#61](https://github.com/python-hyper/h11/issues/60))

## v0.8.0 (2018-03-20)

Backwards **in**compatible changes:

- h11 now performs stricter validation on outgoing header names and
  header values: illegal characters are now rejected (example: you
  can't put a newline into an HTTP header), and header values with
  leading/trailing whitespace are also rejected (previously h11 would
  silently discard the whitespace). All these checks were already
  performed on incoming headers; this just extends that to outgoing
  headers.

New features:

- New method `Connection.send_failed()`, to notify a
  `Connection` object when data returned from
  `Connection.send()` was *not* sent.

Bug fixes:

- Make sure that when computing the framing headers for HEAD
  responses, we produce the same results as we would for the
  corresponding GET.

- Error out if a request has multiple Host: headers.

- Send the Host: header first, as recommended by RFC 7230.

- The Expect: header [is case-insensitive](https://tools.ietf.org/html/rfc7231#section-5.1.1), so use
  case-insensitive matching when looking for 100-continue.

Other changes:

- Better error messages in several cases.

- Provide correct `error_status_hint` in exception raised when
  encountering an invalid `Transfer-Encoding` header.

- For better compatibility with broken servers, h11 now tolerates
  responses where the reason phrase is missing (not just empty).

- Various optimizations and documentation improvements.

## v0.7.0 (2016-11-25)

New features (backwards compatible):

- Made it so that sentinels are [instances of themselves](api.md#special-constants), to enable certain dispatch tricks on
  the return value of `Connection.next_event()` (see [issue #8](https://github.com/python-hyper/h11/issues/8) for discussion).

- Added `Data.chunk_start` and `Data.chunk_end` properties
  to the `Data` event. These provide the user information
  about where chunk delimiters are in the data stream from the remote
  peer when chunked transfer encoding is in use. You [probably shouldn't use these](api.md#chunk-delimiters-are-bad), but sometimes
  there's no alternative (see [issue #19](https://github.com/python-hyper/h11/issues/19) for discussion).

- Expose `Response.reason` attribute, making it possible to read
  or set the textual "reason phrase" on responses ([issue #13](https://github.com/python-hyper/h11/pull/13)).

Bug fixes:

- Fix the error message given when a call to an event constructor is
  missing a required keyword argument ([issue #14](https://github.com/python-hyper/h11/issues/14)).

- Fixed encoding of empty `Data` events (`Data(data=b"")`)
  when using chunked encoding ([issue #21](https://github.com/python-hyper/h11/issues/21)).

## v0.6.0 (2016-10-24)

This is the first release since we started using h11 to write
non-trivial server code, and this experience triggered a number of
substantial API changes.

Backwards **in**compatible changes:

- Split the old `receive_data()` into the new
  `Connection.receive_data()` and
  `Connection.next_event()`, and replaced the old `Paused`
  pseudo-event with the new `NEED_DATA` and `PAUSED`
  sentinels.

- Simplified the API by replacing the old `Connection.state_of()`,
  `Connection.client_state`, `Connection.server_state` with
  the new `Connection.states`.

- Renamed the old `prepare_to_reuse()` to the new
  `Connection.start_next_cycle()`.

- Removed the `Paused` pseudo-event.

Backwards compatible changes:

- State machine: added a `DONE` -> `MUST_CLOSE` transition
  triggered by our peer being in the `ERROR` state.

- Split `ProtocolError` into `LocalProtocolError` and
  `RemoteProtocolError` (see [Error handling](api.md#error-handling)). Use case: HTTP
  servers want to be able to distinguish between an error that
  originates locally (which produce a 500 status code) versus errors
  caused by remote misbehavior (which produce a 4xx status code).

- Changed the `PRODUCT_ID` from `h11/<verson>` to
  `python-h11/<version>`. (This is similar to what requests uses,
  and much more searchable than plain h11.)

Other changes:

- Added a minimal benchmark suite, and used it to make a few small
  optimizations (maybe ~20% speedup?).

## v0.5.0 (2016-05-14)

- Initial release.
