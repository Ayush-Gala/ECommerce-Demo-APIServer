class ApiError(Exception):
    """An error with a fixed HTTP status and JSON body, raised from route handlers."""

    def __init__(self, status_code: int, error: str, message: str, **details):
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message
        self.details = details
