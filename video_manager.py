import os
import hashlib
import cv2
import time
from database import get_db_connection

THUMBNAIL_DIR = "thumbnails"
SUPPORTED_EXTENSIONS = ['.mp4', '.avi', '.mkv', '.mov']

def ensure_thumbnail_dir_exists():
    """Creates the thumbnail directory if it doesn't exist."""
    if not os.path.exists(THUMBNAIL_DIR):
        os.makedirs(THUMBNAIL_DIR)

def calculate_hash(file_path):
    """Calculates the SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256.update(byte_block)
        return sha256.hexdigest()
    except IOError:
        print(f"Could not read file for hashing: {file_path}")
        return None

def get_video_metadata(file_path):
    """Extracts metadata from a video file."""
    try:
        stat = os.stat(file_path)
        file_size = stat.st_size / (1024 * 1024)  # MB
        mod_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
        
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None, None, None

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        cap.release()
        
        return file_size, mod_date, duration
    except Exception as e:
        print(f"Error getting metadata for {file_path}: {e}")
        return None, None, None

def generate_thumbnail(file_path, video_hash):
    """Generates a thumbnail for a video file."""
    ensure_thumbnail_dir_exists()
    thumbnail_path = os.path.join(THUMBNAIL_DIR, f"{video_hash}.jpg")

    if os.path.exists(thumbnail_path):
        return thumbnail_path

    try:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        # Capture frame at 10% of the video
        target_frame_pos = int(frame_count * 0.1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_pos)
        
        ret, frame = cap.read()
        cap.release()

        if ret:
            # Save with compression
            cv2.imwrite(thumbnail_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            return thumbnail_path
        return None
    except Exception as e:
        print(f"Error generating thumbnail for {file_path}: {e}")
        return None

def scan_and_add_videos(directory):
    """Scans a directory for videos and adds them to the database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    for root, _, files in os.walk(directory):
        for file in files:
            if any(file.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                file_path = os.path.join(root, file)
                
                # Check if already in DB
                cursor.execute("SELECT id FROM videos WHERE file_path = ?", (file_path,))
                if cursor.fetchone():
                    print(f"Skipping already indexed file: {file_path}")
                    continue

                print(f"Processing new file: {file_path}")
                file_hash = calculate_hash(file_path)
                if not file_hash:
                    continue
                
                # Check for duplicates by hash
                cursor.execute("SELECT file_path FROM videos WHERE hash = ?", (file_hash,))
                duplicate = cursor.fetchone()
                if duplicate:
                    print(f"Found duplicate file: {file_path} is same as {duplicate['file_path']}")
                    # Here we could ask the user to delete, but for now just log it.
                    # We will still add it to the DB to be able to manage it.
                
                file_name = os.path.basename(file_path)
                file_size, mod_date, duration = get_video_metadata(file_path)
                thumbnail_path = generate_thumbnail(file_path, file_hash)

                if file_size is not None:
                    cursor.execute("""
                    INSERT INTO videos (file_path, file_name, file_size, mod_date, duration, thumbnail_path, hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (file_path, file_name, file_size, mod_date, duration, thumbnail_path, file_hash))
    
    conn.commit()
    conn.close()
