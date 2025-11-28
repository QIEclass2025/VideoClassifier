import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem, QLabel,
    QFileDialog, QMessageBox, QMenu, QAction, QInputDialog
)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt, QSize
import os
import subprocess

from .database import get_db_connection
from .video_manager import scan_and_add_videos

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Classifier")
        self.setGeometry(100, 100, 1200, 800)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.init_ui()
        self.load_videos_from_db()

    def init_ui(self):
        # Top bar: buttons and search
        top_bar_layout = QHBoxLayout()
        
        self.add_folder_btn = QPushButton("Add Folder")
        self.add_folder_btn.clicked.connect(self.add_folder)
        top_bar_layout.addWidget(self.add_folder_btn)

        self.scan_duplicates_btn = QPushButton("Find Duplicates")
        self.scan_duplicates_btn.clicked.connect(self.find_duplicates)
        top_bar_layout.addWidget(self.scan_duplicates_btn)
        
        top_bar_layout.addStretch()

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search by name, tag, extension...")
        self.search_bar.textChanged.connect(self.filter_videos)
        top_bar_layout.addWidget(self.search_bar)
        
        self.layout.addLayout(top_bar_layout)

        # Main content: video list
        self.video_list_widget = QListWidget()
        self.video_list_widget.setIconSize(QSize(256, 144))
        self.video_list_widget.setResizeMode(QListWidget.Adjust)
        self.video_list_widget.setViewMode(QListWidget.IconMode)
        self.video_list_widget.setMovement(QListWidget.Static)
        self.video_list_widget.setSpacing(15)
        self.video_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.video_list_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        self.layout.addWidget(self.video_list_widget)

    def load_videos_from_db(self, search_query=None):
        self.video_list_widget.clear()
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM videos"
        params = []
        if search_query:
            # Simple search by file name for now
            query += " WHERE file_name LIKE ?"
            params.append(f"%{search_query}%")
        
        query += " ORDER BY mod_date DESC"

        cursor.execute(query, params)
        videos = cursor.fetchall()
        conn.close()

        for video in videos:
            item = QListWidgetItem()
            
            thumbnail_path = video['thumbnail_path']
            if thumbnail_path and os.path.exists(thumbnail_path):
                icon = QIcon(thumbnail_path)
            else:
                # Create a placeholder pixmap
                pixmap = QPixmap(128, 72)
                pixmap.fill(Qt.gray)
                icon = QIcon(pixmap)
            
            item.setIcon(icon)
            item.setText(video['file_name'])
            # Store video ID in the item for later retrieval
            item.setData(Qt.UserRole, video['id'])
            self.video_list_widget.addItem(item)
            
    def add_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder_path:
            # This can be a long process, ideally run in a separate thread
            # For now, we'll run it directly and the UI might freeze
            scan_and_add_videos(folder_path)
            self.load_videos_from_db()

    def find_duplicates(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT group_concat(file_path, '\n') as files, hash
            FROM videos
            GROUP BY hash
            HAVING COUNT(id) > 1
        """)
        duplicates = cursor.fetchall()
        conn.close()

        if not duplicates:
            QMessageBox.information(self, "No Duplicates", "No duplicate files found in the library.")
            return

        message = "Found the following duplicate sets:\n\n"
        for dup_set in duplicates:
            message += f"Hash: {dup_set['hash'][:10]}...\nFiles:\n{dup_set['files']}\n\n"
        
        # Using a text edit in a message box for better readability and copy-pasting
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("Duplicates Found")
        msg_box.setText(message)
        msg_box.exec_()

    def filter_videos(self):
        search_text = self.search_bar.text()
        self.load_videos_from_db(search_text)

    def show_context_menu(self, pos):
        item = self.video_list_widget.itemAt(pos)
        if not item:
            return

        video_id = item.data(Qt.UserRole)
        
        menu = QMenu()
        
        open_loc_action = menu.addAction("Open File Location")
        rename_action = menu.addAction("Rename File")
        
        action = menu.exec_(self.video_list_widget.mapToGlobal(pos))

        if action == open_loc_action:
            self.open_file_location(video_id)
        elif action == rename_action:
            self.rename_file(video_id, item)

    def get_video_path_from_id(self, video_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM videos WHERE id = ?", (video_id,))
        result = cursor.fetchone()
        conn.close()
        return result['file_path'] if result else None

    def open_file_location(self, video_id):
        file_path = self.get_video_path_from_id(video_id)
        if not file_path: return

        directory = os.path.dirname(file_path)
        if sys.platform == 'win32':
            # Using explorer to select the file
            subprocess.run(['explorer', '/select,', os.path.normpath(file_path)])
        elif sys.platform == 'darwin':
            subprocess.run(['open', '-R', file_path])
        else:
            subprocess.run(['xdg-open', directory])
            
def rename_file(self, video_id, item):
        file_path = self.get_video_path_from_id(video_id)
        if not file_path: return

        old_name = os.path.basename(file_path)
        new_name, ok = QInputDialog.getText(self, "Rename File", "Enter new name:", text=old_name)

        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(file_path), new_name)
            try:
                os.rename(file_path, new_path)
                
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE videos SET file_path = ?, file_name = ? WHERE id = ?", (new_path, new_name, video_id))
                conn.commit()
                conn.close()
                
                item.setText(new_name) # Update item text in UI
                QMessageBox.information(self, "Success", f"Renamed '{old_name}' to '{new_name}'.")

            except OSError as e:
                QMessageBox.warning(self, "Error", f"Could not rename file: {e}")
