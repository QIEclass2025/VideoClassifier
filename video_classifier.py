import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import threading
import cv2  # opencv-python
from datetime import timedelta
from PIL import Image, ImageTk

class VideoClassifierApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Classifier")
        self.root.geometry("800x600")

        self.video_data = []
        self.json_path = "videos.json"

        # --- Main Frame ---
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Top Frame for controls ---
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        self.select_folder_button = ttk.Button(top_frame, text="Select Folder", command=self.select_folder)
        self.select_folder_button.pack(side=tk.LEFT)

        self.search_type = tk.StringVar(value="All")
        self.search_combo = ttk.Combobox(top_frame, textvariable=self.search_type, width=15)
        self.search_combo['values'] = ("All", "Filename", "Extension", "Tag")
        self.search_combo.pack(side=tk.LEFT, padx=(10, 0))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_list())
        self.search_entry = ttk.Entry(top_frame, textvariable=self.search_var, width=40)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # --- Treeview Frame for video list ---
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_frame, columns=("Filename", "Duration", "Extension", "Tags"), show="headings")
        self.tree.heading("Filename", text="Filename")
        self.tree.heading("Duration", text="Duration")
        self.tree.heading("Extension", text="Extension")
        self.tree.heading("Tags", text="Tags")

        self.tree.column("Filename", width=300)
        self.tree.column("Duration", width=100, anchor=tk.CENTER)
        self.tree.column("Extension", width=80, anchor=tk.CENTER)
        self.tree.column("Tags", width=200)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.bind("<Double-1>", self.edit_tags_popup)

        # --- Status Bar ---
        self.status_var = tk.StringVar(value="Ready. Select a folder to start.")
        self.status_bar = ttk.Label(root, textvariable=self.status_var, anchor=tk.W, relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.load_data()

    def select_folder(self):
        folder_path = filedialog.askdirectory()
        if not folder_path:
            return

        self.status_var.set("Loading...")
        self.root.update_idletasks()
        self.tree.delete(*self.tree.get_children())
        self.video_data = []

        thread = threading.Thread(target=self.scan_videos, args=(folder_path,))
        thread.start()

    def scan_videos(self, folder_path):
        video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"}
        found_videos = []
        for root_dir, _, files in os.walk(folder_path):
            for file in files:
                if os.path.splitext(file)[1].lower() in video_extensions:
                    full_path = os.path.join(root_dir, file)
                    try:
                        filename = os.path.splitext(file)[0]
                        extension = os.path.splitext(file)[1]
                        
                        # Get video duration
                        cap = cv2.VideoCapture(full_path)
                        if not cap.isOpened():
                            continue
                        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        duration_sec = frame_count / fps if fps > 0 else 0
                        duration_str = str(timedelta(seconds=int(duration_sec)))
                        cap.release()

                        found_videos.append({
                            "path": full_path,
                            "filename": filename,
                            "extension": extension,
                            "duration": duration_str,
                            "tags": ""
                        })
                    except Exception as e:
                        print(f"Error processing {full_path}: {e}")
        
        self.video_data = found_videos
        self.save_data()
        self.root.after(0, self.update_ui_after_scan)

    def update_ui_after_scan(self):
        self.populate_treeview()
        self.status_var.set(f"Scan complete. Found {len(self.video_data)} videos.")

    def load_data(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    self.video_data = json.load(f)
                self.populate_treeview()
                self.status_var.set(f"Loaded {len(self.video_data)} videos from {self.json_path}.")
            except (json.JSONDecodeError, TypeError):
                self.status_var.set(f"Error reading {self.json_path}. File might be corrupt.")
                self.video_data = []

    def save_data(self):
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(self.video_data, f, indent=4, ensure_ascii=False)

    def populate_treeview(self, data=None):
        self.tree.delete(*self.tree.get_children())
        videos_to_display = data if data is not None else self.video_data
        for video in videos_to_display:
            self.tree.insert("", tk.END, values=(
                video.get("filename", ""),
                video.get("duration", "0:00:00"),
                video.get("extension", ""),
                video.get("tags", "")
            ), iid=video.get("path"))

    def filter_list(self):
        query = self.search_var.get().lower()
        search_mode = self.search_type.get()

        if not query:
            self.populate_treeview()
            return

        filtered_data = []
        for video in self.video_data:
            filename = video.get("filename", "").lower()
            extension = video.get("extension", "").lower()
            tags = video.get("tags", "").lower()

            match = False
            if search_mode == "All" and (query in filename or query in tags):
                match = True
            elif search_mode == "Filename" and query in filename:
                match = True
            elif search_mode == "Extension" and query in extension:
                match = True
            elif search_mode == "Tag" and query in tags:
                match = True
            
            if match:
                filtered_data.append(video)
        
        self.populate_treeview(filtered_data)

    def edit_tags_popup(self, event):
        selected_item_id = self.tree.focus()
        if not selected_item_id:
            return

        # Find the video data corresponding to the selected item
        video_to_edit = None
        for video in self.video_data:
            if video["path"] == selected_item_id:
                video_to_edit = video
                break
        
        if not video_to_edit:
            return

        # Create a Toplevel window for editing
        popup = tk.Toplevel(self.root)
        popup.title(f"Edit Tags for {video_to_edit['filename']}")
        popup.geometry("400x150")
        popup.transient(self.root) # Keep popup on top of the main window

        # Center the popup
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (400 // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (150 // 2)
        popup.geometry(f"+{x}+{y}")

        ttk.Label(popup, text="Tags (comma-separated):").pack(pady=(10, 5))
        
        tags_var = tk.StringVar(value=video_to_edit.get("tags", ""))
        tags_entry = ttk.Entry(popup, textvariable=tags_var, width=50)
        tags_entry.pack(pady=5, padx=10, fill=tk.X, expand=True)
        tags_entry.focus_set()

        def save_tags_and_close():
            new_tags = tags_var.get()
            video_to_edit["tags"] = new_tags
            self.save_data()
            self.populate_treeview() # Refresh the view
            popup.destroy()

        button_frame = ttk.Frame(popup)
        button_frame.pack(pady=10)
        save_button = ttk.Button(button_frame, text="Save", command=save_tags_and_close)
        save_button.pack(side=tk.LEFT, padx=5)
        cancel_button = ttk.Button(button_frame, text="Cancel", command=popup.destroy)
        cancel_button.pack(side=tk.LEFT, padx=5)
        
        popup.wait_window()


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoClassifierApp(root)
    root.mainloop()
