__all__ = [
    "ProblemNotFound",
    "ProblemAlreadyExisted",
    "ProblemDocsAlreadyExist",
    "ProblemDocsNotFound",
    "InvalidTestcaseExtension",
    "InvalidTestcaseCount",
    "SubmissionNotFound",
    "SubmissionAlreadyExist",
    "LanguageNotSupport",
    "LanguageNotAccept",
    "CompilerNotSupport",
    "CompilerNotAccept",
    "QueueNotFound",
    "ClosedQueue",
    "QueueNotValid",
    "UserAlreadyExist",
    "UserNotFound",
    "NotConnected",
    "ResultNotFound",
    "ResultAlreadyExist",
]


class NotFound(ValueError):
    pass


class AlreadyExist(ValueError):
    pass


class ValidationError(ValueError):
    pass


class NotSupport(ValueError):
    pass


class TestTypeNotSupport(NotSupport):
    pass


class ProblemNotFound(NotFound):
    pass


class ProblemAlreadyExisted(AlreadyExist):
    pass


class ProblemDocsNotFound(NotFound):
    pass


class ProblemDocsAlreadyExist(AlreadyExist):
    pass


class ProblemTestcaseAlreadyExist(AlreadyExist):
    pass


class InvalidProblemJudger(SyntaxError):
    pass


class InvalidTestcaseExtension(ValidationError):
    pass


class InvalidTestcaseCount(ValidationError):
    pass


class SubmissionNotFound(NotFound):
    pass


class SubmissionAlreadyExist(AlreadyExist):
    pass


class NothingToUpdate(ValueError):
    pass


class LanguageNotSupport(NotSupport):
    pass


class CompilerNotSupport(NotSupport):
    pass


class LanguageNotAccept(NotSupport):
    pass


class CompilerNotAccept(NotSupport):
    pass


class UserAlreadyExist(AlreadyExist):
    pass


class UserNotFound(NotFound):
    pass


class RoleNotFound(NotFound):
    pass


class RoleAlreadyExist(AlreadyExist):
    pass


class PermissionDenied(ValueError):
    pass


class PermissionNotFound(NotFound):
    pass


class QueueNotFound(NotFound):
    pass


class QueueAlreadyExist(AlreadyExist):
    pass


class ClosedQueue(ValueError):
    pass


class QueueNotValid(ValueError):
    pass


class NotConnected(ValueError):
    pass


class ResultNotFound(NotFound):
    pass


class ResultAlreadyExist(AlreadyExist):
    pass
