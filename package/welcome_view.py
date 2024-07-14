import subprocess

from PyQt5.QtWidgets import QInputDialog, QLabel, QGridLayout, QSlider, QSpacerItem, QSizePolicy, QHBoxLayout, QLineEdit, QMainWindow, QWidget, QVBoxLayout, QPushButton, QComboBox
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QIcon, QFont
from PyQt5.QtCore import Qt
import numpy as np
import logging
from config_manager import save_config
from utils import start_repeated_task
from camera_requester import standalone_get_request, standalone_post_request, CameraRequester
from time import time
from threading import Event
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
        self._histogram = False

    def adjust_histogram(self, hmin, hmax):
        if hmin < 0 or hmax < 0 or hmin > 100 or hmax > 100 or hmax == hmin:
            return False
        self._histogram = True
        self._hmin = hmin
        self._hmax = hmax
        logger.debug(f"Adjusting histogram to {self._hmin}/{self._hmax}")
        self._process_with_histogram()
        self._update_image_size()
        return True

    def _process_with_histogram(self):
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
        self._current_qimage = QImage(new_arr, width, height, QImage.Format.Format_Grayscale16)

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
        self._current_qimage = QImage(new_arr, width, height, QImage.Format.Format_Grayscale16)

    def set_image(self, image: QImage):
        self._original_qimage = image
        if self._histogram:
            self._process_with_histogram()
        else:
            self._normalize_original()
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
        self._kill_event = Event()
        self._task_events = {}
        self._prepare_ui()

    def _add_task(self, refresh_rate, callback, unique_name):
        start_repeated_task(self, callback, refresh_rate)
        # new_refresh_event = Event()
        # logger.debug("About to start new task")
        # self._task_events[unique_name] = new_refresh_event
        # start_interval_polling(new_refresh_event, callback, refresh_rate, self._kill_event)

    def _end_tasks(self):
        print("===== ENDING TASKS!")
        self._kill_event.set()
        for task_event in self._task_events.values():
            task_event.set()

    def __del__(self):
        self._end_tasks()

    def closeEvent(self, event):
        self._end_tasks()
        event.accept()

    def _prepare_ui(self):
        self._main_layout = QVBoxLayout()
        self._grid = QGridLayout()

        CURRENT_COL = 0
        self._grid.addWidget(QLabel("Unit name"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Pingable"), 0, CURRENT_COL)
        ping_button = QPushButton("Ping units")
        ping_button.clicked.connect(self._ping_units)
        self._grid.addWidget(ping_button, 1, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Reachable"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Cameras"), 0, CURRENT_COL)
        refresh_servers_button = QPushButton("Restart inactive servers")
        refresh_servers_button.clicked.connect(self._refresh_servers)
        self._grid.addWidget(refresh_servers_button, 1, CURRENT_COL)
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
        self._all_coolers_button = QPushButton("Turn on")
        self._all_coolers_button.setCheckable(True)
        self._all_coolers_button.setStyleSheet("background-color : black")
        self._all_coolers_button.clicked.connect(self._turn_all_coolers)
        self._grid.addWidget(self._all_coolers_button, 1, CURRENT_COL)
        # TODO: This button should update text on apropriate labels.
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Current temp [C]"), 0, CURRENT_COL)
        # TODO should ask for current temp every few seconds
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Set temp [C]"), 0, CURRENT_COL)
        self._set_temperature_edit = QLineEdit("0")
        self._set_temperature_edit.returnPressed.connect(self._set_desired_temperature_for_all)
        self._grid.addWidget(self._set_temperature_edit, 1, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Binning"), 0, CURRENT_COL)
        self._grid.addWidget(QPushButton("Update"), 1, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Capturing type"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Capturing number"), 0, CURRENT_COL)
        CURRENT_COL += 1

        self._grid.addWidget(QLabel("Saving images"), 0, CURRENT_COL)
        CURRENT_COL += 1

        view_image_window = ViewImageWindow(parent=self)

        self._cameras_combos = {}
        self._view_buttons = {}
        self._exp_edits = {}
        self._capture_number_edits = {}
        self._pingable = {}
        self._ping_labels = {}
        self._reacheable = {}
        self._camera_statuses = {}
        self._temp_displays = {}
        self._cooling_statuses = {}
        self._cooling_labels = {}
        self._set_temperature_display = {}
        self._start_capture_buttons = {}
        self._capture_number = {}
        self._dir_name_combo = {}

        def view(u):
            if not self._reacheable[unit_name]:
                print(f"Cannot view from {unit_name}")
                return
            print(f"Viewing from {u}")
            i = self._cameras_combos[unit_name].currentIndex()
            view_image_window.show_yourself(u, i)

        ROW_SHIFT=2
        for index, unit_name in enumerate(self._config["units"]):
            CURRENT_COL = 0
            self._grid.addWidget(QLabel(unit_name), index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            ##################################################
            self._capture_number[unit_name] = 1
            self._pingable[unit_name] = self._ping(unit_name)
            self._ping_labels[unit_name] = QLabel()
            self._prepare_pingable_label(unit_name)
            self._grid.addWidget(self._ping_labels[unit_name])
            CURRENT_COL += 1
            ##################################################
            # TODO: this check should go again whenever user presses Refresh button!
            # TODO: UNLESS it is already connected and working then it is useless and may disrupt work!!!
            cameras_list = None
            if self._pingable[unit_name]:
                cameras_list = get_cameras_list(unit_name)
            self._reacheable[unit_name] = cameras_list is not None
            reachable_label = QLabel()
            reachable_label.setText("YES" if self._reacheable[unit_name] else "NO")
            reachable_color = "green" if self._reacheable[unit_name] else "red"
            reachable_font = QFont()
            reachable_font.setBold(True)
            reachable_label.setFont(reachable_font)
            reachable_label.setStyleSheet(f"color: {reachable_color}")

            self._grid.addWidget(reachable_label, index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1
            self._cameras_combos[unit_name] = QComboBox()
            self._refresh_cameras_combo(cameras_list, unit_name)
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
            set_temp_text = "<<value>>"
            # TODO: should ask for temperature and update this every few seconds:
            camera_temp_text = "<<temp unknown>>"
            if self._reacheable[unit_name]:
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

                            ok, temp = CameraRequester(unit_name, current_index).get_set_temp()
                            if ok:
                                set_temp_text = str(temp)

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

            self._camera_statuses[unit_name] = QLabel(camera_status_text)
            self._grid.addWidget(self._camera_statuses[unit_name], index+ROW_SHIFT, CURRENT_COL)
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
            self._cooling_labels[unit_name] = cooling_label
            CURRENT_COL += 1

            self._temp_displays[unit_name] = QLabel(camera_temp_text)
            self._grid.addWidget(self._temp_displays[unit_name],  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            self._set_temperature_display[unit_name] = QLabel(set_temp_text)
            self._grid.addWidget(self._set_temperature_display[unit_name],  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            bin_combo = QComboBox()
            bin_combo.addItems(["x1", "x2", "x4"])
            bin_combo.setCurrentText(current_binning_txt)
            self._grid.addWidget(bin_combo,  index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            capture_type_combo = QComboBox()
            capture_type_combo.addItems(["light", "flat", "dark", "bias"])
            self._grid.addWidget(capture_type_combo,  index+ROW_SHIFT, CURRENT_COL)
            self._dir_name_combo[unit_name] = capture_type_combo
            CURRENT_COL += 1
            self._capture_number_edits[unit_name] = QLineEdit("1")
            self._capture_number_edits[unit_name].returnPressed.connect(lambda u=unit_name: self._changed_capture_number(u))
            self._grid.addWidget(self._capture_number_edits[unit_name], index + ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

            self._start_capture_buttons[unit_name] = QPushButton("Start")
            self._start_capture_buttons[unit_name].setCheckable(True)
            self._start_capture_buttons[unit_name].setStyleSheet("background-color : black")
            self._start_capture_buttons[unit_name].clicked.connect(lambda always_false, u=unit_name: self._start_capture(u))
            self._grid.addWidget(self._start_capture_buttons[unit_name], index+ROW_SHIFT, CURRENT_COL)
            CURRENT_COL += 1

        self._main_layout.addLayout(self._grid)
        self._main_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.setLayout(self._main_layout)
        ######################
        self._add_task(5, self._refresh_statuses, "refresh_statuses")

    def _changed_capture_number(self, unit_name):
        if not self._reacheable[unit_name]:
            print(f"Cannot change capture number in {unit_name}")
            return

        number_raw = self._capture_number_edits[unit_name].text()
        try:
            number = int(number_raw)
        except Exception as e:
            logger.warning(f"Exception raised when changing capture number: {e}")
            return
        if number < 1 or number > 10000:
            logger.warning(f"Number of captures [{number}] for {unit_name} is outside allowed range (1-10000)")
            return
        self._capture_number[unit_name] = number

    def _refresh_statuses(self):
        for unit_name in self._config["units"]:
            if not self._reacheable[unit_name]:
                continue
            camera_index = self._cameras_combos[unit_name].currentIndex()
            ok, status = CameraRequester(unit_name, camera_index).get_status()
            if ok:
                logger.debug(f"Acquired status of {unit_name}: {status}")
                camera_status_text = status["state"]
                self._camera_statuses[unit_name].setText(camera_status_text)
            ok, camera_temp = CameraRequester(unit_name, camera_index).get_temperature()
            if ok:
                camera_temp_text = str(camera_temp)
                self._temp_displays[unit_name].setText(camera_temp_text)

    def _start_capture(self, unit_name):
        logger.debug(f"Start saving on {unit_name} pressed!")
        if not self._reacheable[unit_name]:
            print(f"Cannot start capturing in {unit_name}")
            return
        camera_index = self._cameras_combos[unit_name].currentIndex()
        button = self._start_capture_buttons[unit_name]
        is_checked = button.isChecked()
        if is_checked:
            number = self._capture_number[unit_name]
            dir_name = self._dir_name_combo[unit_name].currentText()
            logger.debug(f"Starting saving {number} frames in directory {dir_name} on {unit_name}")
            result = CameraRequester(unit_name, camera_index).start_saving(number, dir_name)
        else:
            logger.debug(f"Stopping saving on {unit_name}")
            result = CameraRequester(unit_name, camera_index).stop_saving()

        logger.debug(f"Result from saving @ {unit_name}: {result}")
        ok, status = CameraRequester(unit_name, camera_index).get_status()
        if ok:
            is_saving = (status["state"] == "SAVE")
            logger.debug(f"Current {unit_name} status = {status}, is_saving = {is_saving}")
        else:
            logger.warning(f"Could not get save status from {unit_name}")
            return

        if is_saving:
            button.setChecked(True)
            button.setStyleSheet("background-color : #228822")
            button.setText("Stop")
        else:
            button.setText("Start")
            button.setStyleSheet("background-color : black")
            button.setChecked(False)

    def _turn_all_coolers(self):
        value = self._all_coolers_button.isChecked()
        if value:
            print("Turning ON!")
            self._all_coolers_button.setChecked(True)
            self._all_coolers_button.setStyleSheet("background-color : #228822")
            self._all_coolers_button.setText("Turn off")
        else:
            print("Turning OFF!")
            self._all_coolers_button.setText("Turn on")
            self._all_coolers_button.setStyleSheet("background-color : black")
            self._all_coolers_button.setChecked(False)

        for unit_name in self._config["units"]:
            if not self._reacheable[unit_name]:
                continue
            camera_index = self._cameras_combos[unit_name].currentIndex()
            result = CameraRequester(unit_name, camera_index).set_cooler_on(value)
            onoroff = "on" if value else "off"
            print(f"Turning cooler at {unit_name} {onoroff}: {result}")

            ok, is_on = CameraRequester(unit_name, camera_index).get_cooler_on()
            if ok:
                camera_cooling_status_text = "YES" if is_on else "NO"
                camera_cooling_status_color = "green" if is_on else "red"
                self._cooling_labels[unit_name].setText(camera_cooling_status_text)
                self._cooling_labels[unit_name].setStyleSheet(f"color: {camera_cooling_status_color}")

    def _set_desired_temperature_for_all(self):
        value = int(self._set_temperature_edit.text())
        for unit_name in self._config["units"]:
            if not self._reacheable[unit_name]:
                continue
            camera_index = self._cameras_combos[unit_name].currentIndex()
            result = CameraRequester(unit_name, camera_index).set_set_temp(value)
            print(f"Setting cooler temperature at {unit_name} to {value}: {result}")
            ok, temp = CameraRequester(unit_name, camera_index).get_set_temp()
            if ok:
                self._set_temperature_display[unit_name].setText(str(temp))

    def _pressed_exp_edit(self, unit_name):
        if not self._reacheable[unit_name]:
            print(f"Cannot change exp in {unit_name}")
            return
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

    def _prepare_pingable_label(self, unit_name):
        self._ping_labels[unit_name].setText("YES" if self._pingable[unit_name] else "NO")
        pingable_color = "green" if self._pingable[unit_name] else "red"
        pingable_font = QFont()
        pingable_font.setBold(True)
        self._ping_labels[unit_name].setFont(pingable_font)
        self._ping_labels[unit_name].setStyleSheet(f"color: {pingable_color}")

    def _ping(self, unit_name):
        logger.debug(f"Pinging {unit_name}....")
        try:
            result = subprocess.check_output(["ping", unit_name, "-n", "1"]).decode("UTF-8")
        except Exception as e:
            logger.warning(f"Exception while pinging: {e}")
            return False
        f = result.find("Sent = 1, Received = 1")
        pingable = (f > 0)
        result_str = "succeeded" if pingable else "failed"
        logger.debug(f"......{result_str}")
        return pingable

    def _ping_units(self):
        for unit_name in self._config["units"]:
            self._pingable[unit_name] = self._ping(unit_name)
            self._prepare_pingable_label(unit_name)

    def _save_to_config(self, d: dict):
        self._config.update(d)
        save_config(self._config)

    def _refresh_cameras_combo(self, cameras_list, unit_name):
        if not self._reacheable[unit_name] or len(cameras_list) == 0:
            cameras_list = [EMPTY_CAMERA_LIST_ITEM]
        logger.debug(f"Obtained cameras list: {cameras_list} for {unit_name}")
        self._cameras_combos[unit_name].clear()
        self._cameras_combos[unit_name].addItems(cameras_list)

    def _refresh_servers(self):
        self._ping_units()

        for unit_name in self._config["units"]:
            if self._pingable[unit_name]:
                # try:
                cameras_list = get_cameras_list(unit_name)
                # except Exception as e:
                #     cameras_list = None
                #     print(f"Exception while getting cameras list: {e}")
                print("WTF?!?!")
                if cameras_list is None:
                    try:
                        result = subprocess.check_output([f"ssh pi@{unit_name} \"supervisorctl restart gunicorn\""]).decode("UTF-8")
                    except Exception as e:
                        print(f"Exception while checking output: {e}")
                        continue
                    print(f"Result of restarting server: {result}")
                    cameras_list = get_cameras_list(unit_name)
                if cameras_list is None:
                    print(f"Failed to get cameras even after gunicorn restart. Continuing to next...")
                    continue
                print(f"Trying to refresh cameras combo for {unit_name} with {cameras_list}")
                self._reacheable[unit_name] = True
                self._refresh_cameras_combo(cameras_list)

