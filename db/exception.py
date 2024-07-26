__all__ = [
    'ProblemNotFound',
    'ProblemAlreadyExisted',
    'ProblemDocsAlreadyExist',
    'ProblemDocsNotFound',
    'InvalidTestcaseExtension',
    'InvalidTestcaseCount',
    'SubmissionNotFound'
]


class ProblemNotFound(ValueError):
    pass


class ProblemAlreadyExisted(ValueError):
    pass


class ProblemDocsAlreadyExist(ValueError):
    pass


class ProblemDocsNotFound(ValueError):
    pass


class InvalidTestcaseExtension(ValueError):
    pass


class InvalidTestcaseCount(ValueError):
    def __str__(self):
        return self.args[0]


class SubmissionNotFound(ValueError):
    pass


class SubmissionAlreadyExist(ValueError):
    pass
