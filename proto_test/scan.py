import os
import cv2
import time
import base64
import json
import argparse
from pathlib import Path
from decouple import config

# openai 라이브러리: 사용자가 주신 코드 스타일과 동일하게 유지
import openai

# -----------------------------
# OpenAI 클라이언트 유틸
# -----------------------------
def get_openai_client():
    api_key = config('OPENAI_API_KEY', default=None)
    if not api_key or api_key == 'your-openai-api-key-here':
        raise RuntimeError("OPENAI_API_KEY가 .env에 설정되지 않았습니다.")
    try:
        return openai.OpenAI(api_key=api_key)
    except Exception as e:
        raise RuntimeError(f"OpenAI 클라이언트 초기화 실패: {e}")

def strip_code_fence(text: str) -> str:
    if not isinstance(text, str):
        return text
    t = text.strip()
    if t.startswith("```"):
        # ```json ... ```
        if t.startswith("```json"):
            t = t[len("```json"):].strip()
        elif t.startswith("```JSON"):
            t = t[len("```JSON"):].strip()
        else:
            t = t[3:].strip()
        if t.endswith("```"):
            t = t[:-3].strip()
    return t

def call_openai_with_image_b64(image_b64: str, analysis_type: str, model: str = "gpt-4o-mini") -> str:
    """
    analysis_type: envelope | schedule | appearance
    반환: 모델의 원문 응답 문자열(가능하면 JSON)
    """
    if analysis_type == "envelope":
        text_prompt = (
            "이 약봉투 이미지를 분석해서 다음 정보를 JSON 형태로 추출해주세요:\n"
            "{\n"
            '  "medicine_name": "약품명",\n'
            '  "dosage_instructions": "복용법",\n'
            '  "frequency": "복용횟수",\n'
            '  "prescription_number": "처방전 번호"\n'
            "}\n\n정확한 JSON 형태로만 응답해주세요. 한국어로 답변해주세요."
        )
    elif analysis_type == "schedule":
        text_prompt = (
            "이 약물 복용 스케줄 이미지를 분석해서 JSON 형태로 추출해주세요:\n"
            "{\n"
            '  "morning": "아침 복용 정보",\n'
            '  "lunch": "점심 복용 정보",\n'
            '  "evening": "저녁 복용 정보",\n'
            '  "meal_timing": "식전/식후 여부"\n'
            "}\n\n정확한 JSON 형태로만 응답해주세요. 한국어로 답변해주세요."
        )
    elif analysis_type == "appearance":
        text_prompt = (
            "이 약물 이미지를 분석해서 JSON 형태로 추출해주세요:\n"
            "{\n"
            '  "shape": "약물 형태 (정제, 캡슐, 시럽 등)",\n'
            '  "color": "색상",\n'
            '  "size": "크기",\n'
            '  "marking": "각인 정보",\n'
            '  "estimated_name": "추정 약물명",\n'
            '  "warnings": "주의사항"\n'
            "}\n\n정확한 JSON 형태로만 응답해주세요. 한국 의약품 기준으로 분석하고, 한국어로 답변해주세요."
        )
    else:
        raise ValueError("analysis_type은 envelope|schedule|appearance 중 하나여야 합니다.")

    client = get_openai_client()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "너는 한국 의약품 라벨/약봉투 OCR 도우미다. JSON만 출력한다."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=800,
            temperature=0.1
        )
        return response.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"OpenAI API 호출 실패: {e}")

# -----------------------------
# 카메라 캡처 유틸
# -----------------------------
def capture_single_frame(camera_index: int = 0,
                         width: int = 1920,
                         height: int = 1080,
                         warmup_frames: int = 5,
                         timeout_sec: float = 5.0) -> "cv2.Mat":
    """
    USB 카메라에서 프레임 1장을 반환.
    Windows에선 CAP_DSHOW 백엔드가 안정적임.
    """
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    start = time.time()
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"카메라(index={camera_index})를 열 수 없습니다.")

    # 기본 속성
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  float(width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    # 워밍업
    for _ in range(warmup_frames):
        ok, _ = cap.read()
        if not ok and (time.time() - start) > timeout_sec:
            cap.release()
            raise RuntimeError("카메라 워밍업 중 프레임 획득 실패")

    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("카메라 프레임 획득 실패")
    return frame

def interactive_capture(camera_index: int = 0,
                        width: int = 1280,
                        height: int = 720,
                        window_name: str = "Press SPACE to capture, ESC to exit") -> "cv2.Mat":
    """
    라이브 미預览 창을 띄우고 SPACE로 캡처.
    ESC 누르면 종료(예외 raise).
    """
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"카메라(index={camera_index})를 열 수 없습니다.")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  float(width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, width, height)

    frame_to_return = None
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                raise RuntimeError("사용자 취소")
            if key == 32:  # SPACE
                frame_to_return = frame.copy()
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if frame_to_return is None:
        raise RuntimeError("캡처 프레임이 없습니다.")
    return frame_to_return

# -----------------------------
# 이미지 → Base64 (JPEG)
# -----------------------------
def encode_frame_to_b64_jpeg(frame, jpeg_quality: int = 95) -> str:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok or buf is None:
        raise RuntimeError("프레임 JPEG 인코딩 실패")
    return base64.b64encode(buf.tobytes()).decode("utf-8")

# -----------------------------
# 메인 로직
# -----------------------------
def parse_args():
    p = argparse.ArgumentParser(description="USB 카메라로 촬영 후 OpenAI로 약 정보 분석")
    p.add_argument("--analysis", required=True, choices=["envelope", "schedule", "appearance"],
                   help="분석 타입 선택")
    p.add_argument("--camera-index", type=int, default=0, help="카메라 인덱스 (기본 0)")
    p.add_argument("--interactive", action="store_true", help="라이브 미预览 모드(스페이스바로 캡처)")
    p.add_argument("--save-dir", default="captures", help="촬영 이미지 저장 폴더 (옵션)")
    p.add_argument("--no-save", action="store_true", help="촬영 이미지 저장하지 않음")
    p.add_argument("--output", default=None, help="분석 결과(JSON) 저장 파일 경로")
    return p.parse_args()

def main():
    args = parse_args()

    # 1) 촬영
    if args.interactive:
        frame = interactive_capture(camera_index=args.camera_index)
    else:
        frame = capture_single_frame(camera_index=args.camera_index)

    # 2) 저장(옵션)
    image_path = None
    if not args.no_save:
        Path(args.save_dir).mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        image_path = str(Path(args.save_dir) / f"capture_{ts}.jpg")
        ok = cv2.imwrite(image_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not ok:
            print("경고: 촬영 이미지를 파일로 저장하지 못했습니다.")

    # 3) Base64 인코딩
    image_b64 = encode_frame_to_b64_jpeg(frame)

    # 4) OpenAI 호출
    raw = call_openai_with_image_b64(image_b64, analysis_type=args.analysis)

    # 5) JSON 파싱 시도
    cleaned = strip_code_fence(raw)
    parsed = None
    try:
        parsed = json.loads(cleaned)
    except Exception:
        pass

    # 6) 출력
    if parsed is not None:
        out_text = json.dumps(parsed, ensure_ascii=False, indent=2)
    else:
        # 혹시 모델이 순수 JSON이 아니게 답하면 원문 그대로 남김
        out_text = cleaned

    print(out_text)

    # 7) 결과 저장(옵션)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_text)

    if image_path:
        print(f"\n촬영 이미지: {image_path}")

if __name__ == "__main__":
    main()
