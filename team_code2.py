import sys
import os
import json
import threading
from datetime import timedelta
import hashlib

# PyQt5가 설치된 경로를 찾아서 플러그인 위치를 강제로 등록
import PyQt5
qt_root_path = os.path.dirname(PyQt5.__file__)
plugin_path = os.path.join(qt_root_path, 'Qt5', 'plugins')
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path

# PyQt5 and Pillow
try:
    from PyQt5.QtGui import QFont, QIcon, QPixmap, QImage, QColor, QPalette
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout,
        QHBoxLayout, QPushButton, QLabel, QLineEdit,
        QTableWidget, QTableWidgetItem, QHeaderView,
        QAbstractItemView, QMenu, QInputDialog, QMessageBox,
        QComboBox, QFileDialog, QDialog, QSlider, QStyle, QStackedLayout, QScrollArea, QFrame,
        QTimeEdit, QDialogButtonBox, QStackedWidget,
    )
    from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QObject, QThread, QTimer, QPoint, QSize, QTime
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    from PyQt5.QtMultimediaWidgets import QVideoWidget

    from PIL import Image
except ImportError as e:
    print(f"필수 라이브러리가 설치되지 않았습니다: {e}")
    print("pip install PyQt5 Pillow opencv-python PyQt5-sip")
    sys.exit(1)

import cv2
import subprocess

# --- Custom Clickable Widgets ---
class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            if self.orientation() == Qt.Horizontal:
                # Set value based on click position
                val = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.x(), self.width())
                self.setValue(val)

class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

# --- Thumbnail Utility Function ---
def _create_thumbnail_file(video_path, thumb_path, size=(480, 270)):
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video {video_path}")
            return False
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            cap.release()
            return False
            
        pos = int(total_frames * 0.1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        cap.release()

        if ret:
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img.thumbnail(size, Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=85)
            return True
    except Exception as e:
        print(f"Error generating thumbnail for {video_path}: {e}")
    return False

def _create_thumbnail_for_timestamp(video_path, thumb_path, time_seconds, size=(160, 90)):
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video {video_path}")
            return False
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0:
            return False # Cannot seek without fps
            
        frame_pos = int(time_seconds * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        ret, frame = cap.read()
        cap.release()

        if ret:
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img.thumbnail(size, Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=80)
            return True
    except Exception as e:
        print(f"Error generating timestamp thumbnail for {video_path} at {time_seconds}s: {e}")
    return False

# --- Video Player Widget with Overlay Controls ---
class VideoContainer(QWidget):
    def __init__(self, media_player, parent=None):
        super().__init__(parent)
        self.media_player = media_player
        self.setFixedSize(960, 540)
        self.setStyleSheet("background-color: black;")
        self.setMouseTracking(True)

        # 1. Main Display Area (Video or Thumbnail)
        self.display_stack = QStackedWidget(self)
        
        self.video_widget = QVideoWidget()
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")
        
        # Enable mouse tracking for all relevant widgets
        self.video_widget.setMouseTracking(True)
        self.thumbnail_label.setMouseTracking(True)
        
        self.display_stack.addWidget(self.video_widget)
        self.display_stack.addWidget(self.thumbnail_label)

        # 2. Overlay UI Elements (children of this container)
        self.big_play_btn = QPushButton(self)
        self.big_play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.big_play_btn.setIconSize(QSize(64, 64))
        self.big_play_btn.setFixedSize(80, 80)
        self.big_play_btn.setStyleSheet("background-color: rgba(0,0,0,90); border: 1px solid white; border-radius: 40px;")
        self.big_play_btn.hide()

        self.controls_widget = QWidget(self)
        self.controls_widget.setStyleSheet("background-color: rgba(0,0,0,128); border-radius: 10px;")
        self.controls_widget.setMouseTracking(True)
        controls_layout = QHBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(5, 5, 5, 5)

        self.play_pause_btn = QPushButton()
        self.play_pause_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_pause_btn.setStyleSheet("background-color: white; border: 1px solid white; border-radius: 5px;")
        
        self.current_time_label = QLabel("00:00")
        self.current_time_label.setStyleSheet("color: white;")

        self.seek_slider = ClickableSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)

        self.total_time_label = QLabel("00:00")
        self.total_time_label.setStyleSheet("color: white;")
        
        self.volume_label = ClickableLabel()
        self.volume_label.setPixmap(self.style().standardIcon(QStyle.SP_MediaVolume).pixmap(16,16))

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100); self.volume_slider.setValue(80); self.volume_slider.setFixedWidth(100)

        controls_layout.addWidget(self.play_pause_btn)
        controls_layout.addWidget(self.current_time_label)
        controls_layout.addWidget(self.seek_slider)
        controls_layout.addWidget(self.total_time_label)
        controls_layout.addWidget(self.volume_label)
        controls_layout.addWidget(self.volume_slider)
        self.controls_widget.hide()

        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(2500)
        self.hide_timer.timeout.connect(self.auto_hide_controls)

    def auto_hide_controls(self):
        if self.media_player and self.media_player.state() != QMediaPlayer.PlayingState:
            return
        if self.controls_widget.underMouse():
            return
        self.controls_widget.hide()

    def set_thumbnail(self, pixmap):
        if pixmap and not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.thumbnail_label.setPixmap(QPixmap())
            self.thumbnail_label.setText("썸네일 없음")
        self.display_stack.setCurrentWidget(self.thumbnail_label)
    
    def show_video_surface(self):
        self.display_stack.setCurrentWidget(self.video_widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Manually manage geometry of all children
        self.display_stack.setGeometry(self.rect())
        self.big_play_btn.move(self.rect().center() - self.big_play_btn.rect().center())
        self.controls_widget.setGeometry(10, self.height() - 50, self.width() - 20, 40)

    def enterEvent(self, event):
        # Show controls if a video is loaded (i.e., playing, paused, or stopped with thumbnail showing)
        if self.media_player.state() in [QMediaPlayer.PlayingState, QMediaPlayer.PausedState] or self.big_play_btn.isVisible():
            self.controls_widget.show()
            self.controls_widget.raise_()
            self.hide_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hide_timer.stop()
        self.controls_widget.hide()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        if self.media_player.state() in [QMediaPlayer.PlayingState, QMediaPlayer.PausedState] or self.big_play_btn.isVisible():
            self.controls_widget.show()
            self.controls_widget.raise_()
            self.hide_timer.start()
        super().mouseMoveEvent(event)

# --- Worker classes ---
class Worker(QObject):
    finished = pyqtSignal(list)
    progress = pyqtSignal(str)

    def __init__(self, folder_path, thumbnail_dir):
        super().__init__()
        self.folder_path = folder_path
        self.thumbnail_dir = thumbnail_dir
        self.is_running = True

    def run(self):
        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'}
        found_videos = []
        for root_dir, _, files in os.walk(self.folder_path):
            if not self.is_running: break
            for file in files:
                if not self.is_running: break
                if os.path.splitext(file)[1].lower() in video_extensions:
                    full_path = os.path.join(root_dir, file).replace('\\', '/')
                    self.progress.emit(f"Processing: {file}")
                    try:
                        thumbnail_filename = hashlib.md5(full_path.encode()).hexdigest() + ".jpg"
                        thumbnail_path = os.path.join(self.thumbnail_dir, thumbnail_filename).replace('\\', '/')
                        if not os.path.exists(thumbnail_path):
                            _create_thumbnail_file(full_path, thumbnail_path)

                        duration_str = "0:00:00"
                        try:
                            cap = cv2.VideoCapture(full_path)
                            if cap.isOpened():
                                fps = cap.get(cv2.CAP_PROP_FPS)
                                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                                duration_sec = frame_count / fps if fps > 0 else 0
                                duration_str = str(timedelta(seconds=int(duration_sec)))
                                cap.release()
                        except Exception:
                            pass # Could fail on some formats, fallback to 0

                        found_videos.append({
                            "path": full_path, "filename": os.path.splitext(file)[0],
                            "extension": os.path.splitext(file)[1], "duration": duration_str,
                            "tags": "", "thumbnail_path": thumbnail_path
                        })
                    except Exception as e:
                        print(f"Error processing {full_path}: {e}")
        self.finished.emit(found_videos)

    def stop(self):
        self.is_running = False

class ThumbnailGenerator(QObject):
    finished = pyqtSignal(str)
    def __init__(self, video_path, thumbnail_path):
        super().__init__()
        self.video_path = video_path
        self.thumbnail_path = thumbnail_path
    def run(self):
        if _create_thumbnail_file(self.video_path, self.thumbnail_path):
            self.finished.emit(self.thumbnail_path)
        else:
            self.finished.emit("")

class BatchThumbnailGenerator(QObject):
    thumbnail_ready = pyqtSignal(int, str)
    finished = pyqtSignal()
    def __init__(self, video_data):
        super().__init__()
        self.video_data = video_data
        self.is_running = True
    def run(self):
        for i, video in enumerate(self.video_data):
            if not self.is_running: break
            thumb_path = video.get("thumbnail_path")
            if thumb_path and not os.path.exists(thumb_path):
                if _create_thumbnail_file(video["path"], thumb_path):
                    self.thumbnail_ready.emit(i, thumb_path)
        self.finished.emit()
    def stop(self):
        self.is_running = False

# --- Add Timeline Dialog ---
class AddTimelineDialog(QDialog):
    def __init__(self, max_duration_secs=86399, parent=None): # 86399 seconds = 23:59:59
        super().__init__(parent)
        self.setWindowTitle("타임라인 추가")

        layout = QVBoxLayout(self)

        # Time input
        self.time_edit = QTimeEdit(self)
        self.time_edit.setDisplayFormat("HH:mm:ss")
        max_time = QTime.fromMSecsSinceStartOfDay(max_duration_secs * 1000)
        self.time_edit.setMaximumTime(max_time)
        layout.addWidget(QLabel("시간 (HH:mm:ss):"))
        layout.addWidget(self.time_edit)

        # Description input
        self.description_edit = QLineEdit(self)
        layout.addWidget(QLabel("설명:"))
        layout.addWidget(self.description_edit)

        # OK and Cancel buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def get_data(self):
        time_qtime = self.time_edit.time()
        time_in_seconds = time_qtime.hour() * 3600 + time_qtime.minute() * 60 + time_qtime.second()
        return {
            "time": time_in_seconds,
            "description": self.description_edit.text()
        }

# --- Timeline Entry Widget ---
class TimelineEntryWidget(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, timeline_data, parent=None):
        super().__init__(parent)
        self.timeline_data = timeline_data
        
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoFillBackground(True) # Important for background color
        self.set_highlight(False) # Set default background

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(96, 54)
        self.thumb_label.setStyleSheet("border: 1px solid #ccc; background-color: black;")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(timeline_data.get("thumb_path"))
        if not pixmap.isNull():
            self.thumb_label.setPixmap(pixmap.scaled(self.thumb_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.thumb_label.setText("썸네일 없음")
        layout.addWidget(self.thumb_label)
        
        # Info (Time + Desc)
        time_str = str(timedelta(seconds=timeline_data.get("time", 0)))
        desc_str = timeline_data.get("text", "")
        info_text = f"<b>{time_str}</b><br>{desc_str}"
        
        self.info_label = QLabel(info_text)
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignVCenter)
        layout.addWidget(self.info_label, 1) # Give it stretch factor

    def mousePressEvent(self, event):
        self.clicked.emit(self.timeline_data.get("time", 0))
        super().mousePressEvent(event)

    def set_highlight(self, highlighted):
        p = self.palette()
        if highlighted:
            # A light blue color
            p.setColor(self.backgroundRole(), QColor(224, 236, 255)) 
        else:
            # Default window color
            p.setColor(self.backgroundRole(), QApplication.style().standardPalette().color(QPalette.Window))
        self.setPalette(p)


# --- Main Application Window ---
class VideoManagerApp(QMainWindow):
    @staticmethod
    def ms_to_time_string(ms):
        """Converts milliseconds to HH:MM:SS or MM:SS string."""
        seconds = int(ms / 1000)
        minutes = int(seconds / 60)
        hours = int(minutes / 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes % 60:02d}:{seconds % 60:02d}"
        else:
            return f"{minutes:02d}:{seconds % 60:02d}"

    def __init__(self):
        super().__init__()
        self.setWindowTitle('똑똑한 영상 관리자 (Smart Video Manager)')
        self.video_data = [] # Master list of all videos from JSON
        self.current_view_videos = [] # List of videos currently shown in the table
        self.json_path = "videos.json"
        self.thumbnail_dir = ".thumbnails"
        os.makedirs(self.thumbnail_dir, exist_ok=True)
        
        self.current_selected_path = None
        self.scan_thread, self.scan_worker = None, None
        self.thumbnail_gen_thread, self.thumbnail_gen_worker = None, None
        self.batch_thumb_thread, self.batch_thumb_worker = None, None
        
        self.timeline_widgets = []
        
        self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        
        self.init_ui()
        self.connect_signals()
        self.load_data()
        self.update_volume_icon() # Set initial icon state

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)

        top_controls_layout = QHBoxLayout()
        self.select_folder_btn = QPushButton("폴더 선택")
        self.filter_combo = QComboBox(); self.filter_combo.addItems(["All", "Filename", "Tag"])
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("검색어를 입력하세요...")
        top_controls_layout.addWidget(self.select_folder_btn)
        top_controls_layout.addWidget(self.filter_combo)
        top_controls_layout.addWidget(self.search_input)
        main_layout.addLayout(top_controls_layout)

        middle_layout = QHBoxLayout()
        
        self.video_container = VideoContainer(self.media_player)
        self.media_player.setVideoOutput(self.video_container.video_widget)

        info_layout = QVBoxLayout()
        self.selected_filename_label = QLabel("-")
        self.selected_tags_label = QLabel("-")
        self.play_button_main = QPushButton("선택한 영상 재생")

        info_layout.addWidget(QLabel("파일명:"))
        info_layout.addWidget(self.selected_filename_label)
        info_layout.addSpacing(20)
        info_layout.addWidget(QLabel("태그:"))
        info_layout.addWidget(self.selected_tags_label)

        # --- 타임라인 섹션 ---
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        info_layout.addSpacing(10)
        info_layout.addWidget(line)
        info_layout.addSpacing(10)

        info_layout.addWidget(QLabel("타임라인:"))
        
        timeline_scroll = QScrollArea()
        timeline_scroll.setWidgetResizable(True)
        timeline_scroll_content = QWidget()
        self.timeline_list_layout = QVBoxLayout(timeline_scroll_content)
        self.timeline_list_layout.setAlignment(Qt.AlignTop)
        
        self.no_timeline_label = QLabel("생성된 타임라인 없음")
        self.no_timeline_label.setAlignment(Qt.AlignCenter)
        self.timeline_list_layout.addWidget(self.no_timeline_label)

        timeline_scroll.setWidget(timeline_scroll_content)
        info_layout.addWidget(timeline_scroll)

        self.add_timeline_btn = QPushButton("타임라인 추가하기")
        info_layout.addWidget(self.add_timeline_btn)
        # --- 타임라인 섹션 끝 ---

        info_layout.addStretch(1)
        info_layout.addWidget(self.play_button_main)
        
        middle_layout.addWidget(self.video_container)
        middle_layout.addLayout(info_layout)
        
        main_layout.addLayout(middle_layout)

        self.file_list = QTableWidget()
        self.file_list.setColumnCount(5)
        self.file_list.setHorizontalHeaderLabels(["썸네일", "파일명", "길이", "태그", "경로"])
        header = self.file_list.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents); header.setSectionResizeMode(1, QHeaderView.Interactive); header.setSectionResizeMode(2, QHeaderView.ResizeToContents); header.setSectionResizeMode(3, QHeaderView.Interactive); header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.file_list.setColumnWidth(1, 200); self.file_list.setColumnWidth(3, 150)
        self.file_list.verticalHeader().setDefaultSectionSize(70); self.file_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_list.setEditTriggers(QAbstractItemView.NoEditTriggers); self.file_list.setSelectionMode(QAbstractItemView.SingleSelection)
        main_layout.addWidget(self.file_list)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage("준비 완료.")
        self.resize(1600, 900)

    def connect_signals(self):
        self.select_folder_btn.clicked.connect(self.select_folder)
        self.search_input.textChanged.connect(self.filter_list)
        self.file_list.itemSelectionChanged.connect(self.update_info_panel)
        self.file_list.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.play_button_main.clicked.connect(self.play_video)
        
        self.media_player.stateChanged.connect(self.media_state_changed)
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.positionChanged.connect(self.update_timeline_highlight)
        self.media_player.durationChanged.connect(self.duration_changed)
        self.media_player.volumeChanged.connect(self.update_volume_icon)
        self.media_player.mutedChanged.connect(self.update_volume_icon)
        
        controls = self.video_container
        controls.play_pause_btn.clicked.connect(self.toggle_play_pause)
        controls.big_play_btn.clicked.connect(self.play_video)
        controls.seek_slider.valueChanged.connect(self.set_position)
        controls.volume_slider.valueChanged.connect(self.media_player.setVolume)
        controls.volume_label.clicked.connect(self.toggle_mute)

        self.add_timeline_btn.clicked.connect(self.open_add_timeline_dialog)

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "비디오 폴더를 선택하세요", self.current_selected_path or os.path.expanduser("~"))
        if not folder_path:
            return

        self._stop_all_threads()
        self.clear_info_panel()
        self.file_list.setRowCount(0)
        self.status_bar.showMessage(f"폴더 스캔 중: {folder_path}...")

        self.scan_thread = QThread(self)
        self.scan_worker = Worker(folder_path, self.thumbnail_dir)
        self.scan_worker.moveToThread(self.scan_thread)

        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.progress.connect(lambda msg: self.status_bar.showMessage(msg))
        self.scan_worker.finished.connect(self.on_scan_finished)
        
        self.scan_thread.start()

    def on_scan_finished(self, found_videos):
        self.status_bar.showMessage(f"{len(found_videos)}개의 비디오를 찾았습니다. 데이터베이스 업데이트 중...")
        
        existing_videos_map = {v['path']: v for v in self.video_data}
        new_videos_added_to_db = 0
        
        for i, found_video in enumerate(found_videos):
            path = found_video['path']
            if path in existing_videos_map:
                existing_video = existing_videos_map[path]
                found_videos[i]['tags'] = existing_video.get('tags', '')
                found_videos[i]['timelines'] = existing_video.get('timelines', [])
            else:
                self.video_data.append(found_video)
                new_videos_added_to_db += 1

        self.current_view_videos = found_videos
        self.populate_file_list(self.current_view_videos)
        
        if new_videos_added_to_db > 0:
            self.save_data()
            
        self.status_bar.showMessage(f"스캔 완료. {len(self.current_view_videos)}개의 영상 표시. {new_videos_added_to_db}개 신규 추가.", 5000)
        self._stop_all_threads(stop_batch=False)

    def open_add_timeline_dialog(self):
        if not self.current_selected_path:
            QMessageBox.warning(self, "경고", "먼저 영상을 선택해주세요.")
            return

        video = next((v for v in self.video_data if v["path"] == self.current_selected_path), None)
        if not video:
            return

        duration_str = video.get("duration", "0:00:00")
        try:
            parts = list(map(int, duration_str.split(':')))
            if len(parts) == 3:
                h, m, s = parts
                duration_secs = h * 3600 + m * 60 + s
            else:
                duration_secs = 0
        except (ValueError, TypeError):
            duration_secs = 0

        dialog = AddTimelineDialog(max_duration_secs=duration_secs, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["description"].strip():
                QMessageBox.warning(self, "경고", "설명을 입력해야 합니다.")
                return

            thumb_hash = hashlib.md5(f"{video['path']}_{data['time']}".encode()).hexdigest()
            timeline_thumb_path = os.path.join(self.thumbnail_dir, f"timeline_{thumb_hash}.jpg").replace('\\', '/')

            _create_thumbnail_for_timestamp(video['path'], timeline_thumb_path, data['time'])

            if "timelines" not in video:
                video["timelines"] = []
            
            video["timelines"].append({
                "time": data["time"],
                "text": data["description"].strip(),
                "thumb_path": timeline_thumb_path
            })
            video["timelines"].sort(key=lambda t: t["time"])

            self.save_data()
            self.update_info_panel()

    def _get_current_view_from_table(self):
        paths = [self.file_list.item(row, 4).text() for row in range(self.file_list.rowCount())]
        # Return the full video objects from the master list, preserving order
        path_to_video_map = {v['path']: v for v in self.video_data}
        return [path_to_video_map[p] for p in paths if p in path_to_video_map]

    def rename_video_file(self, video):
        current_filename_no_ext = video["filename"]
        
        dialog = QInputDialog(self)
        dialog.setWindowTitle("이름 수정")
        dialog.setLabelText("새 파일명을 입력하세요 (확장자 제외):")
        dialog.setTextValue(current_filename_no_ext)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        ok = dialog.exec_()
        new_filename_no_ext = dialog.textValue()
        
        if ok and new_filename_no_ext and new_filename_no_ext != current_filename_no_ext:
            # Preserve current view before making changes
            self.current_view_videos = self._get_current_view_from_table()

            old_path = video["path"]
            file_dir = os.path.dirname(old_path)
            ext = video["extension"]
            new_filename_with_ext = new_filename_no_ext + ext
            new_path = os.path.join(file_dir, new_filename_with_ext).replace('\\', '/')

            if os.path.exists(new_path):
                QMessageBox.warning(self, "오류", "같은 이름의 파일이 이미 존재합니다.")
                return

            try:
                os.rename(old_path, new_path)
                
                old_thumb_path = video["thumbnail_path"]
                new_thumb_hash = hashlib.md5(new_path.encode()).hexdigest() + ".jpg"
                new_thumb_path = os.path.join(self.thumbnail_dir, new_thumb_hash).replace('\\', '/')
                if os.path.exists(old_thumb_path):
                    os.rename(old_thumb_path, new_thumb_path)
                
                video["path"] = new_path
                video["filename"] = new_filename_no_ext
                video["thumbnail_path"] = new_thumb_path

                self.save_data()
                # Refresh the list with the preserved view
                self.populate_file_list(self.current_view_videos)
                self.update_info_panel()
                QMessageBox.information(self, "성공", "파일 이름이 변경되었습니다.")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"이름 변경 실패: {e}")

    def edit_tags_for_video(self, video):
        current_tags = video.get("tags", "")
        
        dialog = QInputDialog(self)
        dialog.setWindowTitle("태그 수정")
        dialog.setLabelText("태그를 입력하세요 (쉼표로 구분):")
        dialog.setTextValue(current_tags)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        ok = dialog.exec_()
        new_tags = dialog.textValue()

        if ok:
            # Preserve the current view before making changes
            self.current_view_videos = self._get_current_view_from_table()
            
            video["tags"] = new_tags.strip()
            self.save_data()

            # Refresh the list with the same set of videos, now with updated tags
            self.populate_file_list(self.current_view_videos)
            self.update_info_panel()

    def show_path_for_copy(self, path):
        dialog = QDialog(self)
        dialog.setWindowTitle("전체 경로 복사")
        dialog.setMinimumWidth(600)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        layout = QVBoxLayout()
        path_edit = QLineEdit(path)
        path_edit.selectAll()
        path_edit.setReadOnly(True)
        ok_button = QPushButton("닫기")
        ok_button.clicked.connect(dialog.accept)
        layout.addWidget(path_edit)
        layout.addWidget(ok_button)
        dialog.setLayout(layout)
        dialog.exec_()

    def update_info_panel(self):
        self.media_player.stop()

        controls = self.video_container
        controls.seek_slider.blockSignals(True)
        controls.seek_slider.setRange(0, 0)
        controls.seek_slider.setValue(0)
        controls.seek_slider.blockSignals(False)
        controls.current_time_label.setText("00:00")
        controls.total_time_label.setText("00:00")

        selected_rows = self.file_list.selectionModel().selectedRows()
        if not selected_rows: self.clear_info_panel(); return

        path_item = self.file_list.item(selected_rows[0].row(), 4)
        if not path_item: self.clear_info_panel(); return
        
        path = path_item.text()
        self.current_selected_path = path
        video = next((v for v in self.video_data if v["path"] == path), None)

        for i in reversed(range(self.timeline_list_layout.count())):
            widget = self.timeline_list_layout.itemAt(i).widget()
            if widget and widget != self.no_timeline_label:
                widget.deleteLater()
        self.no_timeline_label.hide()

        if video:
            self.selected_filename_label.setText(video.get("filename", "-"))
            self.selected_tags_label.setText(video.get("tags", "-"))
            thumb_path = video.get("thumbnail_path")
            self.video_container.set_thumbnail(QPixmap(thumb_path) if thumb_path and os.path.exists(thumb_path) else QPixmap())
            self.video_container.big_play_btn.show()

            if "timelines" not in video: video["timelines"] = []
            timelines = video["timelines"]

            self.timeline_widgets.clear()
            if timelines:
                self.no_timeline_label.hide()
                for timeline in timelines:
                    widget = TimelineEntryWidget(timeline)
                    widget.clicked.connect(lambda time_sec: self.media_player.setPosition(time_sec * 1000))
                    self.timeline_list_layout.addWidget(widget)
                    self.timeline_widgets.append(widget)
            else:
                self.no_timeline_label.show()
        else:
            self.clear_info_panel()

    def clear_info_panel(self):
        self.media_player.stop()
        self.selected_filename_label.setText("-")
        self.selected_tags_label.setText("-")
        self.video_container.set_thumbnail(QPixmap())
        self.video_container.big_play_btn.hide()
        self.current_selected_path = None

        for i in reversed(range(self.timeline_list_layout.count())):
            widget = self.timeline_list_layout.itemAt(i).widget()
            if widget and widget != self.no_timeline_label:
                widget.deleteLater()
        self.no_timeline_label.show()

    def play_video(self):
        if self.current_selected_path:
            if self.media_player.state() == QMediaPlayer.PausedState:
                self.media_player.play()
            elif self.media_player.state() == QMediaPlayer.StoppedState:
                self.video_container.show_video_surface()
                url = QUrl.fromLocalFile(self.current_selected_path)
                self.media_player.setMedia(QMediaContent(url))
                self.media_player.setVolume(self.video_container.volume_slider.value())
                self.media_player.play()

    def toggle_play_pause(self):
        if self.media_player.state() == QMediaPlayer.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def toggle_mute(self):
        self.media_player.setMuted(not self.media_player.isMuted())

    def update_volume_icon(self):
        if self.media_player.isMuted() or self.media_player.volume() == 0:
            icon = QStyle.SP_MediaVolumeMuted
        else:
            icon = QStyle.SP_MediaVolume
        self.video_container.volume_label.setPixmap(self.style().standardIcon(icon).pixmap(16, 16))

    def media_state_changed(self, state):
        controls = self.video_container
        if state == QMediaPlayer.PlayingState:
            controls.play_pause_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            controls.big_play_btn.hide()
        else:
            controls.play_pause_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            if state == QMediaPlayer.StoppedState and self.current_selected_path:
                thumb_path = next((v for v in self.video_data if v["path"] == self.current_selected_path), {}).get("thumbnail_path")
                self.video_container.set_thumbnail(QPixmap(thumb_path) if thumb_path and os.path.exists(thumb_path) else QPixmap())
                controls.big_play_btn.show()

    def update_timeline_highlight(self, position_ms):
        if not self.timeline_widgets:
            return

        position_sec = position_ms / 1000
        current_timeline_widget = None
        
        for widget in self.timeline_widgets:
            if widget.timeline_data['time'] <= position_sec:
                current_timeline_widget = widget
            else:
                break
        
        for widget in self.timeline_widgets:
            widget.set_highlight(widget == current_timeline_widget)

    def position_changed(self, position):
        slider = self.video_container.seek_slider
        slider.blockSignals(True)
        slider.setValue(position)
        slider.blockSignals(False)
        self.video_container.current_time_label.setText(self.ms_to_time_string(position))

    def duration_changed(self, duration): 
        self.video_container.seek_slider.setRange(0, duration)
        self.video_container.total_time_label.setText(self.ms_to_time_string(duration))

    def set_position(self, position):
        if self.media_player.position() != position:
            self.media_player.setPosition(position)
    
    def closeEvent(self, event):
        self.media_player.stop()
        self._stop_all_threads()
        event.accept()

    def on_cell_double_clicked(self, row, column):
        path_item = self.file_list.item(row, 4)
        if not path_item: return
        video = next((v for v in self.video_data if v["path"] == path_item.text()), None)
        if not video: return
        if column == 1: self.rename_video_file(video)
        elif column == 3: self.edit_tags_for_video(video)
        elif column == 4: self.show_path_for_copy(path_item.text())

    def filter_list(self):
        search_term = self.search_input.text().lower()
        filter_by = self.filter_combo.currentText()
        
        # Start with the currently viewed videos if a scan has been performed,
        # otherwise use the full database.
        source_data = self.current_view_videos if self.current_view_videos else self.video_data
        
        if not search_term:
            self.populate_file_list(source_data)
            return
        
        filtered_videos = [
            v for v in source_data
            if (filter_by == "All" and (search_term in v.get("filename", "").lower() or search_term in v.get("tags", "").lower())) or
               (filter_by == "Filename" and search_term in v.get("filename", "").lower()) or
               (filter_by == "Tag" and search_term in v.get("tags", "").lower())
        ]
        self.populate_file_list(filtered_videos)
    
    def populate_file_list(self, data=None):
        self.file_list.setRowCount(0)
        videos_to_display = data if data is not None else self.video_data
        self.file_list.setRowCount(len(videos_to_display))
        for i, video in enumerate(videos_to_display):
            thumb_path = video.get("thumbnail_path")
            if thumb_path and os.path.exists(thumb_path):
                pixmap = QPixmap(thumb_path)
                if not pixmap.isNull():
                    thumb_label = QLabel()
                    thumb_label.setPixmap(pixmap.scaled(96, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    thumb_label.setAlignment(Qt.AlignCenter)
                    self.file_list.setCellWidget(i, 0, thumb_label)
            
            self.file_list.setItem(i, 1, QTableWidgetItem(video.get("filename", "")))
            self.file_list.setItem(i, 2, QTableWidgetItem(video.get("duration", "0:00:00")))
            self.file_list.setItem(i, 3, QTableWidgetItem(video.get("tags", "")))
            self.file_list.setItem(i, 4, QTableWidgetItem(video.get("path", "")))

    def load_data(self):
        if not os.path.exists(self.json_path): self.video_data = []; return
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self.video_data = json.load(f)
            # On initial load, the view contains all videos from the database
            self.current_view_videos = self.video_data
            self.populate_file_list(self.current_view_videos)
        except (json.JSONDecodeError, TypeError):
            self.status_bar.showMessage(f"오류: {self.json_path} 파일을 읽을 수 없습니다.")
            self.video_data = []

    def save_data(self):
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.video_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.status_bar.showMessage(f"데이터 저장 오류: {e}")

    def _stop_all_threads(self, stop_scan=True, stop_batch=True):
        if stop_scan and self.scan_worker: self.scan_worker.stop()
        if stop_batch and self.batch_thumb_worker: self.batch_thumb_worker.stop()
        if stop_scan and self.scan_thread and self.scan_thread.isRunning(): self.scan_thread.quit(); self.scan_thread.wait()
        if stop_batch and self.batch_thumb_thread and self.batch_thumb_thread.isRunning(): self.batch_thumb_thread.quit(); self.batch_thumb_thread.wait()
        
    def start_batch_thumbnail_generation(self): pass
    def on_batch_thumbnail_ready(self,r,t): pass
    def on_thumbnail_generated(self,p): pass
    def on_thumbnail_thread_finished(self): pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = VideoManagerApp()
    ex.show()
    sys.exit(app.exec_())
