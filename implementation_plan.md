# CarePill 실행 계획서 (Implementation Plan)

## 문서 정보
- 작성일: 2025-10-22
- 수정일: 2025-10-22
- 기준 코드: carepill 저장소 (Django 웹 애플리케이션, 팀원 작성)
- 참조 문서: plan.md (Raspberry Pi 시스템 설계)
- 개발 전략: Django 우선 완성 후 Raspberry Pi 이식

---

## 프로젝트 방향성 결정

### 확정된 개발 전략
1. Phase 1: Django 웹 애플리케이션 완성 (최우선)
2. Phase 2: Raspberry Pi 하드웨어 통합 (Django 완성 후)
3. 데이터베이스: SQLite 유지 (경량화)
4. 팀 협업: 기존 팀원 코드 최대한 활용

### 최우선 과제 (즉시 착수)
1. 약봉투 인식 기능 개선 및 DB 연동
2. ElevenLabs TTS API 통합 (음성 출력)

---

## 현황 분석

### 기존 구현 현황 (팀원 작성 코드)
- Django 5.0 기반 웹 애플리케이션
- OpenAI GPT-4o Realtime API 연동 완료
- WebRTC 기반 실시간 음성 채팅 구현
- Vision API 기반 약봉투 멀티카메라 스캐닝
- 대화 요약 및 저장 기능

### 즉시 개선 필요 영역
1. 약봉투 스캔 결과를 DB에 저장 (현재: JSON만 반환)
2. ElevenLabs TTS 통합 (현재: OpenAI TTS만 사용)
3. 데이터베이스 모델 구현 (models.py 비어있음)

### 차순위 개발 영역
- 약물 상호작용(DUR) 체크
- 복용 스케줄 및 알림
- 약물 정보 관리 시스템

### 보류 항목
- 사용자 인증 시스템 (나중에)
- 테스트 코드 (시간 여유 시)
- OpenAI SDK 업그레이드 (안정성 우선)

---

## 아키텍처 결정 사항

### 확정: Django 웹 애플리케이션 우선 개발
**선택 이유**:
- 기존 팀원 코드 활용 (WebRTC, Vision API 이미 구현)
- 빠른 개발 속도 필요
- 팀 협업 효율성
- 웹 인터페이스로 다양한 디바이스 지원

**향후 계획**:
- Django 완성 후 Raspberry Pi 클라이언트 개발
- Django API를 백엔드로 활용
- 하드웨어 센서는 소프트웨어 완성 후 통합

---

## 개발 로드맵 (우선순위 재정렬)

### Sprint 1: 약봉투 인식 및 DB 저장 (최우선, 2-3일)

**목표**: 스캔한 약 정보를 데이터베이스에 저장하고 관리

**Day 1: DB 모델 구현**
1. Django models.py 구현
   ```python
   class Medicine(models.Model):
       name = models.CharField(max_length=255)  # 약 이름
       patient_name = models.CharField(max_length=100, blank=True)  # 환자명
       age = models.IntegerField(null=True, blank=True)  # 나이
       pharmacy = models.CharField(max_length=255, blank=True)  # 약국
       dosage = models.CharField(max_length=100, blank=True)  # 용량
       usage_instructions = models.TextField(blank=True)  # 복용법
       precautions = models.TextField(blank=True)  # 주의사항
       image = models.ImageField(upload_to='medicines/', blank=True)  # 스캔 이미지
       scanned_at = models.DateTimeField(auto_now_add=True)  # 스캔 일시
   ```

2. Migration 실행
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

3. Django Admin 등록
   ```python
   # admin.py
   @admin.register(Medicine)
   class MedicineAdmin(admin.ModelAdmin):
       list_display = ['name', 'patient_name', 'pharmacy', 'scanned_at']
       search_fields = ['name', 'patient_name']
   ```

**Day 2: 스캔 API 개선**
1. `views.py:api_scan_envelope` 수정
   - 현재: Vision API 응답 → JSON 반환만
   - 개선: Vision API 응답 → Medicine 객체 생성 → DB 저장

2. 이미지 파일 저장
   - request.FILES에서 이미지 추출
   - MEDIA_ROOT에 저장
   - Medicine.image 필드에 연결

3. 응답 형식 개선
   ```json
   {
       "success": true,
       "medicine_id": 123,
       "data": {
           "name": "타이레놀정",
           "patient_name": "홍길동",
           "pharmacy": "서울약국"
       }
   }
   ```

**Day 3: UI 연동**
1. scan.html 개선
   - 스캔 성공 시 약 정보 표시
   - "내 약 목록에 추가됨" 안내

2. meds.html 실제 구현
   - 현재: 정적 데모
   - 개선: DB에서 Medicine 목록 조회
   - 약 상세 정보 표시

**예상 소요 시간**: 2-3일

**산출물**:
- `carepill/models.py` (Medicine 모델)
- `carepill/views.py` (api_scan_envelope 개선)
- `carepill/templates/meds.html` (실제 DB 연동)
- Migration 파일

---

### Sprint 2: ElevenLabs TTS 통합 (최우선, 1-2일)

**목표**: 음성 출력을 ElevenLabs API로 개선

**Day 1: ElevenLabs API 연동**
1. 라이브러리 설치
   ```bash
   pip install elevenlabs
   ```

2. API 키 설정 (.env)
   ```
   ELEVENLABS_API_KEY=your_api_key_here
   ```

3. TTS 함수 작성
   ```python
   # carepill/services/tts_service.py (신규)
   from elevenlabs import generate, set_api_key
   import os

   set_api_key(os.getenv('ELEVENLABS_API_KEY'))

   def text_to_speech(text, voice="alloy"):
       audio = generate(
           text=text,
           voice=voice,
           model="eleven_multilingual_v2"
       )
       return audio
   ```

**Day 2: API 엔드포인트 추가**
1. TTS API 엔드포인트 작성
   ```python
   # views.py
   @csrf_exempt
   def api_text_to_speech(request):
       text = request.POST.get('text')
       audio = text_to_speech(text)
       return HttpResponse(audio, content_type='audio/mpeg')
   ```

2. URL 추가
   ```python
   # urls.py
   path("api/tts/", views.api_text_to_speech),
   ```

3. 프론트엔드 연동
   - voice.html에서 ElevenLabs TTS 호출
   - 약 스캔 성공 시 음성 안내
   - 약 목록 읽어주기 기능

**예상 소요 시간**: 1-2일

**산출물**:
- `carepill/services/tts_service.py` (신규)
- `carepill/views.py` (api_text_to_speech 추가)
- `.env` (ELEVENLABS_API_KEY 추가)

---

### Sprint 3: 약물 상호작용(DUR) 체크 (2일)

**목표**: 약물 충돌 검사 및 경고 시스템

**작업 항목**:
1. DrugInteraction 모델 추가
   ```python
   class DrugInteraction(models.Model):
       medicine_1 = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='interactions_1')
       medicine_2 = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='interactions_2')
       level = models.CharField(max_length=20, choices=[('warning', '주의'), ('danger', '위험')])
       description = models.TextField()
   ```

2. DUR 체크 로직
   ```python
   def check_drug_interactions(medicine_name):
       current_medicines = Medicine.objects.all()
       interactions = []
       for med in current_medicines:
           # LLM으로 약물 상호작용 확인
           result = ask_gpt_interaction(medicine_name, med.name)
           if result['has_interaction']:
               interactions.append(result)
       return interactions
   ```

3. 스캔 시 자동 DUR 체크
   - 약 스캔 후 즉시 기존 약들과 충돌 검사
   - 경고 음성 출력 (ElevenLabs)
   - UI에 경고 표시

**예상 소요 시간**: 2일

---

### Sprint 4: 복용 스케줄 및 알림 (2-3일)

**목표**: 약 복용 시간 관리 및 알림 기능

**작업 항목**:
1. MedicationSchedule 모델 추가
   ```python
   class MedicationSchedule(models.Model):
       medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE)
       time_of_day = models.CharField(max_length=20, choices=[
           ('morning', '아침'), ('lunch', '점심'),
           ('dinner', '저녁'), ('bedtime', '취침 전')
       ])
       notification_time = models.TimeField()
       is_active = models.BooleanField(default=True)
   ```

2. 알림 시스템 구현 (APScheduler 사용 - 간단)
   ```python
   from apscheduler.schedulers.background import BackgroundScheduler

   def send_medication_reminder(medicine_name):
       text = f"{medicine_name} 드실 시간입니다"
       audio = text_to_speech(text)  # ElevenLabs
       # 음성 재생 또는 알림 전송
   ```

3. 스케줄 관리 UI
   - schedules.html 작성
   - 약별 복용 시간 설정
   - 알림 ON/OFF 토글

**예상 소요 시간**: 2-3일

---

### Sprint 5: 음성 인터페이스 Function Calling (2일)

**목표**: 음성으로 DB 정보 조회

**작업 항목**:
1. GPT Function Calling 정의
   ```python
   tools = [
       {
           "type": "function",
           "function": {
               "name": "get_my_medicines",
               "description": "내가 복용 중인 약 목록 조회"
           }
       },
       {
           "type": "function",
           "function": {
               "name": "get_medicine_info",
               "description": "특정 약의 상세 정보 조회",
               "parameters": {
                   "type": "object",
                   "properties": {
                       "medicine_name": {"type": "string"}
                   }
               }
           }
       }
   ]
   ```

2. Function 실행 로직
   - `views.py`에 Function handler 추가
   - DB 쿼리 실행
   - 결과를 GPT에 반환

3. Realtime API 세션 업데이트
   - `issue_ephemeral`에서 tools 전달
   - Function calling 활성화

**예상 소요 시간**: 2일

---

### Sprint 6: 프로덕션 준비 및 최적화 (선택 사항)

**목표**: 배포 가능한 상태로 개선

**작업 항목**:
1. 보안 설정
   - DEBUG = False
   - SECRET_KEY 환경 변수화
   - ALLOWED_HOSTS 설정

2. 에러 처리
   - API 에러 응답 표준화
   - 로깅 설정
   - 사용자 친화적 에러 메시지

3. UI/UX 개선
   - 로딩 인디케이터
   - 에러 알림
   - 성공 토스트 메시지

**예상 소요 시간**: 2-3일 (시간 여유 시)

---

### Sprint 7: Raspberry Pi 통합 (Django 완성 후)

**목표**: 물리적 디바이스로 이식

**작업 항목**:
1. Django REST API 확장
   - GET /api/medicines/ (약 목록)
   - GET /api/schedules/today/ (오늘의 복용 약)
   - POST /api/scan/envelope/ (이미 구현)

2. Raspberry Pi 클라이언트 개발
   - Python 클라이언트 작성
   - Wake Word 감지 (Porcupine)
   - Django API 호출
   - ElevenLabs TTS 재생

3. 하드웨어 센서 연결
   - GPIO 제어 (모터, 센서)
   - 카메라 모듈
   - 스피커/마이크

**예상 소요 시간**: 5-7일 (Django 완성 후)

---

## 우선순위별 작업 순서

### 즉시 시작 (이번 주 완료 목표)
1. **Sprint 1**: 약봉투 인식 및 DB 저장 (2-3일) - 최우선
2. **Sprint 2**: ElevenLabs TTS 통합 (1-2일) - 최우선

### 다음 주 목표
3. **Sprint 3**: 약물 상호작용(DUR) 체크 (2일)
4. **Sprint 4**: 복용 스케줄 및 알림 (2-3일)
5. **Sprint 5**: 음성 인터페이스 Function Calling (2일)

### 시간 여유 시
6. **Sprint 6**: 프로덕션 준비 및 최적화 (2-3일)

### Django 완성 후
7. **Sprint 7**: Raspberry Pi 통합 (5-7일)

---

## 기술 스택 최종 결정

### 백엔드
- **Framework**: Django 5.0 (기존 유지)
- **Database**: SQLite (개발 및 프로덕션 - 경량화 전략)
- **Task Queue**: APScheduler (알림, 간단한 방식)
- **API**: Django 기본 views (REST Framework는 필요 시)

### 프론트엔드
- **현재**: Vanilla JavaScript + WebRTC (기존 유지)
- **개선**: 불필요한 리팩토링 지양, 기능 우선

### AI/ML
- **OpenAI**: GPT-4o Realtime API, Vision API (기존 유지)
- **ElevenLabs**: TTS (음성 출력) - 신규 추가
- **SDK**: v2.3.0 유지 (안정성 우선, 업그레이드 보류)

### 배포
- **Development**: Django runserver
- **Production**: 추후 결정 (일단 개발 완성 우선)

---

## 코드 구조 제안

### 현재 구조 (팀원 작성, 유지)
```
carepill/
├── carepill/
│   ├── models.py          (비어있음 - 구현 필요)
│   ├── views.py           (605줄 - 기능 추가)
│   ├── urls.py            (경로 추가)
│   ├── static/
│   └── templates/
└── config/
```

### 최소한의 추가 구조 (필수만)
```
carepill/
├── carepill/
│   ├── models.py              (Medicine, DrugInteraction, Schedule 추가)
│   ├── views.py               (TTS API, 개선된 스캔 API 추가)
│   ├── urls.py                (신규 경로 추가)
│   ├── services/              (신규 디렉토리)
│   │   ├── __init__.py
│   │   └── tts_service.py    (ElevenLabs TTS 로직)
│   ├── static/
│   └── templates/
│       └── schedules.html    (신규 템플릿)
└── config/
```

**변경 최소화 원칙**:
- 기존 팀원 코드 최대한 유지
- services/ 디렉토리만 신규 추가
- views.py는 기능만 추가 (리팩토링 지양)
- 테스트 코드는 시간 여유 시

---

## 데이터베이스 스키마 (최종안)

### 1. Medicine (약 정보)
```python
class Medicine(models.Model):
    name = models.CharField(max_length=255)
    manufacturer = models.CharField(max_length=255, blank=True)
    ingredients = models.TextField(blank=True)
    dosage = models.CharField(max_length=100, blank=True)
    usage_instructions = models.TextField(blank=True)
    precautions = models.TextField(blank=True)
    image = models.ImageField(upload_to='medicines/', blank=True)
    floor = models.IntegerField(default=1)  # 1층 또는 2층 (Raspberry Pi용)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### 2. MedicationSchedule (복용 스케줄)
```python
class MedicationSchedule(models.Model):
    TIME_OF_DAY_CHOICES = [
        ('morning', '아침'),
        ('lunch', '점심'),
        ('dinner', '저녁'),
        ('bedtime', '취침 전'),
    ]

    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE)
    time_of_day = models.CharField(max_length=20, choices=TIME_OF_DAY_CHOICES)
    notification_time = models.TimeField()
    is_active = models.BooleanField(default=True)
```

### 3. DrugInteraction (약물 상호작용)
```python
class DrugInteraction(models.Model):
    LEVEL_CHOICES = [
        ('warning', '주의'),
        ('danger', '위험'),
    ]

    medicine_1 = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='interactions_1')
    medicine_2 = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='interactions_2')
    interaction_level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    description = models.TextField()
```

### 4. MedicationLog (복용 기록)
```python
class MedicationLog(models.Model):
    STATUS_CHOICES = [
        ('taken', '복용'),
        ('skipped', '건너뜀'),
    ]

    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE)
    taken_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='taken')
```

### 5. UserProfile (사용자 설정)
```python
class UserProfile(models.Model):
    voice_preference = models.CharField(max_length=50, default='alloy')
    notification_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

---

## API 엔드포인트 설계

### 기존 엔드포인트
```
GET  /                              → home
GET  /scan/                         → scan page
GET  /meds/                         → medications list
GET  /voice/                        → voice chat
POST /api/scan/envelope/            → scan medicine
POST /api/realtime/session/         → OpenAI session token
POST /api/realtime/sdp-exchange/    → WebRTC SDP
POST /api/conversation/summarize_and_save/
GET  /api/conversation/download/
```

### 추가 필요 엔드포인트
```
# Medicine API
GET    /api/medicines/              → 약 목록
GET    /api/medicines/{id}/         → 약 상세 정보
POST   /api/medicines/{id}/check-interaction/  → DUR 체크

# Schedule API
GET    /api/schedules/              → 스케줄 목록
POST   /api/schedules/              → 스케줄 생성
PUT    /api/schedules/{id}/         → 스케줄 수정
DELETE /api/schedules/{id}/         → 스케줄 삭제
GET    /api/schedules/today/        → 오늘의 복용 약

# Medication Log API
POST   /api/logs/                   → 복용 기록 생성
GET    /api/logs/                   → 복용 기록 조회
GET    /api/logs/stats/             → 복용 통계

# Raspberry Pi Client API
POST   /api/rpi/dispense/           → 약 분출 요청
GET    /api/rpi/status/             → 디바이스 상태
```

---

## 개발 환경 설정

### 1. 가상환경 설정
```bash
cd C:\Users\woo\Desktop\carepill_lyj\carepill
python -m venv venv
venv\Scripts\activate  # Windows
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정 (.env)
```env
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# OpenAI
OPENAI_API_KEY=sk-...

# Database (개발)
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3

# Database (프로덕션)
# DB_ENGINE=django.db.backends.postgresql
# DB_NAME=carepill
# DB_USER=postgres
# DB_PASSWORD=your_password
# DB_HOST=localhost
# DB_PORT=5432
```

### 4. 데이터베이스 초기화
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

### 5. 개발 서버 실행
```bash
python manage.py runserver
```

---

## 테스트 전략

### Unit Tests
```python
# carepill/tests/test_models.py
from django.test import TestCase
from carepill.models import Medicine, DrugInteraction

class MedicineModelTest(TestCase):
    def test_create_medicine(self):
        medicine = Medicine.objects.create(
            name="타이레놀",
            manufacturer="한국얀센"
        )
        self.assertEqual(medicine.name, "타이레놀")
```

### API Tests
```python
# carepill/tests/test_api.py
from django.test import TestCase, Client
from django.urls import reverse

class ScanAPITest(TestCase):
    def test_scan_envelope(self):
        client = Client()
        response = client.post('/api/scan/envelope/', {
            # test data
        })
        self.assertEqual(response.status_code, 200)
```

---

## 에러 처리 및 로깅

### 로깅 설정 (settings.py)
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'carepill.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}
```

### API 에러 응답 표준화
```python
# utils.py
from django.http import JsonResponse

def error_response(message, status=400):
    return JsonResponse({
        'success': False,
        'error': message
    }, status=status)

def success_response(data):
    return JsonResponse({
        'success': True,
        'data': data
    })
```

---

## 보안 체크리스트

- [ ] SECRET_KEY 환경 변수화
- [ ] DEBUG=False (프로덕션)
- [ ] ALLOWED_HOSTS 설정
- [ ] CSRF 보호 활성화
- [ ] SQL Injection 방지 (ORM 사용)
- [ ] XSS 방지 (템플릿 이스케이핑)
- [ ] HTTPS 강제 (프로덕션)
- [ ] API Rate Limiting
- [ ] 민감 정보 로깅 금지
- [ ] 의존성 취약점 스캔 (`pip-audit`)

---

## 다음 액션 아이템 (바로 시작 가능)

### 즉시 시작: Sprint 1 (약봉투 인식 및 DB 저장)

**Step 1: DB 모델 구현 (30분-1시간)**
```bash
# 1. models.py에 Medicine 클래스 작성
# 2. python manage.py makemigrations
# 3. python manage.py migrate
# 4. admin.py에 Medicine 등록
# 5. python manage.py createsuperuser (admin 계정 생성)
```

**Step 2: 스캔 API 개선 (1-2시간)**
```bash
# 1. views.py의 api_scan_envelope 함수 수정
# 2. Vision API 응답 → Medicine 객체 생성
# 3. 이미지 파일 저장 로직 추가
# 4. 테스트: 약봉투 스캔 후 DB 확인
```

**Step 3: UI 연동 (1-2시간)**
```bash
# 1. scan.html 성공 메시지 개선
# 2. meds.html DB 연동 (현재는 정적)
# 3. 약 목록 페이지 구현
```

### 다음: Sprint 2 (ElevenLabs TTS)

**Step 4: ElevenLabs API 연동 (1-2시간)**
```bash
# 1. pip install elevenlabs
# 2. .env에 ELEVENLABS_API_KEY 추가
# 3. services/tts_service.py 작성
# 4. views.py에 api_text_to_speech 추가
```

### 팀 협업 제안
- **역할 분담**: DB/API는 함께, Frontend는 분담 가능
- **일정**: Sprint 1+2를 이번 주 내 완료 목표
- **소통**: 매일 진행 상황 공유 (Stand-up)

---

## 참고 자료

### Django
- [Django 공식 문서](https://docs.djangoproject.com/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [Django Celery](https://docs.celeryproject.org/en/stable/django/)

### OpenAI
- [Realtime API 문서](https://platform.openai.com/docs/guides/realtime)
- [Function Calling 가이드](https://platform.openai.com/docs/guides/function-calling)

### 의약품 정보
- [식약처 공개 API](https://www.data.go.kr/)
- [의약품안전나라](https://nedrug.mfds.go.kr/)

### Raspberry Pi
- [picamera2 문서](https://github.com/raspberrypi/picamera2)
- [RPi.GPIO 가이드](https://sourceforge.net/p/raspberry-gpio-python/wiki/Home/)

---

---

## 요약: 이번 주 목표

### 최우선 과제 (Must Have)
1. 약봉투 스캔 → DB 저장 (Sprint 1)
2. ElevenLabs TTS 통합 (Sprint 2)

### 핵심 산출물
- Medicine 모델 (DB)
- 개선된 스캔 API
- 약 목록 페이지
- TTS 음성 출력 기능

### 성공 기준
- 약 스캔 후 DB에 저장 확인
- 약 목록 페이지에서 스캔한 약 조회
- 음성으로 약 정보 안내

### 개발 시간 추정
- Sprint 1: 2-3일
- Sprint 2: 1-2일
- **총 3-5일 소요 예상**

---

## 버전 히스토리
- v1.0 (2025-10-22): 초안 작성 (기존 코드 분석 기반)
- v1.1 (2025-10-22): 우선순위 재정렬 (약봉투 인식 + ElevenLabs 최우선)
  - Django 우선 개발 확정
  - SQLite 유지 결정
  - 팀 협업 고려사항 반영
