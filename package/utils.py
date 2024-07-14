from PyQt5.QtCore import QTimer
import logging


logger = logging.getLogger(__name__)


def start_repeated_task(parent, callback, interval_s):
    timer = QTimer(parent)
    timer.timeout.connect(callback)
    timer.start(interval_s*1000)
