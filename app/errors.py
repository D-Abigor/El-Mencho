class InvalidSession(Exception):
    def __init__(self, message: str = "Your session is invalid or has expired."):
        self.message = message
        super().__init__(message)

class DbError(Exception):
    def __init__(self, message: str = "db error"):
        self.message = message
        super().__init__(message)

class CouldNotGetUsernameAvailability(Exception):
    pass

class AuthenticationFailure(Exception):
    def __init__(self, message: str = "authentication failure"):
        self.message = message
        super().__init__(message)

class TransactionError(Exception):
    def __init__(self, message: str = "transaction failed"):
        self.message = message
        super().__init__(message)
