from PyQt5.QtWidgets import QInputDialog, QLabel, QGridLayout, QSpacerItem, QSizePolicy,  QLineEdit, QMainWindow, QWidget, QVBoxLayout, QPushButton, QComboBox
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QIcon, QFont
from PyQt5.QtCore import Qt

import requests
import logging
from config_manager import save_config
from camera_requester import standalone_get_request, standalone_post_request, CameraRequester


logger = logging.getLogger(__name__)


port_for_cameras = 8080
EMPTY_CAMERA_LIST_ITEM = "<<no cameras connected>>"


def get_cameras_list(try_ip):
    full_url = f"http://{try_ip}:{port_for_cameras}/cameras_list"
    response = standalone_get_request(full_url)
    if response is None:
        return response

    cameras_list = response.json()["cameras"]
    logger.debug(f"Successfully got list of cameras at {try_ip} : {cameras_list}")
    return cameras_list


def connect_to_camera(camera_name, camera_index, current_ip):
    logger.debug(f"Connecting to camera {camera_name} at {current_ip}")

    url = f"http://{current_ip}:{port_for_cameras}/camera/{camera_index}/init_camera"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    data = {}

    logger.debug(f"About to call POST...")
    response = standalone_post_request(url, headers, data)
    if response is not None and response.status_code == 200:
        return CameraRequester(current_ip, camera_index).get_status()
    else:
        return None


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

        self._grid.addWidget(QLabel("Reachable"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Cameras"), 0, CURRENT_COL)
        self._grid.addWidget(QPushButton("Refresh"), 1, CURRENT_COL)
        ##################################################################################
        # TODO: refresh should again go through all unit_names, ask cameras_list on them and put results into ComboBoxes
        # TODO: if a camera is already in a state that makes it being regularly requested then do not refresh it!
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
        # TODO: This button should update text on apropriate labels.
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Current temp [C]"), 0, CURRENT_COL)
        # TODO should ask for current temp every few seconds
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

        self._cameras_combos = {}
        self._view_buttons = {}

        def view(u):
            print(f"Viewing from {u}")
            view_image_window.show_yourself(u)

        ROW_SHIFT=2
        for index, unit_name in enumerate(self._config["units"]):
            CURRENT_COL = 0
            self._grid.addWidget(QLabel(unit_name), index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            ##################################################
            # TODO: this check should go again whenever user presses Refresh button!
            # TODO: UNLESS it is already connected and working then it is useless and may disrupt work!!!
            cameras_list = get_cameras_list(unit_name)
            reachable = cameras_list is not None
            reachable_label = QLabel()
            reachable_label.setText("YES" if reachable else "NO")
            reachable_color = "green" if reachable else "red"
            reachable_font = QFont()
            reachable_font.setBold(True)
            reachable_label.setFont(reachable_font)
            reachable_label.setStyleSheet(f"color: {reachable_color}")

            self._grid.addWidget(reachable_label, index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1
            self._cameras_combos[unit_name] = QComboBox()
            if len(cameras_list) == 0:
                cameras_list = [EMPTY_CAMERA_LIST_ITEM]
            logger.debug(f"Obtained cameras list: {cameras_list} for {unit_name}")
            self._cameras_combos[unit_name].addItems(cameras_list)
            self._grid.addWidget(self._cameras_combos[unit_name], index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            ######################################################################
            # TODO: status should be checked once per second ideally. It will also return number of already captured images!
            camera_status_text = "<unknown>"
            # TODO should react on pressing "Turn On" button!!!
            camera_cooling_status_text = "<on or off>"
            camera_cooling_status_color = "white"
            # TODO: should ask for temperature and update this every few seconds:
            camera_temp_text = "<<temp unknown>>"
            if reachable:
                current_camera = self._cameras_combos[unit_name].currentText()
                if current_camera is not EMPTY_CAMERA_LIST_ITEM:
                    current_index = self._cameras_combos[unit_name].currentIndex()
                    result = connect_to_camera(current_camera, current_index, unit_name)
                    if result is not None:
                        ok, status = result
                        if ok:
                            camera_status_text = status["state"]
                            ok, is_cooler_on = CameraRequester(unit_name, current_index).get_cooler_on()
                            if ok:
                                camera_cooling_status_text = "YES" if is_cooler_on else "NO"
                                camera_cooling_status_color = "green" if is_cooler_on else "red"

                            ok, camera_temp = CameraRequester(unit_name, current_index).get_temperature()
                            if ok:
                                camera_temp_text = str(camera_temp)

            self._grid.addWidget(QLabel(camera_status_text), index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1
            self._grid.addWidget(QLabel("<<offset unknown>>"), index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            self._view_buttons[unit_name] = QPushButton("View")
            self._view_buttons[unit_name].clicked.connect(lambda always_false, z=unit_name: view(z))
            self._grid.addWidget(self._view_buttons[unit_name], index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            self._grid.addWidget(QPushButton("Set exp"),  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1
            self._grid.addWidget(QLabel("<value>"),  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1
            self._grid.addWidget(QPushButton("Set gain"),  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1
            self._grid.addWidget(QLabel("<value>"),  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            ############################################################################
            cooling_label = QLabel(camera_cooling_status_text)
            cooling_font = QFont()
            cooling_font.setBold(True)
            cooling_label.setFont(cooling_font)
            cooling_label.setStyleSheet(f"color: {camera_cooling_status_color}")
            self._grid.addWidget(cooling_label,  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1
            self._grid.addWidget(QLabel(camera_temp_text),  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1
            self._grid.addWidget(QLabel("<value>"),  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            bin_combo = QComboBox()
            bin_combo.addItems(["x1", "x2", "x4"])
            self._grid.addWidget(bin_combo,  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            capture_type_combo = QComboBox()
            capture_type_combo.addItems(["light", "flat", "dark", "bias"])
            self._grid.addWidget(capture_type_combo,  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            self._grid.addWidget(QPushButton("Start/Stop"), index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

        self._main_layout.addLayout(self._grid)
        self._main_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.setLayout(self._main_layout)

    def _save_to_config(self, d: dict):
        self._config.update(d)
        save_config(self._config)
