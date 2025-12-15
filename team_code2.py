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
    from PyQt5.QtGui import QFont, QIcon, QPixmap, QImage
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout,
        QHBoxLayout, QPushButton, QLabel, QLineEdit,
        QTableWidget, QTableWidgetItem, QHeaderView,
        QAbstractItemView, QMenu, QInputDialog, QMessageBox,
        QComboBox, QFileDialog, QDialog, QSlider, QStyle, QStackedLayout,
    )
    from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QObject, QThread, QTimer, QPoint, QSize
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    from PyQt5.QtMultimediaWidgets import QVideoWidget

    from PIL import Image
except ImportError as e:
    print(f"필수 라이브러리가 설치되지 않았습니다: {e}")
    print("pip install PyQt5 Pillow opencv-python PyQt5-sip")
    sys.exit(1)

import cv2
import subprocess

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

# --- Video Player Widget with Overlay Controls ---
class VideoContainer(QWidget):
    def __init__(self, media_player, parent=None):
        super().__init__(parent)
        self.media_player = media_player
        self.setFixedSize(640, 360)
        self.setStyleSheet("background-color: black;")
        self.setMouseTracking(True)

        # 1. Main Display Area (Video or Thumbnail)
        self.display_stack = QStackedLayout(self)
        self.display_stack.setStackingMode(QStackedLayout.StackAll)
        
        self.video_widget = QVideoWidget(self)
        self.thumbnail_label = QLabel(self)
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
        self.controls_widget.setStyleSheet("background-color: rgba(0,0,0,90); border-radius: 10px;")
        self.controls_widget.setMouseTracking(True)
        controls_layout = QHBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(5, 5, 5, 5)

        self.play_pause_btn = QPushButton()
        self.play_pause_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        
        self.volume_label = QLabel()
        self.volume_label.setPixmap(self.style().standardIcon(QStyle.SP_MediaVolume).pixmap(16,16))

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100); self.volume_slider.setValue(80); self.volume_slider.setFixedWidth(100)

        controls_layout.addWidget(self.play_pause_btn)
        controls_layout.addWidget(self.seek_slider)
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
        self.big_play_btn.move(self.rect().center() - self.big_play_btn.rect().center())
        self.controls_widget.setGeometry(10, self.height() - 50, self.width() - 20, 40)

    def enterEvent(self, event):
        if self.media_player.state() == QMediaPlayer.PlayingState:
            self.controls_widget.show()
            self.hide_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hide_timer.stop()
        self.controls_widget.hide()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        if self.media_player.state() == QMediaPlayer.PlayingState:
            self.controls_widget.show()
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

# --- Main Application Window ---
class VideoManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('똑똑한 영상 관리자 (Smart Video Manager)')
        self.video_data = []
        self.json_path = "videos.json"
        self.thumbnail_dir = ".thumbnails"
        os.makedirs(self.thumbnail_dir, exist_ok=True)
        
        self.current_selected_path = None
        self.scan_thread, self.scan_worker = None, None
        self.thumbnail_gen_thread, self.thumbnail_gen_worker = None, None
        self.batch_thumb_thread, self.batch_thumb_worker = None, None
        
        self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        
        self.init_ui()
        self.connect_signals()
        self.load_data()

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
        self.resize(1200, 800)

    def connect_signals(self):
        self.select_folder_btn.clicked.connect(self.select_folder)
        self.search_input.textChanged.connect(self.filter_list)
        self.file_list.itemSelectionChanged.connect(self.update_info_panel)
        self.file_list.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.play_button_main.clicked.connect(self.play_video)
        
        self.media_player.stateChanged.connect(self.media_state_changed)
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)
        
        controls = self.video_container
        controls.play_pause_btn.clicked.connect(self.toggle_play_pause)
        controls.big_play_btn.clicked.connect(self.play_video)
        controls.seek_slider.sliderMoved.connect(self.set_position)
        controls.volume_slider.valueChanged.connect(self.media_player.setVolume)

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
        
        # O(N) lookup for existing paths
        existing_paths = {v['path'] for v in self.video_data}
        
        new_videos_added = 0
        for video in found_videos:
            if video['path'] not in existing_paths:
                self.video_data.append(video)
                new_videos_added += 1

        self.populate_file_list()
        self.save_data()
        self.status_bar.showMessage(f"스캔 완료. {new_videos_added}개의 새로운 비디오 추가.", 5000)
        self._stop_all_threads(stop_batch=False) # Keep batch thumbnail generator running if it was

    def update_info_panel(self):
        self.media_player.stop()
        selected_rows = self.file_list.selectionModel().selectedRows()
        if not selected_rows: self.clear_info_panel(); return

        path_item = self.file_list.item(selected_rows[0].row(), 4)
        if not path_item: self.clear_info_panel(); return
        
        path = path_item.text()
        self.current_selected_path = path
        video = next((v for v in self.video_data if v["path"] == path), None)

        if video:
            self.selected_filename_label.setText(video.get("filename", "-"))
            self.selected_tags_label.setText(video.get("tags", "-"))
            thumb_path = video.get("thumbnail_path")
            self.video_container.set_thumbnail(QPixmap(thumb_path) if thumb_path and os.path.exists(thumb_path) else QPixmap())
            self.video_container.big_play_btn.show()
        else:
            self.clear_info_panel()

    def clear_info_panel(self):
        self.media_player.stop()
        self.selected_filename_label.setText("-")
        self.selected_tags_label.setText("-")
        self.video_container.set_thumbnail(QPixmap())
        self.video_container.big_play_btn.hide()
        self.current_selected_path = None

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

    def position_changed(self, position): self.video_container.seek_slider.setValue(position)
    def duration_changed(self, duration): self.video_container.seek_slider.setRange(0, duration)
    def set_position(self, position): self.media_player.setPosition(position)
    
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
        if not search_term: self.populate_file_list(); return
        
        filtered_videos = [
            v for v in self.video_data 
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
            self.populate_file_list()
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
xec_())