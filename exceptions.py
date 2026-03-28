class InvalidSession(Exception):
  def __init__(self, message: str):
    self.message = message

class dbError(Exception):
  def __init__(self, message: str):
    self.message = message

class couldNotGetUsernameAvailability(Exception):
  pass
  
class authenticationFailure(Exception):
  def __init__(self, message: str):
    self.message = message
