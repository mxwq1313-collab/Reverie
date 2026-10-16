from ...importer.validator import DocumentError


class AndroidSourceError(DocumentError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
