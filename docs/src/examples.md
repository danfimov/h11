# Examples

<!--
  If we add any more examples then we should probably split this out
  into separate pages for each example.
-->

You can also find these in the
[`examples/` directory of a source checkout](https://github.com/danfimov/h11/tree/master/examples).

## Minimal client, using synchronous I/O

```python title="examples/basic-client.py"
--8<-- "basic-client.py"
```

## Fairly complete server with error handling, using Trio for async I/O

```python title="examples/trio-server.py"
--8<-- "trio-server.py"
```
