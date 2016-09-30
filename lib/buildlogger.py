#!/usr/bin/env python

#
# build logging facility
#

import logging

_CURRENT_LOGGING_TARGET = 'none'

class LoggingColor(object):
    color_names = ['black', 'red', 'green', 'yellow', 'blue', 'magenta',
                   'cyan', 'white']

    level_color_mapping = {
        'PASS': 'green',
        'FAIL': 'red',
        'CRITICAL': 'magenta',
        'ERROR': 'red',
        'WARNING': 'yellow',
        'INFO': 'black',
        'DEBUG': 'blue',
        }

    # color name to color value mapping
    color_value_mapping = {}

    def dye(self, levelname):
        color_name = self.level_color_mapping.get(levelname)
        color_value = self.color_value_mapping.get(color_name)
        if color_value:
            prefix = self.color_seq.format(color_value)
            suffix = self.reset_seq
            levelname = prefix + levelname + suffix

        return levelname


class ConsoleColor(LoggingColor):
    def __init__(self):
        #These are the sequences need to get colored ouput
        self.color_seq = "\033[1;{}m"
        self.reset_seq = "\033[0m"
        self.color_value_mapping = dict(zip(self.color_names, range(30, 38)))

        # support background highlight
        bg_color_names = ['background_%s' % cn for cn in self.color_names]
        self.color_value_mapping.update(zip(bg_color_names, range(40, 48)))

        super(ConsoleColor, self).__init__()


class NoneColor(LoggingColor):
    def __init__(self):
        #These are the sequences need to get colored ouput
        self.color_seq = ''
        self.reset_seq = ''
        self.color_value_mapping = dict(zip(self.color_names, self.color_names))

        super(NoneColor, self).__init__()


class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt, **kwargs):
        super(ColoredFormatter, self).__init__(fmt, **kwargs)
        self.colors = {'console':ConsoleColor(),
                       'none':NoneColor(),}

    def format(self, record):
        target_corlor = self.colors[_CURRENT_LOGGING_TARGET]
        record.levelname = target_corlor.dye(record.levelname)

        return super(ColoredFormatter, self).format(record)


# add two logging level
PASS_LEVEL_NUM = 60
FAIL_LEVEL_NUM = 61
logging.addLevelName(PASS_LEVEL_NUM, 'PASS')
logging.addLevelName(FAIL_LEVEL_NUM, 'FAIL')

class ColoredLogger(logging.Logger):
    def __init__(self, name):
        fmt = '%(asctime)s %(name)s:%(funcName)s:%(levelname)s: %(message)s'
        super(ColoredLogger, self).__init__(name, logging.INFO)

        color_formatter = ColoredFormatter(fmt)
        console = logging.StreamHandler()
        console.setFormatter(color_formatter)

        self.handlers = []
        self.addHandler(console)

    def passed(self, message, *args, **kws):
        # Yes, logger takes its '*args' as 'args'.
        if self.isEnabledFor(PASS_LEVEL_NUM):
            self._log(PASS_LEVEL_NUM, message, args, **kws) 

    def failed(self, message, *args, **kws):
        # Yes, logger takes its '*args' as 'args'.
        if self.isEnabledFor(FAIL_LEVEL_NUM):
            self._log(FAIL_LEVEL_NUM, message, args, **kws) 

logging.setLoggerClass(ColoredLogger)

def set_logging_color_format(target_fmt='console'):
    '''Tell logging module the output format we need to use to
    colorize/highlight keywords.

    @param target_fmt [in] a string, 'console' or 'none'
    '''
    assert target_fmt in ['console', 'none']

    global _CURRENT_LOGGING_TARGET
    _CURRENT_LOGGING_TARGET = target_fmt

def getLogger(loggerName):
    logger = logging.getLogger(loggerName)

    logger.setLevel(logging.INFO)
    logger.propagate = False

    return logger


if __name__ == '__main__':
    logger = getLogger(__name__)

    logger.debug('hello world')
    logger.info('hello world')
    logger.warning('hello world')
    logger.error('hello world')
    logger.critical('hello world')
    logger.passed('hello world')
    logger.failed('hello world')

