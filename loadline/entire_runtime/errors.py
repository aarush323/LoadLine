"""Errors from provisioning or invoking Entire."""


class EntireSetupError(Exception):
    """A setup failure the user can act on. ``repair`` is the next step."""

    def __init__(self, message: str, repair: str) -> None:
        super().__init__(message)
        self.repair = repair


class PlatformUnsupported(EntireSetupError):
    pass


class GitIncompatible(EntireSetupError):
    pass


class IntegrityError(EntireSetupError):
    pass


class DownloadError(EntireSetupError):
    pass


class GraphInvocationError(Exception):
    def __init__(self, message: str, *, timed_out: bool = False) -> None:
        super().__init__(message)
        self.timed_out = timed_out
