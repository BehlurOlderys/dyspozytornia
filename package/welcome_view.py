from PyQt5.QtWidgets import QInputDialog, QLabel, QGridLayout, QLineEdit, QHBoxLayout, QWidget, QVBoxLayout, QPushButton, QComboBox
import logging
from config_manager import save_config
import copy


logger = logging.getLogger(__name__)


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

        self._connect_buttons = {}

        def connect(u):
            print(f"Connecting to ip {u}")

        ROW_SHIFT=2
        for index, unit in enumerate(self._config["units"]):
            unit_name = unit["name"]
            unit_ip = unit["ip"]
            self._grid.addWidget(QLabel(unit_name), index+ROW_SHIFT, 0)
            self._grid.addWidget(QLabel(unit_ip), index+ROW_SHIFT, 1)
            self._connect_buttons[unit_name] = QPushButton(f"Connect")
            self._grid.addWidget(self._connect_buttons[unit_name], index+ROW_SHIFT, 2)
            self._grid.addWidget(QLabel("<status>"), index+ROW_SHIFT, 3)
            self._grid.addWidget(QLabel("<unknown>"), index+ROW_SHIFT, 4)
            self._grid.addWidget(QPushButton("View"), index+ROW_SHIFT, 5)
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
        self.setLayout(self._main_layout)

    def _save_to_config(self, d: dict):
        self._config.update(d)
        save_config(self._config)
