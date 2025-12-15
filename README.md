# Video Classifier (영상 분류기)

**Video Classifier**는 로컬 디렉토리에 있는 영상 파일들을 직관적인 UI로 관리하고 시청할 수 있는 Python 데스크톱 애플리케이션입니다.

복잡한 영상 파일들을 **자동으로 스캔**하여 썸네일과 함께 리스트로 보여주며, **태그 관리** 및 **타임라인 저장** 기능을 통해 영상을 체계적으로 분류하고 분석할 수 있습니다.


## 주요 기능

* **직관적인 UI**: 눈이 편안한 다크 테마와 직관적인 플레이어/리스트 레이아웃을 제공합니다.
* **자동 디렉토리 스캔**: 폴더를 선택하면 하위 경로의 모든 영상 파일(.mp4, .avi, .mkv 등)을 자동으로 찾아냅니다.
* **썸네일 자동 생성**: OpenCV를 활용해 영상의 대표 이미지를 자동으로 추출하여 보여줍니다.
* **타임라인 기능**: 영상의 중요한 순간을 기록하고, 클릭 한 번으로 해당 구간으로 이동할 수 있습니다.
* **태그 및 검색 시스템**: 영상에 태그를 추가하고, 파일명이나 태그로 원하는 영상을 빠르게 검색할 수 있습니다.
* **데이터 자동 저장**: 모든 메타데이터(태그, 타임라인 등)는 `videos.json`에 안전하게 저장됩니다.


## 기술 스택 (Tech Stack)

* **Language**: Python 3.13
* **GUI Framework**: PyQt5 (Pure Code)
* **Media Processing**: OpenCV (`opencv-python`), Pillow
* **Dependency Management**: uv


## 설치 및 실행 방법

### 1. 사전 요구 사항 (필수!)
본 프로그램은 고화질 영상 재생을 위해 Windows 시스템 코덱을 사용합니다. 영상이나 소리가 나오지 않을 경우 아래 필터를 반드시 설치해주세요.
* **[LAV Filters 다운로드](https://github.com/Nevcairiel/LAVFilters/releases)** (Installer 버전을 받아 설치하세요)

### 2. 프로젝트 클론 및 이동
```bash
git clone [https://github.com/QIEclass2025/VideoClassifier.git](https://github.com/QIEclass2025/VideoClassifier.git)
cd VideoClassifier
```

### 3. 라이브러리 설치
이 프로젝트는 최신 패키지 매니저인 uv를 사용합니다.

방법 A: uv를 사용하는 경우 (권장)
```Bash

# 의존성 동기화 및 가상환경 생성
uv sync
```
방법 B: pip를 사용하는 경우
```Bash

pip install PyQt5 opencv-python Pillow
```
### 4. 프로그램 실행
```Bash

# uv 사용 시
uv run team_code3.5.py

# 일반 python 사용 시
python team_code3.5.py
```


## 사용 가이드

**1. 폴더 열기**: 우측 상단의 폴더 열기 버튼을 눌러 영상이 있는 폴더를 선택합니다.

**2. 영상 재생** 우측 리스트에서 영상을 클릭하면 좌측 플레이어에서 재생됩니다.

**3. 정보 수정**: 리스트의 영상을 더블 클릭하면 이름 변경, 태그 수정, 경로 복사 메뉴를 사용할 수 있습니다.

**4. 타임라인 추가**: 영상 재생 중 중요한 장면에서 타임라인 추가 버튼을 누르세요. 설명과 함께 저장되어 언제든 다시 찾아볼 수 있습니다.

**5. 검색**: 상단 검색창을 이용해 파일명이나 태그로 영상을 필터링하세요.


## 프로젝트 구조  

```bash
VideoClassifier  
├── .thumbnails          # 생성된 썸네일 이미지 (자동 생성)  
├── videos.json          # 영상 메타데이터 및 태그 저장소 (자동 생성)  
├── team_code3.5.py      # 메인 소스 코드  
├── pyproject.toml       # 프로젝트 설정 및 의존성 관리  
├── uv.lock              # 패키지 잠금 파일  
├── .python-version      # 파이썬 버전 명시  
└── README.md            # 프로젝트 설명서  
```

**Developers: QIE Team 태훈 인영 재민**
