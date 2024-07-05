from PyQt5.QtWidgets import QInputDialog, QLabel, QGridLayout, QSpacerItem, QSizePolicy,  QLineEdit, QMainWindow, QWidget, QVBoxLayout, QPushButton, QComboBox
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QIcon
from PyQt5.QtCore import Qt

import logging
from config_manager import save_config


logger = logging.getLogger(__name__)


class ResizeableLabelWithImage(QLabel):
    def __init__(self, parent, initial_image: QImage = None):
        QLabel.__init__(self, parent)
        self.setMinimumSize(640, 480)

        if initial_image is not None:
            # initial_image = QImage("default.png")
            self._original_qimage = initial_image
            self._current_qimage = initial_image
            self._original_pixmap = QPixmap(self._original_qimage)
            self.setPixmap(self._original_pixmap)
        self._zoom_factor = 1.0
        self._stretched = False
        self._grid = False

    def _update_image_size(self):
        self._original_pixmap = QPixmap(self._current_qimage)
        self._original_pixmap = self._original_pixmap.scaled(int(self._zoom_factor*self.width()), int(self._zoom_factor*self.height()), Qt.KeepAspectRatio)
        self.setPixmap(self._original_pixmap)

    def resizeEvent(self, event):
        self._update_image_size()


class ViewImageWindow(QMainWindow):
    def __init__(self, parent):
        super(ViewImageWindow, self).__init__(parent)
        self.setWindowIcon(QIcon('4lufy.ico'))
        self._main_layout = QVBoxLayout()
        self._image_label = ResizeableLabelWithImage(parent=self, initial_image=QImage("default.png"))
        self.setCentralWidget(self._image_label)

    def show_yourself(self, unit_name):
        self.setWindowTitle(f"View last image from {unit_name}")
        self.show()


class WelcomeView(QWidget):
    def __init__(self, config):
        super(WelcomeView, self).__init__()
        self._config = config
        self._prepare_ui()

    def _prepare_ui(self):
        self._main_layout = QVBoxLayout()

        self._grid = QGridLayout()

        CURRENT_COL = 0
        self._grid.addWidget(QLabel("Unit name"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("IP address"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Connection"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Status"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Cameras offsets"), 0, CURRENT_COL)
        self._grid.addWidget(QPushButton("Calculate"), 1, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Last image"), 0, CURRENT_COL)
        CURRENT_COL += 1

        WIDTH = 2
        self._grid.addWidget(QLabel("Exposure"), 0, CURRENT_COL, 1, WIDTH)
        CURRENT_COL += WIDTH

        self._grid.addWidget(QLabel("Gain"), 0, CURRENT_COL, 1, WIDTH)
        CURRENT_COL += WIDTH

        self._grid.addWidget(QLabel("Cooling"), 0, CURRENT_COL)
        self._grid.addWidget(QPushButton("Turn on"), 1, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Current temp [C]"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Set temp [C]"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Binning"), 0, CURRENT_COL)
        self._grid.addWidget(QPushButton("Update"), 1, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Capturing type"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Saving images"), 0, CURRENT_COL)
        CURRENT_COL += 1

        view_image_window = ViewImageWindow(parent=self)

        self._connect_buttons = {}
        self._view_buttons = {}

        def view(u):
            print(f"Viewing from {u}")
            view_image_window.show_yourself(u)

        def connect(u):
            print(f"Connecting to {u}")

        ROW_SHIFT=2
        for index, unit in enumerate(self._config["units"]):
            unit_name = unit["name"]
            unit_ip = unit["ip"]
            self._grid.addWidget(QLabel(unit_name), index+ROW_SHIFT, 0)
            self._grid.addWidget(QLabel(unit_ip), index+ROW_SHIFT, 1)
            self._connect_buttons[unit_name] = QPushButton(f"Connect")
            self._connect_buttons[unit_name].clicked.connect(lambda always_false, z=unit_name: connect(z))
            self._grid.addWidget(self._connect_buttons[unit_name], index+ROW_SHIFT, 2)
            self._grid.addWidget(QLabel("<status>"), index+ROW_SHIFT, 3)
            self._grid.addWidget(QLabel("<unknown>"), index+ROW_SHIFT, 4)

            self._view_buttons[unit_name] = QPushButton("View")
            self._view_buttons[unit_name].clicked.connect(lambda always_false, z=unit_name: view(z))
            self._grid.addWidget(self._view_buttons[unit_name], index+ROW_SHIFT, 5)

            self._grid.addWidget(QPushButton("Set exp"),  index+ROW_SHIFT, 6)
            self._grid.addWidget(QLabel("<value>"),  index+ROW_SHIFT, 7)
            self._grid.addWidget(QPushButton("Set gain"),  index+ROW_SHIFT, 8)
            self._grid.addWidget(QLabel("<value>"),  index+ROW_SHIFT, 9)
            self._grid.addWidget(QLabel("<on or off>"),  index+ROW_SHIFT, 10)
            self._grid.addWidget(QLabel("<value>"),  index+ROW_SHIFT, 11)
            self._grid.addWidget(QLabel("<value>"),  index+ROW_SHIFT, 12)

            bin_combo = QComboBox()
            bin_combo.addItems(["x1", "x2", "x4"])
            self._grid.addWidget(bin_combo,  index+ROW_SHIFT, 13)

            capture_type_combo = QComboBox()
            capture_type_combo.addItems(["light", "flat", "dark", "bias"])
            self._grid.addWidget(capture_type_combo,  index+ROW_SHIFT, 14)

            self._grid.addWidget(QPushButton("Start/Stop"), index+ROW_SHIFT, 15)

        self._main_layout.addLayout(self._grid)
        self._main_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.setLayout(self._main_layout)

    def _save_to_config(self, d: dict):
        self._config.update(d)
        save_config(self._config)
