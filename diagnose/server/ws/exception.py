class WebsocketException(RuntimeError):
    """
    the inner exception for ws

    To make the inner ws package as simple as possible, the exceptions in the origin ``websockets`` library are
    simplified. For the integral implementation of exceptions please refer the `repo`_.

    .. _repo:
        https://github.com/python-websockets/websockets/blob/main/src/websockets/exceptions.py
    """

    def __init__(self, msg: str):
        self._msg = msg
        if ':' in msg:
            self._type = msg.split(':', 1)[0]

    @property
    def msg(self):
        """
        the message of the Exception
        """
        return self._msg

    @msg.setter
    def msg(self, msg: str):
        self._msg = msg

    @property
    def type(self):
        """
        the type of the exception

        Usually, the type corresponds with the origin exception's class name. For example, if the :attr:`type` is set to
        ``InvalidOrigin``, it refers to the ``InvalidOrigin`` `exception`_.

        .. _`exception`:
            https://github.com/python-websockets/websockets/blob/main/src/websockets/exceptions.py#L217
        """
        return self._type

    @type.setter
    def type(self, type_: str):
        self._type = type_
