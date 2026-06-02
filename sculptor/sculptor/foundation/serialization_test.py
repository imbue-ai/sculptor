from sculptor.foundation.serialization import SerializedException


def test_build_with_bytes_arg_does_not_raise() -> None:
    """Regression: UnicodeDecodeError has bytes in its args.

    SerializedException.build() must handle non-JSON-serializable types
    (like bytes) in exception args without raising a pydantic ValidationError.
    """
    try:
        b"\x94 invalid utf-8 data".decode("utf-8")
    except UnicodeDecodeError as e:
        # UnicodeDecodeError.args includes the raw bytes object
        assert any(isinstance(a, bytes) for a in e.args)
        result = SerializedException.build(e)
        assert result.exception == "UnicodeDecodeError"
        # The bytes arg should be converted to a str representation
        for arg in result.args:
            assert not isinstance(arg, bytes)


def test_build_with_standard_exception() -> None:
    """SerializedException.build() works for normal exceptions with string args."""
    try:
        raise ValueError("test error", 42, {"key": "value"})
    except ValueError as e:
        result = SerializedException.build(e)
        assert result.exception == "ValueError"
        assert result.args == ("test error", 42, {"key": "value"})
