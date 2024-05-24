import logging
import colorama



class ColorLogFormatter(logging.Formatter):
    namecolors = {
        'DEBUG': colorama.Fore.BLUE,
        'INFO': colorama.Fore.GREEN,
        'WARNING': colorama.Fore.YELLOW,
        'ERROR': colorama.Style.DIM + colorama.Fore.RED,
        'CRITICAL': colorama.Fore.RED
    }

    def __init__(self, *args, **kwargs):
        super(ColorLogFormatter, self).__init__(*args, **kwargs)
        colorama.init()

    def colorname(self, name):
        s = self.namecolors.get(name, "")
        return colorama.Style.BRIGHT + s + name + colorama.Style.RESET_ALL

    def format(self, record):
        record.levelnamecolor = self.colorname(record.levelname)
        return super(ColorLogFormatter, self).format(record)
