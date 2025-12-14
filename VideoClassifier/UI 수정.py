import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import json
import threading
import cv2
from datetime import timedelta
import sys
import subprocess

class VideoClassifierApp:
    def __init__(self, root):
        self.root = root
        self.root.title("My Video Library (YouTube Style)")
        self.root.geometry("1100x700")

        # --- 데이터 초기화 ---
        self.video_data = [] # 현재 화면에 보이는 데이터
        self.all_video_db = {} # 전체 데이터
        self.json_path = "videos.json"
        self.image_refs = [] # 이미지 가비지 컬렉션 방지용 리스트
        
        # --- 스타일 설정 ---
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except:
            pass
        
        # 색상 테마 (유튜브 느낌: 흰색/회색/빨강)
        self.BG_COLOR = "#f9f9f9" # 전체 배경
        self.CARD_BG = "white"    # 영상 카드 배경
        self.HEADER_BG = "white"  # 상단 헤더 배경
        
        self.root.configure(bg=self.BG_COLOR)
        
        # 앱 시작 시 기존 DB 로드
        self.load_full_db()
        
        # UI 초기화
        self.init_ui()

    def init_ui(self):
        # 1. 상단 헤더 (검색창 + 폴더 선택)
        header_frame = tk.Frame(self.root, bg=self.HEADER_BG, height=60, pady=10, padx=20)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        header_frame.pack_propagate(False) # 높이 고정

        # 로고 텍스트 (YouTube 느낌)
        logo_label = tk.Label(header_frame, text="▶ VideoTube", bg=self.HEADER_BG, fg="#FF0000", font=("Arial", 16, "bold"))
        logo_label.pack(side=tk.LEFT)

        # 폴더 선택 버튼 (오른쪽)
        btn_folder = tk.Button(header_frame, text="📂 폴더 열기", command=self.select_folder, 
                               bg="#f0f0f0", relief="flat", padx=10, pady=5)
        btn_folder.pack(side=tk.RIGHT)

        # 검색바 (가운데)
        search_frame = tk.Frame(header_frame, bg=self.HEADER_BG)
        search_frame.pack(side=tk.TOP) # 가운데 정렬을 위해

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_grid())
        
        entry_search = tk.Entry(search_frame, textvariable=self.search_var, width=40, font=("Arial", 11), relief="solid", bd=1)
        entry_search.pack(side=tk.LEFT, padx=5, ipady=3)
        
        lbl_icon = tk.Label(search_frame, text="🔍", bg=self.HEADER_BG, font=("Arial", 12))
        lbl_icon.pack(side=tk.LEFT)

        # 2. 메인 컨텐츠 영역 (스크롤 가능한 캔버스)
        self.canvas = tk.Canvas(self.root, bg=self.BG_COLOR, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        
        # 실제 카드들이 들어갈 프레임
        self.grid_frame = tk.Frame(self.canvas, bg=self.BG_COLOR)
        
        # 캔버스 설정
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20, pady=10)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 이벤트 바인딩
        self.grid_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel) # 마우스 휠 스크롤

        # 초기 안내 메시지
        if not self.all_video_db:
            tk.Label(self.grid_frame, text="상단의 [폴더 열기]를 눌러 영상을 불러오세요.", 
                     bg=self.BG_COLOR, font=("Arial", 14), fg="#888").pack(pady=50)
        else:
            # DB에 내용이 있으면 바로 보여주기
            self.video_data = list(self.all_video_db.values())
            self.populate_grid()

    def on_frame_configure(self, event):
        """스크롤 영역 자동 조정"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_mousewheel(self, event):
        """마우스 휠 스크롤"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def populate_grid(self, data=None):
        """그리드 뷰에 영상 카드 배치"""
        # 기존 카드들 삭제
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        
        self.image_refs = [] # 이미지 참조 초기화
        
        videos = data if data is not None else self.video_data
        
        if not videos:
            tk.Label(self.grid_frame, text="검색 결과가 없습니다.", bg=self.BG_COLOR, font=("Arial", 12)).pack(pady=20)
            return

        # 그리드 설정 (한 줄에 3개 또는 4개)
        COLUMNS = 4 
        row = 0
        col = 0
        
        for video in videos:
            self.create_video_card(video, row, col)
            col += 1
            if col >= COLUMNS:
                col = 0
                row += 1

    def create_video_card(self, video, row, col):
        """영상 카드 하나를 생성하는 함수"""
        # 카드 프레임 (외곽선 포함)
        card = tk.Frame(self.grid_frame, bg=self.CARD_BG, bd=1, relief="solid")
        card.grid(row=row, column=col, padx=10, pady=15, sticky="n")
        
        # --- 1. 썸네일 이미지 ---
        thumb_path = video.get("thumbnail_path")
        img_obj = None
        
        if thumb_path and os.path.exists(thumb_path):
            try:
                # tkinter PhotoImage 사용
                img_obj = tk.PhotoImage(file=thumb_path)
                # 이미지 크기가 너무 크면 안되므로 (생성시 이미 리사이징 했지만 안전장치)
                # 여기서는 그냥 표시 (generate_thumbnail에서 250px 너비로 맞출 예정)
            except:
                pass
        
        # 이미지가 없으면 검은색 박스로 대체
        if img_obj:
            self.image_refs.append(img_obj) # 참조 유지
            lbl_thumb = tk.Label(card, image=img_obj, bg="black", width=240, height=135)
        else:
            lbl_thumb = tk.Label(card, text="No Image", bg="black", fg="white", width=34, height=9) # 대략적 크기
            
        lbl_thumb.pack(side=tk.TOP, fill=tk.BOTH)
        
        # --- 2. 정보 텍스트 ---
        info_frame = tk.Frame(card, bg=self.CARD_BG, padx=8, pady=5)
        info_frame.pack(fill=tk.BOTH)
        
        # 제목 (두 줄 넘어가면 잘리게 처리하는건 복잡하니 길이 제한)
        title_text = video.get("filename", "Unknown")
        if len(title_text) > 25: title_text = title_text[:22] + "..."
        
        lbl_title = tk.Label(info_frame, text=title_text, font=("Arial", 11, "bold"), 
                             bg=self.CARD_BG, anchor="w", fg="#030303")
        lbl_title.pack(fill=tk.X)
        
        # 메타 정보 (작성자, 시간, 태그)
        by_text = video.get("by") if video.get("by") else "Unknown Author"
        dur_text = video.get("duration", "0:00")
        meta_text = f"{by_text} • {dur_text}"
        
        lbl_meta = tk.Label(info_frame, text=meta_text, font=("Arial", 9), 
                            bg=self.CARD_BG, fg="#606060", anchor="w")
        lbl_meta.pack(fill=tk.X)
        
        # 태그 (있으면 표시)
        tags = video.get("tags", "")
        if tags:
            lbl_tags = tk.Label(info_frame, text=f"#{tags}", font=("Arial", 8), 
                                bg=self.CARD_BG, fg="#3ea6ff", anchor="w")
            lbl_tags.pack(fill=tk.X)

        # --- 3. 이벤트 바인딩 (클릭) ---
        # 카드 내의 어떤 요소를 눌러도 동작하게 함
        for widget in [card, lbl_thumb, info_frame, lbl_title, lbl_meta]:
            if 'lbl_tags' in locals() and widget == lbl_tags: continue # 태그도 포함
            # 좌클릭: 재생
            widget.bind("<Button-1>", lambda e, p=video["path"]: self.play_video(p))
            # 우클릭: 메뉴
            widget.bind("<Button-3>", lambda e, v=video: self.show_context_menu(e, v))

    def show_context_menu(self, event, video):
        """우클릭 메뉴"""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="📝 정보 수정 (태그/작성자)", command=lambda: self.open_edit_popup(video))
        menu.add_command(label="✏️ 파일 이름 변경", command=lambda: self.rename_file(video))
        menu.add_separator()
        menu.add_command(label="📂 폴더 열기", command=lambda: self.open_file_folder(video))
        
        menu.tk_popup(event.x_root, event.y_root)

    def open_edit_popup(self, video):
        """정보 수정 팝업창"""
        popup = tk.Toplevel(self.root)
        popup.title("정보 수정")
        popup.geometry("300x200")
        
        tk.Label(popup, text="작성자 (By):").pack(pady=(10,0))
        entry_by = tk.Entry(popup, width=30)
        entry_by.insert(0, video.get("by", ""))
        entry_by.pack(pady=5)
        
        tk.Label(popup, text="태그 (Tags):").pack(pady=(10,0))
        entry_tags = tk.Entry(popup, width=30)
        entry_tags.insert(0, video.get("tags", ""))
        entry_tags.pack(pady=5)
        
        def save():
            new_by = entry_by.get()
            new_tags = entry_tags.get()
            
            # DB 업데이트
            path = video["path"]
            if path in self.all_video_db:
                self.all_video_db[path]["by"] = new_by
                self.all_video_db[path]["tags"] = new_tags
                
            self.save_full_db()
            self.filter_grid() # 화면 갱신
            popup.destroy()
            
        tk.Button(popup, text="저장", command=save, bg="#005a7d", fg="white").pack(pady=20)

    def rename_file(self, video):
        """파일 이름 변경"""
        old_path = video["path"]
        old_name = video["filename"]
        ext = video["extension"]
        
        new_name = simpledialog.askstring("이름 변경", "새로운 파일 이름을 입력하세요:", initialvalue=old_name)
        if new_name and new_name != old_name:
            folder = os.path.dirname(old_path)
            new_path = os.path.join(folder, new_name + ext).replace('\\', '/')
            
            try:
                os.rename(old_path, new_path)
                
                # DB 정보 갱신 (Key도 바꿔야 함)
                del self.all_video_db[old_path]
                
                video["path"] = new_path
                video["filename"] = new_name
                self.all_video_db[new_path] = video
                
                self.save_full_db()
                self.filter_grid()
                messagebox.showinfo("성공", "파일 이름이 변경되었습니다.")
            except Exception as e:
                messagebox.showerror("오류", f"이름 변경 실패: {e}")

    def open_file_folder(self, video):
        path = video["path"]
        folder = os.path.dirname(path)
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.call(["open", folder])
            else:
                subprocess.call(["xdg-open", folder])
        except:
            pass

    def filter_grid(self):
        """검색어에 따라 그리드 갱신"""
        query = self.search_var.get().lower()
        if not query:
            self.video_data = list(self.all_video_db.values())
        else:
            filtered = []
            for v in self.all_video_db.values():
                # 이름, 태그, 작성자 중 하나라도 포함되면 검색
                if (query in v.get("filename", "").lower() or 
                    query in v.get("tags", "").lower() or
                    query in v.get("by", "").lower()):
                    filtered.append(v)
            self.video_data = filtered
            
        self.populate_grid()

    # --- 기존 로직 유지 (DB, 스캔 등) ---
    def load_full_db(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for v in data:
                        self.all_video_db[v['path']] = v
            except:
                self.all_video_db = {}

    def save_full_db(self):
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(list(self.all_video_db.values()), f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Save error: {e}")

    def play_video(self, file_path):
        try:
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                subprocess.call(["open", file_path])
            else:
                subprocess.call(["xdg-open", file_path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file: {e}")

    def select_folder(self):
        folder_path = filedialog.askdirectory()
        if not folder_path:
            return
        
        # 스캔 중임을 알리는 팝업 (간단하게)
        threading.Thread(target=self.scan_videos, args=(folder_path,)).start()

    def scan_videos(self, folder_path):
        thumb_dir = "thumbnails"
        if not os.path.exists(thumb_dir):
            os.makedirs(thumb_dir)

        video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"}
        found_count = 0
        
        for root_dir, _, files in os.walk(folder_path):
            for file in files:
                if os.path.splitext(file)[1].lower() in video_extensions:
                    full_path = os.path.join(root_dir, file).replace('\\', '/')
                    
                    if full_path in self.all_video_db:
                        existing = self.all_video_db[full_path]
                        if not os.path.exists(existing.get('thumbnail_path', '')):
                            self.generate_thumbnail(full_path, thumb_dir, file, existing)
                    else:
                        new_info = {
                            "path": full_path,
                            "filename": os.path.splitext(file)[0],
                            "extension": os.path.splitext(file)[1],
                            "tags": "", "by": "", "duration": "0:00"
                        }
                        self.generate_thumbnail(full_path, thumb_dir, file, new_info)
                        self.all_video_db[full_path] = new_info
                        found_count += 1
        
        self.save_full_db()
        # UI 갱신은 메인 스레드에서 해야 안전하지만, 간단한 갱신은 여기서 호출 후 내부 처리
        self.root.after(0, self.filter_grid)
        self.root.after(0, lambda: messagebox.showinfo("완료", f"스캔 완료! {found_count}개의 새 영상을 찾았습니다."))

    def generate_thumbnail(self, full_path, thumb_dir, filename, info_dict):
        try:
            cap = cv2.VideoCapture(full_path)
            if cap.isOpened():
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                duration_sec = frame_count / fps if fps > 0 else 0
                
                # 시간 포맷 예쁘게 (0:00:00 -> 05:23)
                td = timedelta(seconds=int(duration_sec))
                info_dict["duration"] = str(td)
                
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count // 10)
                ret, frame = cap.read()
                if ret:
                    # 유튜브 썸네일 비율 (16:9)에 맞춰 리사이징
                    # 너비 240px 기준 -> 높이 135px
                    target_w, target_h = 240, 135
                    frame_resized = cv2.resize(frame, (target_w, target_h))
                    
                    safe_name = f"{filename}_{os.path.getsize(full_path)}.png"
                    thumb_path = os.path.join(thumb_dir, safe_name)
                    cv2.imwrite(thumb_path, frame_resized)
                    info_dict["thumbnail_path"] = thumb_path
            cap.release()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoClassifierApp(root)
    root.mainloop()