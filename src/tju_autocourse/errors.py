"""Sanitized errors crossing the network/application boundary."""


class AutoCourseError(RuntimeError):
    pass


class AuthenticationError(AutoCourseError):
    pass


class TransportError(AutoCourseError):
    pass


class ProtocolError(AutoCourseError):
    pass


class Cancelled(AutoCourseError):
    """The user interrupted a running selection session."""
