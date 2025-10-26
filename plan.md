# 약 관리 시스템 개발 계획서

## 중요 사항

### 개발 범위
- **본 계획서는 소프트웨어 구현에 집중합니다**
- 하드웨어 관련 내용(모터, 센서, GPIO 제어)은 참고용으로 포함되어 있습니다
- 실제 구현은 소프트웨어 로직(음성 처리, 이미지 처리, DB 관리)을 우선합니다
- 향후 하드웨어 통합 시 센서 활성화 코드를 추가할 수 있습니다

### 기존 코드 통합
- **기존 팀원이 작성한 코드와 설정을 우선 파악해야 합니다**
- 기존 DB 스키마, 데이터, 웹페이지 등의 세팅을 먼저 분석합니다
- 본 계획서의 내용은 기존 코드 파악 후 조정될 수 있습니다
- 중복 작업을 방지하고 기존 코드를 최대한 재사용합니다

### 문서 작성 원칙
- 이모지를 사용하지 않습니다
- 명확하고 기술적인 용어를 사용합니다

---

## 목차
1. [시스템 개요](#시스템-개요)
2. [유저 플로우](#유저-플로우)
3. [시스템 아키텍처](#시스템-아키텍처)
4. [기술 스택](#기술-스택)
5. [데이터베이스 설계](#데이터베이스-설계)
6. [모듈별 상세 설계](#모듈별-상세-설계)
7. [개발 단계](#개발-단계)
8. [에러 처리](#에러-처리)

---

## 시스템 개요

### 목적
음성 인터페이스 기반 스마트 약 관리 시스템 개발

### 주요 기능
- 음성 명령으로 약 관리
- 자동 약봉지 스캔 및 정보 추출
- 약물 상호작용(DUR) 체크
- 자동 약 분출
- 복용 알림

### 하드웨어
- **메인 컨트롤러**: Raspberry Pi 4
- **입출력**: 
  - Raspberry Pi Camera Module
  - 마이크 (Porcupine Wake Word)
  - 스피커 (ElevenLabs TTS)
- **액추에이터**:
  - 모터 (약봉투 삽입/분출용)
  - 거리 센서 (약 투입 감지)

---

## 유저 플로우

### 0) 유저 설정
**목적**: 개인화된 음성 설정
- 원하는 목소리 등록

---

### 1) 약봉지 스캔

**트리거**: Wake word or 스위치

**플로우**:
```
Wake word 감지 
→ "스캔해줘" (음성 입력)
→ STT (Speech-to-Text)
→ 카메라 활성화
→ 약봉지 이미지 촬영
→ 정보 추출 (OCR + LLM)
→ DB 저장
→ DUR 체크
```

**분기**:
- **a) 충돌 문제가 없을 경우**
  - LLM API → `"{약}이 스캔되었습니다. 약봉투를 삽입해줘"` → ElevenLabs TTS

- **b) 충돌이 있을 경우**
  - LLM API → `"{약1}과 {약2} 충돌"` → ElevenLabs TTS

---

### 2) 약봉투 삽입

**플로우**:
```
모터 + 거리센서 활성화
→ 약 투입 (사용자)
→ 거리 감소 감지
→ 모터 비활성화
```

---

### 3) 상태 확인

**트리거**: Wake word or 스위치

**플로우**:
```
사용자 질문 (재고, 충돌, 복용법, 주의사항)
→ GPT Real-time API
  - STT → LLM → DB 접근 → TXT 출력
→ ElevenLabs TTS
→ 음성 응답
```

---

### 4) 약 분출

**트리거**: Wake word or 스위치 → "아침약 줘"

**플로우**:
```
STT → LLM → DB 접근
→ 해당 시간대 약 정보 조회
```

**분기**:

**1) DB에 1층만 있을 때**
```
1층 모터 + 카메라 활성화
→ 절취선 인식
→ 모터 비활성화
→ 잡기모터 회전
→ 사용자가 약을 뜯음
→ 절취선 옆 비어있음 인식
→ 잡기모터 회전
→ 모터 활성화
```

**2) DB에 1층, 2층 둘다 있을 때**
```
1)의 과정 + ? + 1)의 과정
```
*(구체적인 2층 처리 로직 추가 필요)*

---

### 5) 약 알림

**트리거**: 6시 정각 (설정 가능)

**플로우**:
```
스케줄러 실행
→ LLM → DB 접근
→ TXT 출력
→ ElevenLabs TTS
→ "~약 드셔야 합니다" (음성 알림)
```

---

## 시스템 아키텍처

### 전체 구조
```
메인 프로세스 (asyncio 기반)
├── 모듈 1: Wake Word 감지 (Porcupine)
├── 모듈 2: 음성 처리 (GPT Real-time API)
├── 모듈 3: 하드웨어 제어 (모터, 카메라, 센서)
├── 모듈 4: DB 관리 (MySQL)
└── 모듈 5: 스케줄러 (약 알림)
```

### 비동기 처리 방식
- **asyncio** 사용 (라즈베리파이 리소스 효율성)
- 모든 모듈은 독립적으로 동시 실행
- 모듈 간 통신은 `asyncio.Queue` 사용

---

## 기술 스택

### 언어 및 프레임워크
- **Python 3.8+**
- **asyncio** (비동기 처리)

### 주요 라이브러리

#### 음성 처리
- **Porcupine**: Wake word 감지
- **OpenAI Python SDK**: GPT Real-time API (WebSocket 기반)
- **ElevenLabs API**: TTS (음성 출력)

#### 이미지 처리
- **picamera2**: Raspberry Pi Camera 제어
- **EasyOCR**: 텍스트 추출 (OCR)
- **OpenCV**: 이미지 전처리, 절취선 인식

#### 데이터베이스
- **MySQL**: 메인 데이터베이스
- **mysql-connector-python**: Python MySQL 드라이버

#### 하드웨어 제어
- **RPi.GPIO** 또는 **gpiozero**: GPIO 핀 제어
- **pigpio**: 고급 GPIO 제어 (PWM, 서보 모터)

#### 기타
- **APScheduler**: 약 알림 스케줄러
- **python-dotenv**: 환경 변수 관리

---

## 데이터베이스 설계

### 테이블 구조

#### 1. medicines (약 정보)
```sql
CREATE TABLE medicines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    manufacturer VARCHAR(255),
    ingredients TEXT,
    dosage VARCHAR(100),
    usage_instructions TEXT,
    precautions TEXT,
    image_path VARCHAR(500),
    floor INT DEFAULT 1,  -- 약 보관 층 (1층 또는 2층)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

#### 2. schedules (복용 스케줄)
```sql
CREATE TABLE schedules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    medicine_id INT NOT NULL,
    time_of_day ENUM('morning', 'lunch', 'dinner', 'bedtime') NOT NULL,
    notification_time TIME NOT NULL,  -- 예: 08:00:00
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE CASCADE
);
```

#### 3. drug_interactions (DUR - 약물 상호작용)
```sql
CREATE TABLE drug_interactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    medicine_id_1 INT NOT NULL,
    medicine_id_2 INT NOT NULL,
    interaction_level ENUM('warning', 'danger') NOT NULL,
    description TEXT,
    FOREIGN KEY (medicine_id_1) REFERENCES medicines(id) ON DELETE CASCADE,
    FOREIGN KEY (medicine_id_2) REFERENCES medicines(id) ON DELETE CASCADE
);
```

#### 4. medication_logs (복용 기록)
```sql
CREATE TABLE medication_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    medicine_id INT NOT NULL,
    taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('taken', 'skipped') DEFAULT 'taken',
    FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE CASCADE
);
```

#### 5. user_settings (사용자 설정)
```sql
CREATE TABLE user_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    voice_preference VARCHAR(50) DEFAULT 'alloy',
    notification_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

---

## 모듈별 상세 설계

### 모듈 1: Wake Word 감지

**파일**: `wake_word_listener.py`

**기능**:
- Porcupine으로 Wake word 감지
- 감지 시 음성 처리 모듈 트리거

**주요 함수**:
```python
async def listen_for_wake_word():
    """
    Wake word를 계속 감지
    감지되면 음성 처리 모듈로 이벤트 전송
    """
    pass
```

---

### 모듈 2: 음성 처리 (GPT Real-time API)

**파일**: `voice_assistant.py`

**기능**:
- 사용자 음성 입력 → STT
- GPT Real-time API로 처리
- Function Calling으로 DB 접근
- 응답 생성 → TTS

**주요 함수**:
```python
async def start_voice_session():
    """
    GPT Real-time API 세션 시작
    WebSocket 연결 유지
    """
    pass

async def handle_user_speech(audio_data):
    """
    사용자 음성 처리
    1. STT
    2. LLM 처리
    3. Function Calling (필요시)
    4. TTS 응답
    """
    pass
```

**Function Calling 정의**:
```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_medicine_info",
            "description": "DB에서 약 정보 조회",
            "parameters": {
                "type": "object",
                "properties": {
                    "medicine_name": {"type": "string"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_drug_interaction",
            "description": "약물 상호작용 체크",
            "parameters": {
                "type": "object",
                "properties": {
                    "medicine_ids": {
                        "type": "array",
                        "items": {"type": "integer"}
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_medication_schedule",
            "description": "복용 스케줄 조회",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_of_day": {"type": "string"}
                }
            }
        }
    }
]
```

---

### 모듈 3: 이미지 처리 (약봉지 스캔)

**파일**: `image_processor.py`

**기능**:
- 카메라로 약봉지 촬영
- OCR + LLM으로 정보 추출
- DB 저장

**주요 함수**:
```python
async def capture_medicine_image():
    """
    Raspberry Pi Camera로 이미지 촬영
    """
    pass

async def extract_medicine_info(image_path):
    """
    이미지에서 약 정보 추출
    1. 이미지 전처리 (OpenCV)
    2. OCR (EasyOCR)
    3. LLM으로 정보 구조화
    """
    pass

async def save_medicine_to_db(medicine_info):
    """
    추출된 약 정보를 DB에 저장
    """
    pass
```

**이미지 처리 파이프라인**:
```
원본 이미지
→ 그레이스케일 변환
→ 노이즈 제거
→ 이진화 (Threshold)
→ OCR (EasyOCR)
→ 추출된 텍스트
→ LLM 구조화
→ JSON 형식 약 정보
```

---

### 모듈 4: 하드웨어 제어

**파일**: `hardware_controller.py`

**기능**:
- 모터 제어 (약봉투 삽입/분출)
- 거리센서 제어 (약 투입 감지)
- 카메라 제어 (절취선 인식)

**주요 함수**:
```python
async def activate_insertion_motor():
    """
    약봉투 삽입 모터 활성화
    """
    pass

async def monitor_distance_sensor():
    """
    거리센서로 약 투입 감지
    """
    pass

async def dispense_medicine(floor=1):
    """
    약 분출
    1. 해당 층 모터 활성화
    2. 절취선 인식 (OpenCV)
    3. 약 분출
    4. 비어있음 확인
    """
    pass

async def detect_perforation():
    """
    카메라로 절취선 감지 (OpenCV)
    """
    pass
```

**GPIO 핀 매핑** (예시):
```python
# GPIO 핀 번호는 실제 하드웨어 설계에 따라 변경
MOTOR_1_PIN = 17  # 1층 모터
MOTOR_2_PIN = 27  # 2층 모터
GRIPPER_PIN = 22  # 잡기 모터
DISTANCE_SENSOR_TRIG = 23
DISTANCE_SENSOR_ECHO = 24
```

---

### 모듈 5: 데이터베이스 관리

**파일**: `database.py`

**기능**:
- MySQL 연결 관리
- CRUD 작업

**주요 함수**:
```python
async def get_db_connection():
    """
    MySQL 연결 풀 관리
    """
    pass

async def get_medicine_by_name(name):
    """
    약 이름으로 조회
    """
    pass

async def check_drug_interactions(medicine_ids):
    """
    DUR 체크
    """
    pass

async def get_schedule_by_time(time_of_day):
    """
    복용 시간대별 스케줄 조회
    """
    pass

async def log_medication(medicine_id):
    """
    복용 기록 저장
    """
    pass
```

---

### 모듈 6: 스케줄러 (약 알림)

**파일**: `scheduler.py`

**기능**:
- 정해진 시간에 약 복용 알림

**주요 함수**:
```python
async def schedule_medication_reminders():
    """
    DB에서 스케줄 조회 후
    APScheduler에 작업 등록
    """
    pass

async def send_medication_reminder(medicine_name, time):
    """
    음성 알림 전송
    "{medicine_name}약 드셔야 합니다" (TTS)
    """
    pass
```

---

## 개발 단계

### Phase 1: 개발 환경 설정

**1.1 로컬 PC 환경**
```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 라이브러리 설치
pip install openai elevenlabs easyocr opencv-python
pip install mysql-connector-python python-dotenv
pip install apscheduler pvporcupine
```

**1.2 MySQL 설치 및 DB 생성**
```sql
CREATE DATABASE medicine_system;
USE medicine_system;
-- 위의 테이블 생성 SQL 실행
```

**1.3 환경 변수 설정** (`.env`)
```
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
PORCUPINE_API_KEY=your_porcupine_api_key

DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=medicine_system
```

---

### Phase 2: 핵심 모듈 개발

**우선순위 순서**:

1. **DB 모듈** (`database.py`)
   - 가장 기초가 되는 모듈
   - 다른 모듈들이 의존

2. **이미지 처리 모듈** (`image_processor.py`)
   - 약봉지 스캔 기능
   - OCR + LLM 통합

3. **음성 처리 모듈** (`voice_assistant.py`)
   - GPT Real-time API 통합
   - Function Calling 구현

4. **하드웨어 제어 모듈** (`hardware_controller.py`)
   - GPIO 제어
   - 모터, 센서 통합

5. **Wake Word 모듈** (`wake_word_listener.py`)
   - Porcupine 통합

6. **스케줄러 모듈** (`scheduler.py`)
   - 약 알림 기능

---

### Phase 3: 통합 및 테스트

**3.1 메인 프로그램 작성** (`main.py`)
```python
import asyncio
from wake_word_listener import listen_for_wake_word
from voice_assistant import start_voice_session
from hardware_controller import monitor_hardware
from scheduler import schedule_medication_reminders

async def main():
    """
    모든 모듈을 동시에 실행
    """
    await asyncio.gather(
        listen_for_wake_word(),
        start_voice_session(),
        monitor_hardware(),
        schedule_medication_reminders()
    )

if __name__ == "__main__":
    asyncio.run(main())
```

**3.2 유저 플로우별 테스트**
- 약봉지 스캔 → 저장 → 충돌 체크
- 음성 명령 → 약 분출
- 상태 확인 질문 → 응답
- 약 알림 → 음성 출력

---

### Phase 4: 라즈베리파이 배포

**4.1 라즈베리파이 OS 설치**
- Raspberry Pi OS (Bullseye 권장)

**4.2 라이브러리 설치**
```bash
# 라즈베리파이에서 실행
sudo apt-get update
sudo apt-get install python3-pip python3-opencv
sudo apt-get install libatlas-base-dev  # NumPy 의존성

pip3 install -r requirements.txt
```

**4.3 코드 전송**
```bash
# 로컬 PC에서
scp -r project/ pi@raspberrypi.local:/home/pi/medicine_system/
```

**4.4 하드웨어 연결**
- 카메라 모듈 연결
- GPIO 핀에 모터, 센서 연결
- 마이크, 스피커 연결

**4.5 자동 실행 설정**
```bash
# systemd 서비스 생성
sudo nano /etc/systemd/system/medicine_system.service
```

```ini
[Unit]
Description=Medicine Management System
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/medicine_system/main.py
WorkingDirectory=/home/pi/medicine_system
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable medicine_system
sudo systemctl start medicine_system
```

---

## 에러 처리

### 1. 네트워크 오류
```python
async def call_api_with_retry(api_call, max_retries=3):
    """
    API 호출 실패 시 재시도
    """
    for i in range(max_retries):
        try:
            return await api_call()
        except Exception as e:
            if i == max_retries - 1:
                # 최종 실패 시 음성 알림
                await play_error_message("네트워크 오류가 발생했습니다")
                raise
            await asyncio.sleep(2 ** i)  # 지수 백오프
```

### 2. DB 연결 오류
```python
async def get_db_connection_safe():
    """
    DB 연결 실패 시 재연결 시도
    """
    try:
        return await get_db_connection()
    except Exception as e:
        await play_error_message("데이터베이스 연결 오류")
        raise
```

### 3. 하드웨어 오류
```python
async def safe_motor_control(motor_func):
    """
    모터 제어 실패 시 안전 처리
    """
    try:
        await motor_func()
    except Exception as e:
        # 모터 즉시 정지
        await emergency_stop()
        await play_error_message("하드웨어 오류가 발생했습니다")
```

### 4. 이미지 처리 오류
```python
async def process_image_safe(image_path):
    """
    이미지 처리 실패 시 재촬영 요청
    """
    try:
        return await extract_medicine_info(image_path)
    except Exception as e:
        await play_error_message("이미지를 인식할 수 없습니다. 다시 촬영해주세요")
        return None
```

---

## 추가 고려사항

### 보안
- API 키는 환경 변수로 관리
- DB 접근은 읽기 전용 권한 권장
- 민감 정보 로깅 금지

### 성능 최적화
- 이미지 캐싱 (중복 스캔 방지)
- DB 쿼리 최적화 (인덱스 활용)
- 음성 데이터 압축

### 로깅
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('medicine_system.log'),
        logging.StreamHandler()
    ]
)
```

---

## 참고 문서

### API 문서
- [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime)
- [ElevenLabs API](https://elevenlabs.io/docs)
- [Porcupine Wake Word](https://picovoice.ai/docs/porcupine/)

### 라이브러리 문서
- [EasyOCR](https://github.com/JaidedAI/EasyOCR)
- [OpenCV](https://docs.opencv.org/)
- [RPi.GPIO](https://sourceforge.net/p/raspberry-gpio-python/wiki/Home/)

---

## 프로젝트 디렉토리 구조

```
medicine_system/
├── main.py                    # 메인 실행 파일
├── wake_word_listener.py      # Wake word 감지
├── voice_assistant.py         # 음성 처리 (GPT Real-time API)
├── image_processor.py         # 이미지 처리 (OCR + LLM)
├── hardware_controller.py     # 하드웨어 제어
├── database.py                # DB 관리
├── scheduler.py               # 약 알림 스케줄러
├── config.py                  # 설정 관리
├── utils.py                   # 유틸리티 함수
├── requirements.txt           # 의존성 목록
├── .env                       # 환경 변수 (git ignore)
├── .gitignore
├── README.md
└── plan.md                    # 이 문서
```

---

## 다음 액션 아이템

### 즉시 시작
1. (완료) plan.md 작성 완료
2. (대기) 기존 팀원 코드 리뷰
3. (대기) DB 스키마 생성
4. (대기) 개발 환경 설정

### 개발 순서 (소프트웨어 우선)
1. DB 모듈
2. 이미지 처리 모듈
3. 음성 처리 모듈
4. (향후) 하드웨어 제어 모듈
5. 통합 및 테스트

---

## 버전 히스토리
- v1.0 (2025-10-18): 초안 작성