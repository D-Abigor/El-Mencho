class InvalidSession(Exception):
    def __init__(self, message: str = "Your session is invalid or has expired."):
        self.message = message

class DbError(Exception):
    def __init__(self, message: str):
        self.message = message

class CouldNotGetUsernameAvailability(Exception):
    pass

class AuthenticationFailure(Exception):
    def __init__(self, message: str):
        self.message = message

class TransactionError(Exception):
    def __init__(self, message: str):
        self.message = message
