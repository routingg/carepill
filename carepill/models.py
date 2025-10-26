from django.db import models
from django.contrib.auth.models import User


class Medicine(models.Model):
    """약물 정보 (식약처 데이터)"""
    item_seq = models.AutoField(primary_key=True)
    item_name = models.CharField(max_length=500, verbose_name="약 이름")
    item_name_eng = models.CharField(max_length=500, blank=True, null=True, verbose_name="영문명")
    entp_name = models.CharField(max_length=300, verbose_name="제조회사")
    effect = models.TextField(blank=True, null=True, verbose_name="효능/효과")
    usage = models.TextField(blank=True, null=True, verbose_name="사용법")
    warning_critical = models.TextField(blank=True, null=True, verbose_name="중요 경고")
    warning_general = models.TextField(blank=True, null=True, verbose_name="일반 경고")
    interaction = models.TextField(blank=True, null=True, verbose_name="상호작용")
    side_effect = models.TextField(blank=True, null=True, verbose_name="부작용")
    storage = models.TextField(blank=True, null=True, verbose_name="보관법")
    main_ingredient = models.TextField(blank=True, null=True, verbose_name="주성분")
    ingredient_count = models.IntegerField(blank=True, null=True, verbose_name="성분 개수")
    class_type = models.CharField(max_length=100, blank=True, null=True, verbose_name="분류")
    product_type = models.CharField(max_length=100, blank=True, null=True, verbose_name="제품 타입")
    edi_code = models.CharField(max_length=50, blank=True, null=True, verbose_name="EDI 코드")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'medicines'
        verbose_name = "약물 정보"
        verbose_name_plural = "약물 정보"

    def __str__(self):
        return self.item_name


class UserMedication(models.Model):
    """사용자 복용 중인 약"""
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, verbose_name="약물")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="사용자")
    dosage = models.CharField(max_length=100, blank=True, null=True, verbose_name="복용량")
    frequency = models.CharField(max_length=100, blank=True, null=True, verbose_name="복용 횟수")
    days = models.CharField(max_length=50, blank=True, null=True, verbose_name="복용 일수")
    prescription_date = models.DateField(blank=True, null=True, verbose_name="처방일")
    start_date = models.DateField(verbose_name="시작일")
    pharmacy_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="약국명")
    hospital_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="병원명")
    is_completed = models.BooleanField(default=False, verbose_name="복용 완료")

    class Meta:
        managed = False
        db_table = 'user_medications'
        verbose_name = "사용자 복용 약"
        verbose_name_plural = "사용자 복용 약"

    def __str__(self):
        return f"{self.user.username} - {self.medicine.item_name}"


class PillIdentification(models.Model):
    """알약 식별 정보"""
    medicine = models.OneToOneField(Medicine, on_delete=models.CASCADE, primary_key=True)
    image_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="이미지 URL")
    shape = models.CharField(max_length=100, blank=True, null=True, verbose_name="모양")
    color_front = models.CharField(max_length=100, blank=True, null=True, verbose_name="앞면 색상")
    color_back = models.CharField(max_length=100, blank=True, null=True, verbose_name="뒷면 색상")
    print_front = models.CharField(max_length=200, blank=True, null=True, verbose_name="앞면 각인")
    print_back = models.CharField(max_length=200, blank=True, null=True, verbose_name="뒷면 각인")
    length_long = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True, verbose_name="장축 길이")
    length_short = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True, verbose_name="단축 길이")
    thickness = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True, verbose_name="두께")
    line_front = models.CharField(max_length=100, blank=True, null=True, verbose_name="앞면 분할선")
    line_back = models.CharField(max_length=100, blank=True, null=True, verbose_name="뒷면 분할선")
    shape_code = models.IntegerField(blank=True, null=True, verbose_name="모양 코드")

    class Meta:
        managed = False
        db_table = 'pill_identification'
        verbose_name = "알약 식별 정보"
        verbose_name_plural = "알약 식별 정보"

    def __str__(self):
        return f"{self.medicine.item_name} 식별정보"


class VoiceTTSCache(models.Model):
    """TTS 캐싱"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="사용자")
    text = models.TextField(verbose_name="텍스트")
    text_hash = models.CharField(max_length=64, verbose_name="텍스트 해시")
    audio_file = models.CharField(max_length=100, verbose_name="오디오 파일")
    duration_seconds = models.FloatField(blank=True, null=True, verbose_name="재생 시간")
    created_at = models.DateTimeField(auto_now_add=True)
    accessed_at = models.DateTimeField(auto_now=True)
    access_count = models.IntegerField(default=0, verbose_name="접근 횟수")

    class Meta:
        managed = False
        db_table = 'voice_tts_cache'
        unique_together = (('user', 'text_hash'),)
        verbose_name = "TTS 캐시"
        verbose_name_plural = "TTS 캐시"

    def __str__(self):
        return f"{self.user.username} - {self.text[:30]}"


class VoiceUserVoice(models.Model):
    """사용자 음성 샘플 (ElevenLabs Voice Cloning용)"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="사용자")
    voice_file = models.CharField(max_length=100, verbose_name="음성 파일")
    voice_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="ElevenLabs Voice ID")
    duration_seconds = models.FloatField(blank=True, null=True, verbose_name="재생 시간")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, verbose_name="활성화")

    class Meta:
        managed = False
        db_table = 'voice_user_voice'
        verbose_name = "사용자 음성"
        verbose_name_plural = "사용자 음성"

    def __str__(self):
        return f"{self.user.username}의 음성"


class AccessibilityInfo(models.Model):
    """접근성 정보"""
    medicine = models.OneToOneField(Medicine, on_delete=models.CASCADE, primary_key=True)
    video_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="영상 URL")
    has_audio = models.BooleanField(default=False, verbose_name="음성 지원")
    has_sign_language = models.BooleanField(default=False, verbose_name="수어 지원")
    effect_tts = models.TextField(blank=True, null=True, verbose_name="효능 TTS")
    usage_tts = models.TextField(blank=True, null=True, verbose_name="사용법 TTS")
    warning_tts = models.TextField(blank=True, null=True, verbose_name="경고 TTS")
    barcode = models.CharField(max_length=100, blank=True, null=True, verbose_name="바코드")
    std_code = models.CharField(max_length=100, blank=True, null=True, verbose_name="표준 코드")

    class Meta:
        managed = False
        db_table = 'accessibility_info'
        verbose_name = "접근성 정보"
        verbose_name_plural = "접근성 정보"

    def __str__(self):
        return f"{self.medicine.item_name} 접근성"


class OCRImage(models.Model):
    """약봉투 OCR 이미지"""
    image = models.CharField(max_length=100, verbose_name="이미지")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    ocr_result = models.TextField(blank=True, null=True, verbose_name="OCR 결과")
    extracted_medicine_names = models.TextField(blank=True, null=True, verbose_name="추출된 약 이름")

    class Meta:
        managed = False
        db_table = 'ocr_ocrimage'
        verbose_name = "OCR 이미지"
        verbose_name_plural = "OCR 이미지"

    def __str__(self):
        return f"OCR {self.id}"
