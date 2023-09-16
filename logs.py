import datetime
import io
import logging
from os import PathLike
from typing import ClassVar, Optional

__all__ = ['Logger']

#from typings import LoggerLike


class Logger(logging.Logger):
    """
    The logger implementation for the whole project.

    The :class:`Logger` is a subclass of :class:`logging.Logger` which is
    implemented by Vinay Sajip. This :class:`Logger` rewrites various logging
    methods and reorganizes :meth:`get_logger` and :meth:`redirect_to_file` to
    support the current situation and make it more object-oriented.

    The current :class:`Logger` is actually a dummy Logger and only provides the
    logging interface for users. The real :class:`Logger` is its class variable
    :obj:`_logger`.

    Attributes:
        _logger: The class variable for storing the real
            :class:`logging.Logger` which is appended to the Logger chain.
            See the `logging document`_ and `HOW-TO`_ for more details.

            .. _`logging document`: https://docs.python.org/3/library/logging.html
            .. _`HOW-TO`: https://docs.python.org/3/howto/logging.html

    """

    _logger: ClassVar[logging.Logger] = None

    @staticmethod
    def _acquire_lock():
        """
        Acquire the lock in the logging package.

        """
        getattr(logging, '_acquireLock')()

    @staticmethod
    def _release_lock():
        """
        Release the lock in the logging package.

        """
        getattr(logging, '_releaseLock')()
    
    @staticmethod
    def redirect_to_file(filename: PathLike,
                         mode: str = 'a',
                         logger: Optional['LoggerLike'] = None):
        """
        Redirect the output stream of :class:`Logger` to a file.

        The method :meth:`redirect_to_file` behaves like the function
        :func:`logging.basicConfig` in :mod:`logging`. Users can redirect the
        logging information to given file like this::

            Logger.redirect_to_file('foo.log')

        Note that the output of other Python program will not be affected. For
        example, the file in executed in ``exec``

        Args:
            filename(PathLike): The path of the redirected file.
            mode(str): The mode for processing files. See the `offical document`_
                for :mod:`os`.

                .. _`offical document`: https://docs.python.org/3/library/functions.html#open
            logger(Optional[LoggerLike]): The :class:`Logger` needs to redirect
                the output. If not provided, all :class:`Logger` will be
                redirected.

        """
        Logger._acquire_lock()
        # Copy from the logging module
        encoding = None
        errors = 'backslashreplace'
        try:
            if 'b' in mode:
                errors = None
            else:
                encoding = io.text_encoding(encoding)
            h = logging.FileHandler(filename, mode,
                                encoding=encoding, errors=errors)
            fmt = logging.Formatter(logging.BASIC_FORMAT, None, '%')
            h.setFormatter(fmt)
            if not logger:
                logging.root.addHandler(h)
            else:
                # XXX: Hack to the inner real Logger object
                logger._logger.addHandler(h)
                # Update the dict in logging module manually
                logging.Logger.manager.loggerDict.update([(logger.name.name, logger)])
        finally:
            Logger._release_lock()
    
    @classmethod
    def get_logger(cls, name=None) -> 'Logger':
        """
        Get the :class:`Logger` object with given name. If not provided, it will
        return the default :class:`Logger`.

        It behaves like the function :func:`logging.getLogger`.

        Args:
            name: The name of the :class:`Logger`. If it exists in the inner dict,
                it will returns directly. Otherwise, it will be initialized.

        Returns:
            Logger: The :class:`Logger` object.
        """
        cls._logger = logging.getLogger(name)
        # Real Logger must be wrapped so that it can invoke the methods bellow.
        return Logger(cls._logger)

    # Modify the methods in the logging package.

    def debug(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'DEBUG'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.debug("Houston, we have a %s", "thorny problem", exc_info=1)
        """
        _logger = self._logger
        if _logger.isEnabledFor(logging.DEBUG):
            msg = f'\033[38m[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]{msg}\033[0m'
            _logger._log(logging.DEBUG, msg, args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'INFO'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.info("Houston, we have a %s", "interesting problem", exc_info=1)
        """
        _logger = self._logger
        if _logger.isEnabledFor(logging.INFO):
            msg = f'\033[38m[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]{msg}\033[0m'
            _logger._log(logging.INFO, msg, args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'WARNING'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.warning("Houston, we have a %s", "bit of a problem", exc_info=1)
        """
        _logger = self._logger
        if _logger.isEnabledFor(logging.WARNING):
            msg = f'\033[33m[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]{msg}\033[0m'
            _logger._log(logging.WARNING, msg, args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'ERROR'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.error("Houston, we have a %s", "major problem", exc_info=1)
        """
        _logger = self._logger
        if _logger.isEnabledFor(logging.ERROR):
            msg = f'\033[31m[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]{msg}\033[0m'
            _logger._log(logging.ERROR, msg, args, **kwargs)

    def exception(self, msg, *args, exc_info=True, **kwargs):
        """
        Convenience method for logging an ERROR with exception information.
        """
        self._logger.error(msg, *args, exc_info=exc_info, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'CRITICAL'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.critical("Houston, we have a %s", "major disaster", exc_info=1)
        """
        _logger = self._logger
        if _logger.isEnabledFor(logging.CRITICAL):
            msg = f'\033[31m[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]{msg}\033[0m'
            _logger._log(logging.CRITICAL, msg, args, **kwargs)

    def fatal(self, msg, *args, **kwargs):
        """
        Don't use this method, use critical() instead.
        """
        self._logger.critical(msg, *args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        """
        Log 'msg % args' with the integer severity 'level'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.log(level, "We have a %s", "mysterious problem", exc_info=1)
        """
        _logger = self._logger
        if not isinstance(level, int):
            raise TypeError("level must be an integer")

        if _logger.isEnabledFor(level):
            msg = f'\033[38m[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]{msg}\033[0m'
            _logger._log(level, msg, args, **kwargs)