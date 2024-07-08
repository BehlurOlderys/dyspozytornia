from PyQt5.QtWidgets import QInputDialog, QLabel, QGridLayout, QSlider, QSpacerItem, QSizePolicy, QHBoxLayout, QLineEdit, QMainWindow, QWidget, QVBoxLayout, QPushButton, QComboBox
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QIcon, QFont
from PyQt5.QtCore import Qt
import numpy as np
import logging
from config_manager import save_config
from camera_requester import standalone_get_request, standalone_post_request, CameraRequester
from time import time
import re


logger = logging.getLogger(__name__)


regexp_for_exp_time = re.compile("(([0-9]*[.])?[0-9]+)(s|ms|us)")
port_for_cameras = 8080
EMPTY_CAMERA_LIST_ITEM = "<<no cameras connected>>"
US_IN_MILLISECOND = 1000
MILLISECONDS_IN_SECOND = 1000
US_IN_SECOND = MILLISECONDS_IN_SECOND * US_IN_MILLISECOND
MIN_EXP_US = 64
MAX_EXP_US = US_IN_SECOND*3600*2 # 2h is max anyway


def normalize_image(img, is16b=False):
    maxv = 65536 if is16b else 256
    typv = np.uint16 if is16b else np.uint8

    a = np.percentile(img, 5)
    b = np.percentile(img, 95)
    if b - a == 0:
        return (np.ones_like(img)*(maxv/2)).astype(typv)
    normalized = (img - a) / (b - a)
    return np.clip(maxv * normalized, 0, maxv-1).astype(typv)


def qimage_from_buffer(content, resolution, image_format):
    logger.debug(f"Creating image with format {image_format}")
    is16b = (image_format == "RAW16")
    buffer_type = np.uint16 if is16b else np.uint8
    image_format = QImage.Format_Grayscale16 if is16b else QImage.Format_Grayscale8

    img = np.frombuffer(content, dtype=buffer_type)
    w, h = resolution
    logger.debug(f"Reshaping into {w}x{h}...")
    original_img = img.reshape(w, h)
    logger.debug(f"dimension = {original_img.shape}, Max = {np.max(original_img)}, min = {np.min(original_img)}")
    # final_img = normalize_image(original_img, is16b=is16b)
    logger.debug("Normalized!")
    q_img = QImage(original_img.data, original_img.shape[0], original_img.shape[1], image_format)
    return q_img, original_img


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
        self._hmin = 0
        self._hmax = 100
        if initial_image is not None:
            # initial_image = QImage("default.png")
            self._original_qimage = initial_image
            self._current_qimage = initial_image
            self._original_pixmap = QPixmap(self._original_qimage)
            self.setPixmap(self._original_pixmap)
        self._zoom_factor = 1.0
        self._stretched = False
        self._grid = False

    def adjust_histogram(self, hmin, hmax):
        if hmin < 0 or hmax < 0 or hmin > 100 or hmax > 100 or hmax == hmin:
            return False
        self._hmin = hmin
        self._hmax = hmax
        logger.debug(f"Adjusting histogram to {self._hmin}/{self._hmax}")
        self._current_qimage = self._histogram_from_original()
        self._update_image_size()
        return True

    def _histogram_from_original(self):
        qimage: QImage = self._original_qimage
        working_image = qimage.convertToFormat(QImage.Format.Format_Grayscale16)
        width = working_image.width()
        height = working_image.height()
        ptr = working_image.bits()
        ptr.setsize(height * width * 2)
        arr = np.frombuffer(ptr, np.uint16)
        maxv = 65536
        typv = np.uint16
        # we assume that signal will be in first 10% of histogram here:
        a = maxv*self._hmin/1000.0
        b = maxv*self._hmax/1000.0
        normalized = (arr - a) / (b - a)
        logger.debug(f"a={a}, b={b}")
        new_arr = np.clip(maxv * normalized, 0, maxv - 1).astype(typv)
        return QImage(new_arr, width, height, QImage.Format.Format_Grayscale16)

    def _normalize_original(self):
        qimage: QImage = self._original_qimage
        working_image = qimage.convertToFormat(QImage.Format.Format_Grayscale16)
        width = working_image.width()
        height = working_image.height()
        ptr = working_image.bits()
        ptr.setsize(height * width * 2)
        arr = np.frombuffer(ptr, np.uint16)
        a = np.percentile(arr, 1)
        b = np.percentile(arr, 99)
        normalized = (arr - a) / (b - a)
        logger.debug(f"a={a}, b={b}")
        maxv = 65536
        typv = np.uint16
        new_arr = np.clip(maxv * normalized, 0, maxv - 1).astype(typv)
        return QImage(new_arr, width, height, QImage.Format.Format_Grayscale16)

    def set_image(self, image: QImage):
        self._original_qimage = image
        self._current_qimage = self._normalize_original()
        self._update_image_size()

    def _update_image_size(self):
        self._original_pixmap = QPixmap(self._current_qimage)
        self._original_pixmap = self._original_pixmap.scaled(int(self._zoom_factor*self.width()), int(self._zoom_factor*self.height()), Qt.KeepAspectRatio)
        self.setPixmap(self._original_pixmap)

    def resizeEvent(self, event):
        self._update_image_size()


def get_last_image_as_qimage(unit_name, camera_index):
    is_ok1, (w, h) = CameraRequester(unit_name, camera_index).get_resolution()
    is_ok2, current_format = CameraRequester(unit_name, camera_index).get_current_format()
    if not is_ok1 or not is_ok2:
        logger.error("Could not get required image parameters from camera")
        return None
    start_time = time()
    response = CameraRequester(unit_name, camera_index).get_last_image(send_as_jpg=False)
    time_elapsed = time() - start_time
    logger.debug(f"Time elapsed on receiving response: {time_elapsed}s")
    if response is None:
        return response
    q_img, _ = qimage_from_buffer(response.content, [w, h], current_format)
    return q_img


class ImageView(QWidget):
    def __init__(self):
        super(ImageView, self).__init__()
        self._main_layout = QHBoxLayout()
        self._image_label = ResizeableLabelWithImage(parent=self, initial_image=QImage("default.png"))
        self._main_layout.addWidget(self._image_label)
        self._current_index = -1
        self._current_name = ""
        button_layout = QVBoxLayout()

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh)
        button_layout.addWidget(refresh_button)

        def add_button_move_focuser(value: int):
            button_move_focuser = QPushButton(f"Move {value}")
            button_move_focuser.clicked.connect(lambda: self._move_focuser(value))
            button_layout.addWidget(button_move_focuser)

        for value in [-1024, -512, -256, 256, 512, 1024]:
            add_button_move_focuser(value)

        self._main_layout.addLayout(button_layout)

        self._slider_min = QSlider(Qt.Vertical)
        self._slider_min.sliderReleased.connect(self._slider_released)
        self._slider_min.setValue(0)
        self._main_layout.addWidget(self._slider_min)

        self._slider_max = QSlider(Qt.Vertical)
        self._slider_max.setValue(100)
        self._slider_max.sliderReleased.connect(self._slider_released)
        self._main_layout.addWidget(self._slider_max)
        self.setLayout(self._main_layout)

    def _slider_released(self):
        minp = self._slider_min.value()
        maxp = self._slider_max.value()
        logger.debug(f"New max/min = {maxp}/{minp}")
        self._image_label.adjust_histogram(minp, maxp)

    def _refresh(self):
        q_image = get_last_image_as_qimage(self._current_name, self._current_index)
        self._image_label.set_image(q_image)

    def _move_focuser(self, value):
        if self._current_index < 0 or len(self._current_name) < 1:
            return
        CameraRequester(self._current_name, self._current_index).move_focuser(value)

    def set_image_and_camera(self, q_image: QImage, current_index: int, current_name: str):
        self._current_index = current_index
        self._current_name = current_name
        CameraRequester(current_name, current_index).connect_focuser()
        self._image_label.set_image(q_image)


class ViewImageWindow(QMainWindow):
    def __init__(self, parent):
        super(ViewImageWindow, self).__init__(parent)
        self.setWindowIcon(QIcon('4lufy.ico'))
        self._main_view = ImageView()
        self.setCentralWidget(self._main_view)

    def show_yourself(self, unit_name, camera_index):
        q_image = get_last_image_as_qimage(unit_name, camera_index)
        self.setWindowTitle(f"View last image from {unit_name}")
        self._main_view.set_image_and_camera(q_image, camera_index, unit_name)
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
        self._exp_edits = {}

        def view(u):
            print(f"Viewing from {u}")
            i = self._cameras_combos[unit_name].currentIndex()
            view_image_window.show_yourself(u, i)

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
            current_exposure_text = "<<exposure time>>"
            current_binning_txt = "x4"
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

                            ########## a little bit of hardcode:
                            bin_value = 4
                            CameraRequester(unit_name, current_index).set_binning(bin_value)
                            format_str = "RAW16"
                            CameraRequester(unit_name, current_index).set_format(format_str)
                            CameraRequester(unit_name, current_index).set_exposure("1")
                            CameraRequester(unit_name, current_index).start_capturing()

                            ok, is_cooler_on = CameraRequester(unit_name, current_index).get_cooler_on()
                            if ok:
                                camera_cooling_status_text = "YES" if is_cooler_on else "NO"
                                camera_cooling_status_color = "green" if is_cooler_on else "red"

                            ok, camera_temp = CameraRequester(unit_name, current_index).get_temperature()
                            if ok:
                                camera_temp_text = str(camera_temp)

                            ok, exposure_raw_us = CameraRequester(unit_name, current_index).get_exposure_us()
                            if ok:
                                exposure_us = int(exposure_raw_us)
                                if exposure_us >= US_IN_SECOND:
                                    current_exposure_text = f"{exposure_us/US_IN_SECOND}s"
                                elif exposure_us >= US_IN_MILLISECOND:
                                    current_exposure_text = f"{exposure_us/US_IN_MILLISECOND}ms"
                                else:
                                    current_exposure_text = f"{exposure_us}us"


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

            self._exp_edits[unit_name] = QLineEdit(current_exposure_text)
            self._exp_edits[unit_name].returnPressed.connect(lambda u=unit_name: self._pressed_exp_edit(u))
            self._grid.addWidget(self._exp_edits[unit_name],  index+ROW_SHIFT, CURRENT_COL)

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
            bin_combo.setCurrentText(current_binning_txt)
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

    def _pressed_exp_edit(self, unit_name):
        camera_index = self._cameras_combos[unit_name].currentIndex()
        exp_raw = self._exp_edits[unit_name].text()
        m = regexp_for_exp_time.match(exp_raw)
        if not m:
            logger.warning(f"Could not match regexp for exposure time")
            return
        reconstructed_str = m.groups()[0] + m.groups()[-1]
        if len(reconstructed_str) != len(exp_raw):
            logger.warning("There are some extra chars, let's leave it!")
            return
        fnumber = float(m.groups()[0])
        funit = m.groups()[-1]

        if funit == "ms":
            factor = US_IN_MILLISECOND
        elif funit == "us":
            factor = US_IN_SECOND
        else:
            factor = 1
        new_exp = float(fnumber/factor)
        if new_exp < MIN_EXP_US or new_exp > MAX_EXP_US:
            logger.warning(f"Exposure outside range: {new_exp}us")
        logger.debug(f"Unit name = {unit_name}, exp_raw = {exp_raw}, new_exp={new_exp}")
        CameraRequester(unit_name, camera_index).set_exposure(new_exp)


    def _save_to_config(self, d: dict):
        self._config.update(d)
        save_config(self._config)
