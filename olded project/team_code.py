import sys
import os

# PyQt5가 설치된 경로를 찾아서 플러그인 위치를 강제로 등록
import PyQt5
qt_root_path = os.path.dirname(PyQt5.__file__)
plugin_path = os.path.join(qt_root_path, 'Qt5', 'plugins')
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QTableWidget, QTableWidgetItem, QHeaderView, 
                             QAbstractItemView, QMenu, QInputDialog, QMessageBox, QComboBox)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget

# 클래스 구조로 만드는 이유:
# 프로그램의 '상태'(현재 재생 중인 영상, 리스트 정보 등)를 저장하고 
# 여러 함수(기능)들끼리 변수를 공유하기 위해서 'self'를 사용해야 하기 때문입니다.
class VideoManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 1. 윈도우(창) 기본 설정
        self.setWindowTitle('똑똑한 영상 관리자 (Smart Video Manager)') # 창 제목
        self.resize(1000, 700) # 창 크기 (가로, 세로)

        # 2. UI 화면 구성 초기화 함수 실행
        self.init_ui()

    def init_ui(self):
        """화면의 전체적인 레이아웃을 잡는 함수입니다."""
        
        # PyQt는 '위젯'들을 담을 그릇(Layout)이 필요합니다.
        # 전체 화면을 감싸는 가장 큰 그릇(central_widget)을 만듭니다.
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 전체 레이아웃은 세로 방향(VBox)으로 쌓겠습니다.
        # [상단 검색창]
        # [중단 플레이어 + 태그 편집]
        # [하단 파일 리스트]
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # --- [A. 상단 검색 영역] ---
        search_layout = QHBoxLayout() # 가로 방향 정렬
        
        # 검색 필터 (콤보박스)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["전체", "태그", "파일이름", "확장자"])
        
        # 검색어 입력창
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("검색어를 입력하세요...") # 안내 문구
        
        # 검색 버튼
        self.search_btn = QPushButton("검색")
        
        # 레이아웃에 추가
        search_layout.addWidget(self.filter_combo)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        
        main_layout.addLayout(search_layout) # 전체 레이아웃에 상단 영역 추가

        # --- [B. 중단 플레이어 및 편집 영역] ---
        middle_layout = QHBoxLayout()

        # 1. 비디오 플레이어 (왼쪽) - 중요!
        # QVideoWidget: 영상을 실제로 보여주는 화면
        self.video_widget = QVideoWidget()
        # QMediaPlayer: 영상을 재생/정지하는 컨트롤러
        self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.media_player.setVideoOutput(self.video_widget) # 컨트롤러와 화면 연결
        
        self.video_widget.setMinimumSize(600, 400) # 플레이어 최소 크기 지정
        self.video_widget.setStyleSheet("background-color: black;") # 빈 화면 검은색

        # 2. 태그/정보 편집창 (오른쪽)
        edit_layout = QVBoxLayout()
        edit_label = QLabel("Editing Interface")
        edit_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        # 예시로 보여줄 입력창들
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("태그 입력 (예: #여행 #가족)")
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("메모 입력")
        save_btn = QPushButton("정보 저장")

        # 편집창 레이아웃 구성
        edit_layout.addWidget(edit_label)
        edit_layout.addWidget(QLabel("태그:"))
        edit_layout.addWidget(self.tag_input)
        edit_layout.addWidget(QLabel("메모:"))
        edit_layout.addWidget(self.desc_input)
        edit_layout.addWidget(save_btn)
        edit_layout.addStretch(1) # 빈 공간을 채워 위젯들을 위로 밀어올림

        # 중단 레이아웃에 추가 (비디오 7 : 편집창 3 비율)
        middle_layout.addWidget(self.video_widget, 7)
        middle_layout.addLayout(edit_layout, 3)

        main_layout.addLayout(middle_layout)

        # --- [C. 하단 파일 리스트 영역] ---
        # QTableWidget: 엑셀처럼 행/열이 있는 표를 만듭니다.
        self.file_list = QTableWidget()
        self.file_list.setColumnCount(4) # 4개의 열 (썸네일, 파일명, By, 태그)
        self.file_list.setHorizontalHeaderLabels(["썸네일", "File Name", "By", "Tags"])
        
        # 테이블 모양 다듬기
        self.file_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch) # 꽉 차게 늘리기
        self.file_list.setSelectionBehavior(QAbstractItemView.SelectRows) # 한 줄씩 선택되게
        self.file_list.setEditTriggers(QAbstractItemView.NoEditTriggers) # 더블클릭 수정 금지 (우클릭으로만 하게)

        # ★ 중요: 우클릭 메뉴 활성화 ★
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_context_menu)

        # ★ 중요: 리스트 클릭 시 영상 재생 연결 ★
        self.file_list.cellClicked.connect(self.on_file_clicked)

        main_layout.addWidget(self.file_list)

        # (테스트용 가짜 데이터 추가 - 나중에 DB 연동 시 삭제할 부분)
        self.add_dummy_data()

    def add_dummy_data(self):
        """UI 테스트를 위해 임시로 데이터를 넣어보는 함수입니다."""
        # 실제로는 여기서 DB 담당 친구가 만든 함수를 호출해서 데이터를 받아와야 합니다.
        # 예: data = db.get_all_videos()
        
        # [파일명, By, 태그, 실제경로]
        # 테스트를 위해 본인 컴퓨터에 있는 실제 영상 경로로 바꿔서 테스트해보세요!
        sample_data = [
            ["여행_vlog.mp4", "나", "#여행 #바다", r"C:\Users\Public\Videos\Sample Videos\Wildlife.wmv"], 
            ["강의_자료구조.mp4", "교수님", "#공부 #코딩", r"C:\Test\lecture.mp4"]
        ]

        self.file_list.setRowCount(len(sample_data))
        for row_idx, row_data in enumerate(sample_data):
            # 썸네일은 일단 텍스트로 대체 (나중에 이미지로 교체 필요)
            self.file_list.setItem(row_idx, 0, QTableWidgetItem("📷Img")) 
            self.file_list.setItem(row_idx, 1, QTableWidgetItem(row_data[0]))
            self.file_list.setItem(row_idx, 2, QTableWidgetItem(row_data[1]))
            self.file_list.setItem(row_idx, 3, QTableWidgetItem(row_data[2]))
            
            # 숨겨진 데이터로 '실제 파일 경로'를 저장해둡니다. (재생할 때 필요함)
            self.file_list.item(row_idx, 1).setData(Qt.UserRole, row_data[3])

    def on_file_clicked(self, row, col):
        """리스트의 항목을 클릭했을 때 실행되는 함수입니다."""
        # 1. 파일명 칸(1번 컬럼)에 숨겨둔 실제 파일 경로를 가져옵니다.
        file_path = self.file_list.item(row, 1).data(Qt.UserRole)
        
        print(f"선택된 파일: {file_path}") # 디버깅용 출력

        if file_path and os.path.exists(file_path):
            # 2. 미디어 플레이어에 파일을 로드하고 재생합니다.
            self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
            self.media_player.play()
        else:
            print("파일을 찾을 수 없습니다.")

    def show_context_menu(self, position):
        """우클릭 했을 때 메뉴를 띄우는 함수입니다 (F. 기능 구현)"""
        menu = QMenu()
        
        # 메뉴 항목 만들기
        action_open = menu.addAction("📂 파일 위치 열기")
        action_rename = menu.addAction("✏️ 이름 수정")
        
        # 메뉴가 선택되었을 때 실행할 함수 연결
        action = menu.exec_(self.file_list.mapToGlobal(position))
        
        if action == action_open:
            self.open_file_location()
        elif action == action_rename:
            self.rename_file()

    def open_file_location(self):
        """선택된 파일의 폴더를 여는 함수"""
        row = self.file_list.currentRow()
        if row == -1: return # 선택된 게 없으면 종료

        file_path = self.file_list.item(row, 1).data(Qt.UserRole)
        if file_path and os.path.exists(file_path):
            # 탐색기에서 해당 파일 선택된 상태로 열기 (Windows 전용)
            # os.path.normpath: 경로의 슬래시(\)를 윈도우 스타일로 맞춰줌
            os.system(f'explorer /select,"{os.path.normpath(file_path)}"')
        else:
            QMessageBox.warning(self, "오류", "파일이 존재하지 않습니다.")

    def rename_file(self):
        """파일 이름을 변경하는 함수"""
        row = self.file_list.currentRow()
        if row == -1: return

        # 현재 이름 가져오기
        current_item = self.file_list.item(row, 1)
        current_name = current_item.text()
        full_path = current_item.data(Qt.UserRole) # 전체 경로

        # 입력창 띄우기 (제목, 내용, 기본값)
        new_name, ok = QInputDialog.getText(self, "이름 수정", "새로운 파일 이름을 입력하세요:", text=current_name)

        if ok and new_name:
            # 확장자 유지하기 로직
            file_dir = os.path.dirname(full_path) # 폴더 경로
            ext = os.path.splitext(full_path)[1] # .mp4 같은 확장자
            
            # 사용자가 확장자를 안 썼으면 붙여줌
            if not new_name.endswith(ext):
                new_name += ext
            
            new_path = os.path.join(file_dir, new_name)

            try:
                # 1. 실제 파일 이름 변경 (OS 레벨)
                os.rename(full_path, new_path)
                
                # 2. 리스트(UI) 업데이트
                current_item.setText(new_name)
                current_item.setData(Qt.UserRole, new_path) # 변경된 경로로 데이터 갱신
                
                # 3. 나중에 여기에 DB 업데이트 함수도 추가해야 함!
                # db.update_filename(old_path, new_path) 이런 식으로.
                
                QMessageBox.information(self, "성공", "이름이 변경되었습니다.")
                
            except Exception as e:
                QMessageBox.critical(self, "오류", f"이름 변경 실패: {e}")

if __name__ == '__main__':
    # 프로그램 실행 코드
    app = QApplication(sys.argv)
    ex = VideoManagerApp()
    ex.show()
    sys.exit(app.exec_())