class ClientException(Exception):
    data = {}

    def __init__(self, message, data={}):
        super().__init__(message)
        self.data = data
