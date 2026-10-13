class PlayError(Exception):
    """Shown to the player. `code` lets the page react (e.g. show the sign-up link)."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
