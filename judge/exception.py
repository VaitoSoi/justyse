class InitalizationError(ValueError):
    pass


class WriteError(ValueError):
    pass


class CodeWriteError(WriteError):
    pass


class TestcaseWriteError(WriteError):
    pass


class MismatchError(ValueError):
    pass


class TestcaseMismatchError(MismatchError):
    pass


class ServerBusy(ValueError):
    pass


class MissingField(ValueError):
    pass


class NotReceiving(ValueError):
    pass


class AlreadyConnected(ValueError):
    pass


class Closed(Warning):
    pass
