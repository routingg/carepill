import os
import cv2
import time
import base64
import json
from pathlib import Path
from decouple import config
import openai
from collections import Counter, defaultdict

# =========================
# 1) OpenAI 클라이언트
# =========================
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
        if t.startswith("```json"):
            t = t[len("```json"):].strip()
        elif t.startswith("```JSON"):
            t = t[len("```JSON"):].strip()
        else:
            t = t[3:].strip()
        if t.endswith("```"):
            t = t[:-3].strip()
    return t

def call_openai_with_image_b64(image_b64: str, analysis_type: str, model="gpt-4o-mini") -> str:
    if analysis_type == "envelope":
        text_prompt = (
            "이 약봉투 이미지를 분석해서 JSON 형태로 추출해주세요:\n"
            "{\n"
            '  "medicine_name": "약품명",\n'
            '  "dosage_instructions": "복용법",\n'
            '  "frequency": "복용횟수",\n'
            '  "prescription_number": "처방전 번호"\n'
            "}\n\n정확한 JSON 형태로만 응답해주세요. 한국어로 답변해주세요."
        )
    elif analysis_type == "schedule":
        text_prompt = (
            "이 복용 스케줄 이미지를 분석해서 JSON 형태로 추출해주세요:\n"
            "{\n"
            '  "morning": "아침 복용",\n'
            '  "lunch": "점심 복용",\n'
            '  "evening": "저녁 복용",\n'
            '  "meal_timing": "식전/식후"\n'
            "}\n\n정확한 JSON 형태로만 응답해주세요. 한국어로 답변해주세요."
        )
    elif analysis_type == "appearance":
        text_prompt = (
            "이 약물 이미지를 분석해서 JSON 형태로 추출해주세요:\n"
            "{\n"
            '  "shape": "형태 (정제, 캡슐 등)",\n'
            '  "color": "색상",\n'
            '  "size": "크기",\n'
            '  "marking": "각인",\n'
            '  "estimated_name": "추정 약물명",\n'
            '  "warnings": "주의사항"\n'
            "}\n\n정확한 JSON 형태로만 응답해주세요. 한국어로 답변해주세요."
        )
    else:
        raise ValueError("analysis_type은 envelope | schedule | appearance 중 하나여야 합니다.")

    client = get_openai_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "너는 한국 의약품 OCR 및 인식 전문가다. 반드시 유효한 JSON만 출력한다. 설명 문장은 쓰지 않는다."},
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

# =========================
# 2) 카메라 캡처
# =========================
def capture_preview_and_burst(camera_index=2, width=1920, height=1080,
                              warmup_frames=5, burst_count=3, interval_s=0.5,
                              window_name="Camera"):
    """
    스페이스 한 번 누르면 burst_count장 자동 촬영.
    q 또는 ESC로 취소. Ctrl+C로 강제 종료 가능.
    반환: [frame1, frame2, frame3]
    """
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"카메라(index={camera_index})를 열 수 없습니다.")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  float(width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    for _ in range(warmup_frames):
        cap.read()

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

    print("스페이스를 누르면 3장 연속 촬영을 시작합니다. q 또는 ESC로 취소.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q') or key == 27:  # q or ESC
                raise KeyboardInterrupt("촬영이 취소되었습니다.")
            elif key == 32:  # Space
                break
    except KeyboardInterrupt:
        cap.release()
        cv2.destroyAllWindows()
        raise

    # 스페이스 입력 후 버스트 촬영
    frames = []
    # 첫 번째는 지금 보이던 프레임으로 저장
    if frame is not None:
        frames.append(frame.copy())

    for i in range(burst_count - 1):
        time.sleep(interval_s)
        ok, f = cap.read()
        if ok and f is not None:
            frames.append(f.copy())

    cap.release()
    cv2.destroyAllWindows()

    if len(frames) < burst_count:
        print(f"경고: 요청한 {burst_count}장 중 {len(frames)}장만 촬영되었습니다.")
    return frames

# =========================
# 3) 인코딩 유틸
# =========================
def encode_frame_to_b64_jpeg(frame, jpeg_quality=95):
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok:
        raise RuntimeError("JPEG 인코딩 실패")
    return base64.b64encode(buf.tobytes()).decode("utf-8")

# =========================
# 4) 결과 병합(다수결+휴리스틱)
# =========================
def merge_json_results(json_list):
    """
    여러 번 분석한 JSON(dict)들을 받아 필드별 다수결로 병합.
    - 가장 많이 나온 값 채택
    - 동률이면 가장 긴 문자열(정보량이 많다고 가정) 우선
    - 모두 빈 값이면 빈 문자열
    추가로 필드별 신뢰도(비율)와 각 샷의 값도 함께 반환
    """
    if not json_list:
        return {}, {}

    # 모든 키 수집
    keys = set()
    for d in json_list:
        if isinstance(d, dict):
            keys.update(d.keys())

    merged = {}
    diagnostics = {}
    for k in keys:
        values = []
        for d in json_list:
            v = d.get(k, "")
            if v is None:
                v = ""
            if isinstance(v, (dict, list)):
                # 중첩은 문자열로 변환(이번 버전은 일단 평탄화)
                v = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
            v = str(v).strip()
            values.append(v)

        # 빈값 제외한 카운트
        non_empty = [v for v in values if v]
        if not non_empty:
            merged[k] = ""
            diagnostics[k] = {"per_shot": values, "selected": "", "confidence": 0.0}
            continue

        cnt = Counter(non_empty)
        most_common = cnt.most_common()
        if len(most_common) == 1:
            winner = most_common[0][0]
        else:
            top_freq = most_common[0][1]
            top_candidates = [val for val, c in most_common if c == top_freq]
            if len(top_candidates) == 1:
                winner = top_candidates[0]
            else:
                # 동률이면 가장 긴 문자열 선택
                winner = max(top_candidates, key=lambda s: len(s))

        confidence = cnt[winner] / max(1, len(values))
        merged[k] = winner
        diagnostics[k] = {"per_shot": values, "selected": winner, "confidence": round(confidence, 3)}

    return merged, diagnostics

# =========================
# 5) 메인
# =========================
def main():
    print("\n=== 약 정보 스캔 프로그램 ===")
    print("1. 약봉투 인식 (envelope)")
    print("2. 복용 스케줄 인식 (schedule)")
    print("3. 약 외관 식별 (appearance)")
    choice = input("\n분석할 항목을 선택하세요 (1~3): ").strip()

    analysis_map = {"1": "envelope", "2": "schedule", "3": "appearance"}
    analysis_type = analysis_map.get(choice)
    if not analysis_type:
        print("잘못된 선택입니다.")
        return

    # 촬영 및 저장 폴더
    save_dir = Path("captures")
    save_dir.mkdir(parents=True, exist_ok=True)

    try:
        frames = capture_preview_and_burst(camera_index=2, burst_count=3, interval_s=0.5)
        # 저장 및 인코딩
        image_b64_list = []
        paths = []
        ts_base = time.strftime("%Y%m%d_%H%M%S")
        for i, fr in enumerate(frames, start=1):
            img_path = save_dir / f"capture_{ts_base}_{i}.jpg"
            ok = cv2.imwrite(str(img_path), fr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            if not ok:
                print(f"경고: {img_path} 저장 실패")
            paths.append(str(img_path))
            image_b64_list.append(encode_frame_to_b64_jpeg(fr))

        print("\n이미지 3장을 촬영했습니다. 분석을 시작합니다...")

        # 각 샷 분석
        raw_texts = []
        per_shot_json = []
        for idx, b64 in enumerate(image_b64_list, start=1):
            try:
                raw = call_openai_with_image_b64(b64, analysis_type)
                cleaned = strip_code_fence(raw)
                raw_texts.append(cleaned)
                try:
                    parsed = json.loads(cleaned)
                except Exception:
                    parsed = {}
                per_shot_json.append(parsed)
                print(f"\n[샷 {idx}] 1차 결과:")
                if parsed:
                    print(json.dumps(parsed, ensure_ascii=False, indent=2))
                else:
                    print("(JSON 파싱 실패, 원문 표시)")
                    print(cleaned)
            except Exception as e:
                raw_texts.append(f"ERROR: {e}")
                per_shot_json.append({})
                print(f"\n[샷 {idx}] 분석 실패: {e}")

        # 병합
        merged, diag = merge_json_results(per_shot_json)
        print("\n=== 최종 병합 결과(JSON) ===")
        print(json.dumps(merged, ensure_ascii=False, indent=2))

        # 진단 정보(필드별 신뢰도/샷별 값)
        print("\n=== 필드별 비교/신뢰도 ===")
        for k, info in diag.items():
            print(f"\n[{k}]")
            for i, v in enumerate(info["per_shot"], start=1):
                print(f"  샷{i}: {v}")
            print(f"  선택값: {info['selected']}")
            print(f"  신뢰도: {info['confidence']}")

        # 결과 저장
        out_dir = Path("results")
        out_dir.mkdir(parents=True, exist_ok=True)
        result_path = out_dir / f"result_{ts_base}.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "analysis_type": analysis_type,
                    "shots": [{"image_path": p, "raw": r, "json": j} for p, r, j in zip(paths, raw_texts, per_shot_json)],
                    "merged": merged,
                    "diagnostics": diag,
                },
                f,
                ensure_ascii=False,
                indent=2
            )
        print(f"\n결과 저장: {result_path}")

        # 촬영 파일 안내
        print("\n촬영 이미지:")
        for p in paths:
            print(f" - {p}")

    except KeyboardInterrupt:
        print("\n촬영이 취소되었습니다.")
    except Exception as e:
        print(f"\n오류: {e}")

if __name__ == "__main__":
    main()
