import sys
import os
import json
import threading
from datetime import timedelta
import hashlib

# PyQt5 and Pillow
try:
    import PyQt5

    # Try to locate Qt platform plugins and set QT_QPA_PLATFORM_PLUGIN_PATH
    def _ensure_qt_platform_plugin_path():
        try:
            qt_root = os.path.dirname(PyQt5.__file__)
        except Exception:
            return

        candidates = [
            os.path.join(qt_root, 'Qt', 'plugins'),
            os.path.join(qt_root, 'Qt5', 'plugins'),
            os.path.join(qt_root, 'plugins'),
            os.path.join(qt_root, 'Qt', 'lib', 'plugins'),
        ]

        for c in candidates:
            platforms_dir = os.path.join(c, 'platforms')
            if os.path.isdir(platforms_dir):
                os.environ.setdefault('QT_QPA_PLATFORM_PLUGIN_PATH', platforms_dir)
                return

            # some installations have plugin files directly under c
            if os.path.isdir(c):
                try:
                    names = os.listdir(c)
                except Exception:
                    names = []
                for name in names:
                    if name.startswith('qwindows') or name.startswith('libqwindows'):
                        os.environ.setdefault('QT_QPA_PLATFORM_PLUGIN_PATH', c)
                        return

    _ensure_qt_platform_plugin_path()

    from PyQt5.QtGui import QFont, QIcon, QPixmap
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout,
        QHBoxLayout, QPushButton, QLabel, QLineEdit,
        QTableWidget, QTableWidgetItem, QHeaderView,
        QAbstractItemView, QMenu, QInputDialog, QMessageBox,
        QComboBox, QFileDialog, QDialog,
    )
    from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QObject, QThread
    from PIL import Image
except ImportError as e:
    print(f"필수 라이브러리가 설치되지 않았습니다: {e}")
    print("pip install PyQt5 Pillow opencv-python")
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



# --- Custom Scalable QLabel for Thumbnails ---
class ScalablePixmapLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pixmap = QPixmap()
        self.setMinimumSize(1, 1)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")

    def setPixmap(self, pixmap):
        if pixmap and not pixmap.isNull():
            self._pixmap = pixmap
            self._update_pixmap()
        else:
            self._pixmap = QPixmap()
            super().setPixmap(QPixmap())
            self.setText("썸네일 없음")

    def resizeEvent(self, event):
        self._update_pixmap()
        super().resizeEvent(event)

    def _update_pixmap(self):
        if not self._pixmap.isNull():
            scaled_pixmap = self._pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            super().setPixmap(scaled_pixmap)

# --- Worker for threaded video scanning ---
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
                        cap = cv2.VideoCapture(full_path)
                        if cap.isOpened():
                            fps = cap.get(cv2.CAP_PROP_FPS)
                            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                            duration_sec = frame_count / fps if fps > 0 else 0
                            duration_str = str(timedelta(seconds=int(duration_sec)))
                            cap.release()

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

# --- Worker for On-Demand Thumbnail Generation ---
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

# --- Worker for Batch Thumbnail Generation ---
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


class VideoManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('똑똑한 영상 관리자 (Smart Video Manager)')
        self.video_data = []
        self.json_path = "videos.json"
        self.thumbnail_dir = ".thumbnails"
        os.makedirs(self.thumbnail_dir, exist_ok=True)
        
        self.current_selected_path = None
        self.scan_thread = None
        self.scan_worker = None
        self.thumbnail_gen_thread = None
        self.thumbnail_gen_worker = None
        self.batch_thumb_thread = None
        self.batch_thumb_worker = None

        self.init_ui()
        self.load_data()

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)

        top_controls_layout = QHBoxLayout()
        self.select_folder_btn = QPushButton("폴더 선택")
        self.select_folder_btn.clicked.connect(self.select_folder)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Filename", "Tag"])
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("검색어를 입력하세요...")
        self.search_input.textChanged.connect(self.filter_list)
        top_controls_layout.addWidget(self.select_folder_btn)
        top_controls_layout.addWidget(self.filter_combo)
        top_controls_layout.addWidget(self.search_input)
        main_layout.addLayout(top_controls_layout)

        middle_layout = QHBoxLayout()
        self.thumbnail_placeholder = ScalablePixmapLabel("썸네일이 여기에 표시됩니다.")
        self.thumbnail_placeholder.setFixedSize(640, 360)
        
        info_layout = QVBoxLayout()
        self.selected_filename_label = QLabel("-")
        self.selected_tags_label = QLabel("-")
        play_button = QPushButton("선택한 영상 재생")
        play_button.clicked.connect(self.play_selected_video)
        
        info_layout.addWidget(QLabel("파일명:"))
        info_layout.addWidget(self.selected_filename_label)
        info_layout.addSpacing(20)
        info_layout.addWidget(QLabel("태그:"))
        info_layout.addWidget(self.selected_tags_label)
        info_layout.addStretch(1)
        info_layout.addWidget(play_button)
        
        middle_layout.addWidget(self.thumbnail_placeholder)
        middle_layout.addLayout(info_layout)
        main_layout.addLayout(middle_layout)

        self.file_list = QTableWidget()
        self.file_list.setColumnCount(5)
        self.file_list.setHorizontalHeaderLabels(["썸네일", "파일명", "길이", "태그", "경로"])
        
        header = self.file_list.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.file_list.setColumnWidth(1, 200)
        self.file_list.setColumnWidth(3, 150)

        self.file_list.verticalHeader().setDefaultSectionSize(70)
        self.file_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.file_list.itemSelectionChanged.connect(self.update_info_panel)
        self.file_list.cellDoubleClicked.connect(self.on_cell_double_clicked)
        main_layout.addWidget(self.file_list)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage("준비 완료.")
        self.resize(1200, 800)

    def on_cell_double_clicked(self, row, column):
        path_item = self.file_list.item(row, 4)
        if not path_item: return
        path = path_item.text()
        video = next((v for v in self.video_data if v["path"] == path), None)
        if not video: return

        if column == 1: self.rename_video_file(video)
        elif column == 3: self.edit_tags_for_video(video)
        elif column == 4: self.show_path_for_copy(path)

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
                self.populate_file_list()
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
            video["tags"] = new_tags
            self.save_data()
            self.populate_file_list()
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

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if not folder_path: return

        self.status_bar.showMessage("영상 스캔 중...")
        self.file_list.setRowCount(0)
        self.clear_info_panel()
        self.select_folder_btn.setEnabled(False)

        self.scan_thread = QThread()
        self.scan_worker = Worker(folder_path, self.thumbnail_dir)
        self.scan_worker.moveToThread(self.scan_thread)

        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.finished.connect(self.scan_worker.deleteLater)
        self.scan_worker.progress.connect(lambda s: self.status_bar.showMessage(s))

        self.scan_thread.start()

    def on_scan_finished(self, found_videos):
        self.video_data = found_videos
        # Preserve tags from old data
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                # Merge tags from old data
                old_dict = {v.get('path'): v.get('tags', '') for v in old_data}
                for video in self.video_data:
                    if video['path'] in old_dict:
                        video['tags'] = old_dict[video['path']]
            except Exception as e:
                print(f"Error loading old tags: {e}")
        
        # Save the new video data
        self.save_data()
        self.populate_file_list()
        self.start_batch_thumbnail_generation()
        self.status_bar.showMessage(f"스캔 완료. {len(self.video_data)}개의 영상을 찾았습니다.")
        self.select_folder_btn.setEnabled(True)
        self.scan_thread = None

    def load_data(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    self.video_data = json.load(f)
                
                if not isinstance(self.video_data, list):
                    self.video_data = []
                    raise TypeError("JSON is not a list")
                
                # Ensure all videos have thumbnail_path
                data_updated = False
                for video in self.video_data:
                    if "thumbnail_path" not in video or not video.get("thumbnail_path"):
                        video_path = video.get("path")
                        if video_path:
                            thumb_hash = hashlib.md5(video_path.encode()).hexdigest() + ".jpg"
                            video["thumbnail_path"] = os.path.join(self.thumbnail_dir, thumb_hash).replace('\\', '/')
                            data_updated = True
                if data_updated:
                    self.save_data()

                self.populate_file_list()
                self.start_batch_thumbnail_generation()
                self.status_bar.showMessage(f"{len(self.video_data)}개의 영상 정보를 불러왔습니다.")
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                print(f"Error loading {self.json_path}: {e}")
                self.status_bar.showMessage(f"오류: {self.json_path} 파일을 읽을 수 없습니다.")
                self.video_data = []
        else:
            # JSON 파일이 없으면 빈 상태로 시작
            self.video_data = []
            self.status_bar.showMessage("준비 완료. 폴더를 선택하여 영상을 스캔하세요.")

    def save_data(self):
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.video_data, f, indent=4, ensure_ascii=False)
            print(f"Data saved to {self.json_path}")
        except Exception as e:
            print(f"Error saving data to {self.json_path}: {e}")
            self.status_bar.showMessage(f"오류: 데이터를 저장할 수 없습니다. {e}")

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

    def start_batch_thumbnail_generation(self):
        # Stop only batch and thumbnail threads, keep scan thread
        self._stop_all_threads(stop_scan=False, stop_batch=True, stop_thumbnail=False)
        
        # Ensure previous threads are fully cleaned up
        if self.batch_thumb_thread is None:
            self.batch_thumb_thread = QThread()
            self.batch_thumb_worker = BatchThumbnailGenerator(self.video_data)
            self.batch_thumb_worker.moveToThread(self.batch_thumb_thread)
            self.batch_thumb_thread.started.connect(self.batch_thumb_worker.run)
            self.batch_thumb_worker.thumbnail_ready.connect(self.on_batch_thumbnail_ready)
            self.batch_thumb_worker.finished.connect(self.batch_thumb_thread.quit)
            self.batch_thumb_worker.finished.connect(self.batch_thumb_worker.deleteLater)
            self.batch_thumb_thread.start()

    def on_batch_thumbnail_ready(self, row_index, thumb_path):
        if os.path.exists(thumb_path):
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull() and row_index < self.file_list.rowCount():
                thumb_label = QLabel()
                thumb_label.setPixmap(pixmap.scaled(96, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                thumb_label.setAlignment(Qt.AlignCenter)
                self.file_list.setCellWidget(row_index, 0, thumb_label)

    def on_thumbnail_generated(self, generated_thumb_path):
        if generated_thumb_path:
            pixmap = QPixmap(generated_thumb_path)
            self.thumbnail_placeholder.setPixmap(pixmap)
            self.on_batch_thumbnail_ready(self.file_list.currentRow(), generated_thumb_path)
        else:
            self.thumbnail_placeholder.setText("썸네일 생성 실패")

    def on_thumbnail_thread_finished(self):
        self.thumbnail_gen_thread = None
        self.thumbnail_gen_worker = None

    def update_info_panel(self):
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

            if thumb_path and os.path.exists(thumb_path):
                self.thumbnail_placeholder.setPixmap(QPixmap(thumb_path))
            elif thumb_path and video.get("path"):
                self.thumbnail_placeholder.setText("썸네일 생성 중...")
                self.thumbnail_placeholder.setPixmap(QPixmap())
                
                self.thumbnail_gen_thread = QThread()
                self.thumbnail_gen_worker = ThumbnailGenerator(video["path"], thumb_path)
                self.thumbnail_gen_worker.moveToThread(self.thumbnail_gen_thread)
                self.thumbnail_gen_thread.started.connect(self.thumbnail_gen_worker.run)
                self.thumbnail_gen_worker.finished.connect(self.on_thumbnail_generated)
                self.thumbnail_gen_worker.finished.connect(self.thumbnail_gen_thread.quit)
                self.thumbnail_gen_worker.finished.connect(self.thumbnail_gen_worker.deleteLater)
                self.thumbnail_gen_thread.finished.connect(self.on_thumbnail_thread_finished)
                self.thumbnail_gen_thread.finished.connect(self.thumbnail_gen_thread.deleteLater)
                self.thumbnail_gen_thread.start()
            else:
                self.thumbnail_placeholder.setPixmap(QPixmap())
        else:
            self.clear_info_panel()

    def clear_info_panel(self):
        self.selected_filename_label.setText("-")
        self.selected_tags_label.setText("-")
        self.thumbnail_placeholder.setText("영상을 선택하면 썸네일이 표시됩니다.")
        self.thumbnail_placeholder.setPixmap(QPixmap())
        self.current_selected_path = None

    def play_selected_video(self):
        if not self.current_selected_path:
            QMessageBox.warning(self, "경고", "먼저 영상을 선택해주세요.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(self.current_selected_path)
            elif sys.platform == "darwin":
                subprocess.call(["open", self.current_selected_path])
            else:
                subprocess.call(["xdg-open", self.current_selected_path])
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일을 열 수 없습니다: {e}")

    
    def filter_list(self):
        search_term = self.search_input.text().lower()
        filter_by = self.filter_combo.currentText()

        if not search_term:
            self.populate_file_list(self.video_data)
            return

        filtered_videos = []
        for video in self.video_data:
            filename = video.get("filename", "").lower()
            tags = video.get("tags", "").lower()
            
            match = False
            if filter_by == "All":
                if search_term in filename or search_term in tags:
                    match = True
            elif filter_by == "Filename":
                if search_term in filename:
                    match = True
            elif filter_by == "Tag":
                if search_term in tags:
                    match = True
            
            if match:
                filtered_videos.append(video)

        self.populate_file_list(filtered_videos)

    def _stop_all_threads(self, stop_scan=True, stop_batch=True, stop_thumbnail=True):
        """Safely stop and cleanup all threads."""
        # Stop thumbnail generation thread first
        if stop_thumbnail and self.thumbnail_gen_worker:
            self.thumbnail_gen_worker.stop() if hasattr(self.thumbnail_gen_worker, 'stop') else None
        if stop_thumbnail and self.thumbnail_gen_thread is not None:
            self.thumbnail_gen_thread.quit()
            if not self.thumbnail_gen_thread.wait(1000):  # Wait up to 1 second
                self.thumbnail_gen_thread.terminate()
                self.thumbnail_gen_thread.wait()
            self.thumbnail_gen_thread = None
            self.thumbnail_gen_worker = None
        
        # Stop scan thread
        if stop_scan and self.scan_worker:
            self.scan_worker.stop()
        if stop_scan and self.scan_thread is not None:
            self.scan_thread.quit()
            if not self.scan_thread.wait(2000):  # Wait up to 2 seconds
                self.scan_thread.terminate()
                self.scan_thread.wait()
            self.scan_thread = None
            self.scan_worker = None

        # Stop batch thumbnail thread
        if stop_batch and self.batch_thumb_worker:
            self.batch_thumb_worker.stop()
        if stop_batch and self.batch_thumb_thread is not None:
            self.batch_thumb_thread.quit()
            if not self.batch_thumb_thread.wait(2000):  # Wait up to 2 seconds
                self.batch_thumb_thread.terminate()
                self.batch_thumb_thread.wait()
            self.batch_thumb_thread = None
            self.batch_thumb_worker = None

    def closeEvent(self, event):
        """Handle application close event by stopping all threads safely."""
        try:
            self._stop_all_threads(stop_scan=True, stop_batch=True, stop_thumbnail=True)
        except Exception as e:
            print(f"Error during thread cleanup: {e}")
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = VideoManagerApp()
    ex.show()
    sys.exit(app.exec_())