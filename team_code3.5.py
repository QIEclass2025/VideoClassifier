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
        QTimeEdit, QDialogButtonBox, QStackedWidget, QSplitter, QSizePolicy
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
        if not cap.isOpened(): return False
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0: cap.release(); return False
            
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
        print(f"Thumbnail Error: {e}")
    return False


def _create_thumbnail_for_timestamp(video_path, thumb_path, time_seconds, size=(160, 90)):
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): return False
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0: return False
            
        frame_pos = int(time_seconds * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        ret, frame = cap.read()
        cap.release()


        if ret:
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img.thumbnail(size, Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=80)
            return True
    except Exception:
        pass
    return False


# --- Video Player Widget ---
class VideoContainer(QWidget):
    def __init__(self, media_player, parent=None):
        super().__init__(parent)
        self.media_player = media_player
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(640, 360)
        
        # QPalette 사용 (렌더링 충돌 방지)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.Window, Qt.black)
        self.setPalette(pal)
        
        self.setMouseTracking(True)


        self.display_stack = QStackedWidget(self)
        
        # QVideoWidget 설정 (스타일시트 제거)
        self.video_widget = QVideoWidget()
        v_pal = self.video_widget.palette()
        v_pal.setColor(QPalette.Window, Qt.black)
        self.video_widget.setPalette(v_pal)
        self.video_widget.setAutoFillBackground(True)
        self.video_widget.setMouseTracking(True)


        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("background-color: #0f0f0f; color: #aaaaaa; border: none;")
        self.thumbnail_label.setText("재생할 영상을 선택하세요")
        self.thumbnail_label.setMouseTracking(True)
        
        self.display_stack.addWidget(self.video_widget)
        self.display_stack.addWidget(self.thumbnail_label)


        # Overlay UI
        self.big_play_btn = QPushButton(self)
        self.big_play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.big_play_btn.setIconSize(QSize(64, 64))
        self.big_play_btn.setFixedSize(80, 80)
        self.big_play_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0,0,0,150); 
                border: 2px solid white; 
                border-radius: 40px;
            }
            QPushButton:hover {
                background-color: rgba(255,0,0,200);
                border: 2px solid #ff0000;
            }
        """)
        self.big_play_btn.hide()


        # Controls Bar
        self.controls_widget = QWidget(self)
        self.controls_widget.setStyleSheet("background-color: rgba(15,15,15,0.9); border-radius: 5px;")
        self.controls_widget.setMouseTracking(True)
        controls_layout = QHBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(10, 5, 10, 5)


        self.play_pause_btn = QPushButton()
        self.play_pause_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_pause_btn.setFixedSize(30, 30)
        # [수정] 재생/정지 버튼을 흰색으로 변경
        self.play_pause_btn.setStyleSheet("""
            QPushButton {
                background-color: white; 
                border: none; 
                border-radius: 15px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        
        self.current_time_label = QLabel("00:00")
        self.current_time_label.setStyleSheet("color: white; font-weight: bold; background: transparent; border: none;")


        self.seek_slider = ClickableSlider(Qt.Horizontal)
        self.seek_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #505050; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ff0000; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
            QSlider::sub-page:horizontal { background: #ff0000; border-radius: 2px; }
        """)


        self.total_time_label = QLabel("00:00")
        self.total_time_label.setStyleSheet("color: white; font-weight: bold; background: transparent; border: none;")
        
        self.volume_label = ClickableLabel()
        self.volume_label.setPixmap(self.style().standardIcon(QStyle.SP_MediaVolume).pixmap(16,16))
        self.volume_label.setStyleSheet("color: white; background: transparent; border: none;")


        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100); self.volume_slider.setValue(80); self.volume_slider.setFixedWidth(80)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #505050; }
            QSlider::handle:horizontal { background: white; width: 10px; height: 10px; margin: -3px 0; border-radius: 5px; }
            QSlider::sub-page:horizontal { background: white; }
        """)


        controls_layout.addWidget(self.play_pause_btn)
        controls_layout.addWidget(self.current_time_label)
        controls_layout.addWidget(self.seek_slider)
        controls_layout.addWidget(self.total_time_label)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(self.volume_label)
        controls_layout.addWidget(self.volume_slider)
        self.controls_widget.hide()


        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(2500)
        self.hide_timer.timeout.connect(self.auto_hide_controls)


    def auto_hide_controls(self):
        if self.media_player and self.media_player.state() != QMediaPlayer.PlayingState: return
        if self.controls_widget.underMouse(): return
        self.controls_widget.hide()


    def set_thumbnail(self, pixmap):
        if pixmap and not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.thumbnail_label.setText("")
        else:
            self.thumbnail_label.setPixmap(QPixmap())
            self.thumbnail_label.setText("썸네일 없음")
        self.display_stack.setCurrentWidget(self.thumbnail_label)
    
    def show_video_surface(self):
        self.display_stack.setCurrentWidget(self.video_widget)


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.display_stack.setGeometry(self.rect())
        self.big_play_btn.move(self.rect().center() - self.big_play_btn.rect().center())
        self.controls_widget.setGeometry(10, self.height() - 50, self.width() - 20, 45)


    def enterEvent(self, event):
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


# --- Workers (로직 동일) ---
class Worker(QObject):
    finished = pyqtSignal(list)
    progress = pyqtSignal(str)
    def __init__(self, folder_path, thumbnail_dir):
        super().__init__()
        self.folder_path = folder_path; self.thumbnail_dir = thumbnail_dir; self.is_running = True
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
                        thumb_name = hashlib.md5(full_path.encode()).hexdigest() + ".jpg"
                        thumb_path = os.path.join(self.thumbnail_dir, thumb_name).replace('\\', '/')
                        if not os.path.exists(thumb_path): _create_thumbnail_file(full_path, thumb_path)
                        
                        duration_str = "0:00:00"
                        try:
                            cap = cv2.VideoCapture(full_path)
                            if cap.isOpened():
                                fps = cap.get(cv2.CAP_PROP_FPS)
                                frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                                sec = frames / fps if fps > 0 else 0
                                duration_str = str(timedelta(seconds=int(sec)))
                                cap.release()
                        except: pass


                        found_videos.append({
                            "path": full_path, "filename": os.path.splitext(file)[0],
                            "extension": os.path.splitext(file)[1], "duration": duration_str,
                            "tags": "", "thumbnail_path": thumb_path
                        })
                    except Exception: pass
        self.finished.emit(found_videos)
    def stop(self): self.is_running = False


# --- Dialogs (로직 동일) ---
class AddTimelineDialog(QDialog):
    def __init__(self, max_duration_secs=86399, parent=None):
        super().__init__(parent)
        self.setWindowTitle("타임라인 추가")
        self.setStyleSheet("""
            QDialog { background-color: #272727; color: white; }
            QLabel { color: white; }
            QLineEdit, QTimeEdit { background-color: #121212; border: 1px solid #555; padding: 5px; color: white; }
            QPushButton { background-color: #3f3f3f; color: white; border-radius: 5px; padding: 5px; }
            QPushButton:hover { background-color: #505050; }
        """)
        layout = QVBoxLayout(self)
        
        self.time_edit = QTimeEdit(self)
        self.time_edit.setDisplayFormat("HH:mm:ss")
        max_time = QTime.fromMSecsSinceStartOfDay(max_duration_secs * 1000)
        self.time_edit.setMaximumTime(max_time)
        layout.addWidget(QLabel("시간 (HH:mm:ss):"))
        layout.addWidget(self.time_edit)


        self.description_edit = QLineEdit(self)
        layout.addWidget(QLabel("설명:"))
        layout.addWidget(self.description_edit)


        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.button_box.accepted.connect(self.accept); self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)


    def get_data(self):
        t = self.time_edit.time()
        return {"time": t.hour()*3600 + t.minute()*60 + t.second(), "description": self.description_edit.text()}


# --- Timeline Entry Widget (로직 동일) ---
class TimelineEntryWidget(QWidget):
    clicked = pyqtSignal(int)
    def __init__(self, timeline_data, parent=None):
        super().__init__(parent)
        self.timeline_data = timeline_data
        self.setCursor(Qt.PointingHandCursor)
        self.set_highlight(False)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        time_str = str(timedelta(seconds=timeline_data.get("time", 0)))
        self.time_label = QLabel(time_str)
        self.time_label.setStyleSheet("color: #3ea6ff; font-weight: bold; background: #272727; padding: 3px; border-radius: 4px;")
        layout.addWidget(self.time_label)


        self.desc_label = QLabel(timeline_data.get("text", ""))
        self.desc_label.setStyleSheet("color: #f1f1f1; background: transparent;")
        layout.addWidget(self.desc_label, 1)


    def mousePressEvent(self, event):
        self.clicked.emit(self.timeline_data.get("time", 0))
        super().mousePressEvent(event)


    def set_highlight(self, highlighted):
        if highlighted: self.setStyleSheet("background-color: #3f3f3f; border-radius: 5px;")
        else: self.setStyleSheet("background-color: transparent;")


# --- Main Application ---
class VideoManagerApp(QMainWindow):
    @staticmethod
    def ms_to_time_string(ms):
        s = int(ms / 1000); m = int(s / 60); h = int(m / 60)
        if h > 0: return f"{h:02d}:{m%60:02d}:{s%60:02d}"
        return f"{m:02d}:{s%60:02d}"


    def __init__(self):
        super().__init__()
        self.setWindowTitle('Smart Video Manager (Dark Mode)')
        self.video_data = []; self.current_view_videos = []
        self.json_path = "videos.json"; self.thumbnail_dir = ".thumbnails"
        os.makedirs(self.thumbnail_dir, exist_ok=True)
        self.current_selected_path = None
        self.scan_thread = None; self.scan_worker = None
        self.timeline_widgets = []
        
        # QMediaPlayer 초기화
        self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        
        self.setup_dark_theme()
        self.init_ui()
        
        # QVideoWidget과 QMediaPlayer 연결
        self.media_player.setVideoOutput(self.video_container.video_widget)
        
        self.connect_signals()
        self.load_data()
        self.update_volume_icon()


    def setup_dark_theme(self):
        # 스타일시트 범위 제한 (QVideoWidget 간섭 방지)
        self.setStyleSheet("""
            QMainWindow { background-color: #0f0f0f; color: #f1f1f1; font-family: 'Segoe UI', sans-serif; }
            QDialog { background-color: #0f0f0f; color: #f1f1f1; }
            
            QLabel { color: #f1f1f1; }
            QLineEdit { 
                background-color: #121212; border: 1px solid #303030; 
                border-radius: 18px; padding: 5px 15px; color: white; selection-background-color: #3ea6ff;
            }
            QLineEdit:focus { border: 1px solid #3ea6ff; }
            
            QPushButton { 
                background-color: #272727; border: none; border-radius: 18px; 
                padding: 8px 16px; font-weight: bold; color: #f1f1f1;
            }
            QPushButton:hover { background-color: #3f3f3f; }
            
            QComboBox {
                background-color: #272727; border: none; border-radius: 15px; padding: 5px 10px; color: #f1f1f1;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #272727; color: #f1f1f1; selection-background-color: #3f3f3f;
            }


            QTableWidget {
                background-color: #0f0f0f; gridline-color: transparent; border: none;
            }
            QTableWidget::item { padding: 5px; border-bottom: 1px solid #272727; color: #f1f1f1; }
            QTableWidget::item:selected { background-color: #272727; color: white; }
            
            QHeaderView::section { background-color: #0f0f0f; color: #aaaaaa; border: none; font-weight: bold; padding: 5px; }
            
            QScrollBar:vertical { background: #0f0f0f; width: 10px; }
            QScrollBar::handle:vertical { background: #505050; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #707070; }
        """)


    def init_ui(self):
        self.central_widget = QWidget()
        self.central_widget.setObjectName("centralWidget")
        self.central_widget.setStyleSheet("#centralWidget { background-color: #0f0f0f; }")
        self.setCentralWidget(self.central_widget)
        
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)


        # --- Top Bar ---
        top_bar = QWidget()
        top_bar.setFixedHeight(60)
        top_bar.setStyleSheet("background-color: #0f0f0f;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(20, 10, 20, 10)
        
        logo_label = QLabel("▶ Studio")
        logo_label.setStyleSheet("font-size: 20px; font-weight: bold; color: white; letter-spacing: -1px; background: transparent;")
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("검색")
        self.search_input.setFixedWidth(400)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["전체", "파일명", "태그"])
        self.filter_combo.setFixedWidth(100)


        self.select_folder_btn = QPushButton("폴더 열기")
        self.select_folder_btn.setStyleSheet("background-color: #272727; color: #3ea6ff;")


        top_bar_layout.addWidget(logo_label)
        top_bar_layout.addStretch(1)
        top_bar_layout.addWidget(self.filter_combo)
        top_bar_layout.addWidget(self.search_input)
        top_bar_layout.addStretch(1)
        top_bar_layout.addWidget(self.select_folder_btn)


        main_layout.addWidget(top_bar)


        # --- Body Area ---
        body_widget = QWidget()
        body_widget.setStyleSheet("background-color: #0f0f0f;")
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(20, 0, 20, 20)
        body_layout.setSpacing(20)


        # [LEFT COLUMN]
        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setAlignment(Qt.AlignTop)


        self.video_container = VideoContainer(self.media_player)
        left_layout.addWidget(self.video_container)


        self.selected_filename_label = QLabel("재생할 영상을 선택해주세요")
        self.selected_filename_label.setStyleSheet("font-size: 20px; font-weight: bold; margin-top: 10px; color: white; background: transparent;")
        self.selected_filename_label.setWordWrap(True)
        left_layout.addWidget(self.selected_filename_label)


        self.selected_tags_label = QLabel("#태그없음")
        self.selected_tags_label.setStyleSheet("color: #3ea6ff; font-size: 12px; margin-bottom: 10px; background: transparent;")
        left_layout.addWidget(self.selected_tags_label)


        actions_layout = QHBoxLayout()
        self.play_button_main = QPushButton(" 재생")
        self.play_button_main.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_button_main.setStyleSheet("background-color: white; color: black; border-radius: 18px;")
        
        self.add_timeline_btn = QPushButton(" 타임라인 추가")
        self.add_timeline_btn.setStyleSheet("background-color: #272727; color: white; border-radius: 18px;")
        
        actions_layout.addWidget(self.play_button_main)
        actions_layout.addWidget(self.add_timeline_btn)
        actions_layout.addStretch(1)
        left_layout.addLayout(actions_layout)


        # Timeline
        timeline_container = QFrame()
        timeline_container.setStyleSheet("background-color: #272727; border-radius: 10px; margin-top: 15px;")
        timeline_layout = QVBoxLayout(timeline_container)
        
        timeline_header = QLabel("타임라인 (챕터)")
        timeline_header.setStyleSheet("font-weight: bold; color: white; margin-bottom: 5px; background: transparent;")
        timeline_layout.addWidget(timeline_header)


        timeline_scroll = QScrollArea()
        timeline_scroll.setWidgetResizable(True)
        timeline_scroll.setStyleSheet("background: transparent; border: none;")
        timeline_scroll_content = QWidget()
        timeline_scroll_content.setStyleSheet("background: transparent;")
        self.timeline_list_layout = QVBoxLayout(timeline_scroll_content)
        self.timeline_list_layout.setAlignment(Qt.AlignTop)
        
        self.no_timeline_label = QLabel("저장된 타임라인이 없습니다.")
        self.no_timeline_label.setStyleSheet("color: #aaaaaa; background: transparent;")
        self.timeline_list_layout.addWidget(self.no_timeline_label)
        
        timeline_scroll.setWidget(timeline_scroll_content)
        timeline_layout.addWidget(timeline_scroll)
        
        left_layout.addWidget(timeline_container)
        left_layout.setStretchFactor(timeline_container, 1)


        # [RIGHT COLUMN]
        right_column = QWidget()
        right_column.setFixedWidth(400)
        right_column.setStyleSheet("background-color: #0f0f0f;")
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)


        list_header = QLabel("다음 동영상")
        list_header.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px; background: transparent; color: white;")
        right_layout.addWidget(list_header)


        self.file_list = QTableWidget()
        self.file_list.setColumnCount(5)
        self.file_list.setHorizontalHeaderLabels(["", "영상 정보", "", "", ""]) 
        header = self.file_list.horizontalHeader()
        header.hide()
        self.file_list.setColumnWidth(0, 120)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.file_list.setColumnHidden(2, True)
        self.file_list.setColumnHidden(3, True)
        self.file_list.setColumnHidden(4, True)
        
        self.file_list.verticalHeader().hide()
        self.file_list.verticalHeader().setDefaultSectionSize(80)
        self.file_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.file_list.setShowGrid(False)


        right_layout.addWidget(self.file_list)


        body_layout.addWidget(left_column, stretch=7)
        body_layout.addWidget(right_column, stretch=3)


        main_layout.addWidget(body_widget)


        self.status_bar = self.statusBar()
        self.status_bar.setStyleSheet("background-color: #0f0f0f; color: #707070;")
        self.status_bar.showMessage("Ready")
        self.resize(1280, 800)


    # --- Logic Connections ---
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


    # [추가] 스페이스바로 재생/정지 토글
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.toggle_play_pause()
            event.accept()
        else:
            super().keyPressEvent(event)


    # --- Scan Logic ---
    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Open Video Folder", self.current_selected_path or os.path.expanduser("~"))
        if not folder_path: return
        self._stop_all_threads(); self.clear_info_panel(); self.file_list.setRowCount(0)
        self.status_bar.showMessage(f"Scanning: {folder_path}...")
        self.scan_thread = QThread(self); self.scan_worker = Worker(folder_path, self.thumbnail_dir)
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.progress.connect(lambda msg: self.status_bar.showMessage(msg))
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_thread.start()


    def on_scan_finished(self, found_videos):
        self.status_bar.showMessage(f"Found {len(found_videos)} videos.")
        existing_map = {v['path']: v for v in self.video_data}
        new_cnt = 0
        for i, v in enumerate(found_videos):
            if v['path'] in existing_map:
                old = existing_map[v['path']]
                found_videos[i]['tags'] = old.get('tags', ''); found_videos[i]['timelines'] = old.get('timelines', [])
            else:
                self.video_data.append(v); new_cnt += 1
        self.current_view_videos = found_videos
        self.populate_file_list(self.current_view_videos)
        if new_cnt > 0: self.save_data()
        self._stop_all_threads(stop_batch=False)


    def populate_file_list(self, data=None):
        self.file_list.setRowCount(0)
        videos = data if data is not None else self.video_data
        self.file_list.setRowCount(len(videos))
        for i, video in enumerate(videos):
            thumb_path = video.get("thumbnail_path")
            thumb_label = QLabel()
            if thumb_path and os.path.exists(thumb_path):
                pix = QPixmap(thumb_path)
                if not pix.isNull():
                    thumb_label.setPixmap(pix.scaled(120, 68, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            thumb_label.setAlignment(Qt.AlignCenter)
            thumb_label.setStyleSheet("background-color: black; border: none;")
            self.file_list.setCellWidget(i, 0, thumb_label)
            
            title = video.get("filename", "")
            duration = video.get("duration", "0:00:00")
            info_text = f"{title}\nLength: {duration}"
            self.file_list.setItem(i, 1, QTableWidgetItem(info_text))
            
            self.file_list.setItem(i, 2, QTableWidgetItem(duration))
            self.file_list.setItem(i, 3, QTableWidgetItem(video.get("tags", "")))
            self.file_list.setItem(i, 4, QTableWidgetItem(video.get("path", "")))


    # --- Playback Logic ---
    def update_info_panel(self):
        self.media_player.stop()
        controls = self.video_container
        controls.seek_slider.setValue(0); controls.current_time_label.setText("00:00")
        
        rows = self.file_list.selectionModel().selectedRows()
        if not rows: self.clear_info_panel(); return
        
        path_item = self.file_list.item(rows[0].row(), 4)
        if not path_item: self.clear_info_panel(); return
        
        path = path_item.text()
        self.current_selected_path = path
        video = next((v for v in self.video_data if v["path"] == path), None)
        
        for i in reversed(range(self.timeline_list_layout.count())):
            w = self.timeline_list_layout.itemAt(i).widget()
            if w and w != self.no_timeline_label: w.deleteLater()
        self.no_timeline_label.hide()


        if video:
            self.selected_filename_label.setText(video.get("filename", "-"))
            tags = video.get("tags", "")
            self.selected_tags_label.setText(tags if tags else "#태그없음")
            
            thumb_path = video.get("thumbnail_path")
            self.video_container.set_thumbnail(QPixmap(thumb_path) if thumb_path and os.path.exists(thumb_path) else QPixmap())
            self.video_container.big_play_btn.show()


            timelines = video.get("timelines", [])
            self.timeline_widgets.clear()
            if timelines:
                self.no_timeline_label.hide()
                for t in timelines:
                    w = TimelineEntryWidget(t)
                    w.clicked.connect(lambda ts: self.media_player.setPosition(ts * 1000))
                    self.timeline_list_layout.addWidget(w)
                    self.timeline_widgets.append(w)
            else:
                self.no_timeline_label.show()
        else:
            self.clear_info_panel()


    def clear_info_panel(self):
        self.media_player.stop()
        self.selected_filename_label.setText("재생할 영상을 선택해주세요")
        self.selected_tags_label.setText("")
        self.video_container.set_thumbnail(QPixmap())
        self.video_container.big_play_btn.hide()
        self.current_selected_path = None
        self.no_timeline_label.show()


    def play_video(self):
        if self.current_selected_path:
            if self.media_player.state() == QMediaPlayer.PausedState:
                self.media_player.play()
            elif self.media_player.state() == QMediaPlayer.StoppedState:
                self.video_container.show_video_surface()
                self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(self.current_selected_path)))
                self.media_player.setVolume(self.video_container.volume_slider.value())
                self.media_player.play()


    def toggle_play_pause(self):
        if self.media_player.state() == QMediaPlayer.PlayingState: self.media_player.pause()
        else: self.media_player.play()


    def toggle_mute(self): self.media_player.setMuted(not self.media_player.isMuted())
    def update_volume_icon(self):
        icon = QStyle.SP_MediaVolumeMuted if (self.media_player.isMuted() or self.media_player.volume()==0) else QStyle.SP_MediaVolume
        self.video_container.volume_label.setPixmap(self.style().standardIcon(icon).pixmap(16, 16))


    def media_state_changed(self, state):
        c = self.video_container
        if state == QMediaPlayer.PlayingState:
            c.play_pause_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            c.big_play_btn.hide()
        else:
            c.play_pause_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            if state == QMediaPlayer.StoppedState and self.current_selected_path:
                c.big_play_btn.show()


    def update_timeline_highlight(self, ms):
        if not self.timeline_widgets: return
        sec = ms / 1000
        cur = None
        for w in self.timeline_widgets:
            if w.timeline_data['time'] <= sec: cur = w
            else: break
        for w in self.timeline_widgets: w.set_highlight(w == cur)


    def position_changed(self, p):
        self.video_container.seek_slider.blockSignals(True)
        self.video_container.seek_slider.setValue(p)
        self.video_container.seek_slider.blockSignals(False)
        self.video_container.current_time_label.setText(self.ms_to_time_string(p))


    def duration_changed(self, d):
        self.video_container.seek_slider.setRange(0, d)
        self.video_container.total_time_label.setText(self.ms_to_time_string(d))


    def set_position(self, p):
        if self.media_player.position() != p: self.media_player.setPosition(p)


    def on_cell_double_clicked(self, row, col):
        path_item = self.file_list.item(row, 4)
        if not path_item: return
        video = next((v for v in self.video_data if v["path"] == path_item.text()), None)
        if not video: return
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #272727; color: white; border: 1px solid #505050; } QMenu::item:selected { background-color: #3f3f3f; }")
        rename_action = menu.addAction("이름 변경")
        tag_action = menu.addAction("태그 수정")
        copy_action = menu.addAction("경로 복사")
        
        action = menu.exec_(self.file_list.mapToGlobal(self.file_list.visualItemRect(self.file_list.item(row, 1)).center()))
        
        if action == rename_action: self.rename_video_file(video)
        elif action == tag_action: self.edit_tags_for_video(video)
        elif action == copy_action: self.show_path_for_copy(path_item.text())


    def rename_video_file(self, video):
        cur = video["filename"]
        text, ok = QInputDialog.getText(self, "이름 변경", "새 파일명:", text=cur)
        if ok and text and text != cur:
            old_path = video["path"]; folder = os.path.dirname(old_path); ext = video["extension"]
            new_path = os.path.join(folder, text + ext).replace('\\', '/')
            if os.path.exists(new_path): QMessageBox.warning(self, "오류", "이미 존재하는 파일명입니다."); return
            try:
                os.rename(old_path, new_path)
                video["path"] = new_path; video["filename"] = text
                self.save_data(); self.populate_file_list(self.current_view_videos); self.update_info_panel()
            except Exception as e: QMessageBox.critical(self, "오류", str(e))


    def edit_tags_for_video(self, video):
        cur = video.get("tags", "")
        text, ok = QInputDialog.getText(self, "태그 수정", "태그 (콤마 구분):", text=cur)
        if ok:
            video["tags"] = text.strip(); self.save_data()
            self.populate_file_list(self.current_view_videos); self.update_info_panel()
            
    def show_path_for_copy(self, path):
        QMessageBox.information(self, "전체 경로", path)


    def filter_list(self):
        term = self.search_input.text().lower(); kind = self.filter_combo.currentText()
        src = self.current_view_videos if self.current_view_videos else self.video_data
        if not term: self.populate_file_list(src); return
        filtered = []
        for v in src:
            fname = v.get("filename", "").lower(); tags = v.get("tags", "").lower()
            if kind == "전체" and (term in fname or term in tags): filtered.append(v)
            elif kind == "파일명" and term in fname: filtered.append(v)
            elif kind == "태그" and term in tags: filtered.append(v)
        self.populate_file_list(filtered)


    def load_data(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    self.video_data = json.load(f)
                    self.current_view_videos = self.video_data
                    self.populate_file_list(self.video_data)
            except: self.video_data = []


    def save_data(self):
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.video_data, f, indent=4, ensure_ascii=False)
        except: pass


    def _stop_all_threads(self, stop_batch=True):
        if self.scan_worker: self.scan_worker.stop()
        if self.scan_thread and self.scan_thread.isRunning(): self.scan_thread.quit(); self.scan_thread.wait()


    def open_add_timeline_dialog(self):
        if not self.current_selected_path: return
        video = next((v for v in self.video_data if v["path"] == self.current_selected_path), None)
        if not video: return
        
        dur = 0
        try: 
            parts = list(map(int, video.get("duration", "0:00:00").split(':')))
            if len(parts)==3: dur = parts[0]*3600+parts[1]*60+parts[2]
            else: dur = parts[0]*60+parts[1]
        except: pass
            
        dlg = AddTimelineDialog(dur, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            t_hash = hashlib.md5(f"{video['path']}_{data['time']}".encode()).hexdigest()
            t_path = os.path.join(self.thumbnail_dir, f"tl_{t_hash}.jpg").replace('\\', '/')
            _create_thumbnail_for_timestamp(video['path'], t_path, data['time'])
            
            if "timelines" not in video: video["timelines"] = []
            video["timelines"].append({"time": data["time"], "text": data["description"], "thumb_path": t_path})
            video["timelines"].sort(key=lambda x: x["time"])
            self.save_data(); self.update_info_panel()


    def closeEvent(self, event):
        self.media_player.stop(); self._stop_all_threads(); event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = VideoManagerApp()
    ex.show()
    sys.exit(app.exec_())