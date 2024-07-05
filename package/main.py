from package.config_manager import read_config
from package.welcome_view import WelcomeView
from PyQt5.QtWidgets import QMainWindow, QApplication, QVBoxLayout
from PyQt5.QtGui import QIcon
import sys
import logging
from logging.handlers import RotatingFileHandler
import qdarktheme


logger = logging.getLogger(__name__)


if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    print('running in a PyInstaller bundle')
else:
    print('running in a normal Python process')


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowIcon(QIcon('4lufy.ico'))
        self.config = read_config()
        self.main_layout = QVBoxLayout()
        self.setWindowTitle("Dyspozytornia")
        # self.setGeometry(100, 100, 320, 100)
        welcome_view = WelcomeView(self.config)
        self.setCentralWidget(welcome_view)
        self.show()


def configure_logging(logfile_path):
    default_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] [%(funcName)s():%(lineno)s] [PID:%(process)d] %(message)s",
        "%d/%m/%Y %H:%M:%S")

    file_handler = RotatingFileHandler(logfile_path, maxBytes=10485760, backupCount=300, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    file_handler.setFormatter(default_formatter)
    console_handler.setFormatter(default_formatter)

    logging.root.setLevel(logging.DEBUG)
    logging.root.addHandler(file_handler)
    logging.root.addHandler(console_handler)


if __name__ == '__main__':
    configure_logging("main.log")
    logger.debug("Logging works, starting Qt...")
    app = QApplication(sys.argv)

    qdarktheme.setup_theme()

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
