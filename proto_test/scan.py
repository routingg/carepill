import os
import cv2
import time
import base64
import json
from pathlib import Path
from decouple import config
import openai
from collections import Counter
from typing import List, Dict, Tuple

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
        if t.startswith("```json") or t.startswith("```JSON"):
            t = t.split("\n", 1)[1] if "\n" in t else ""
        else:
            t = t[3:]
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
    return t

# =========================
# 2) 분석 호출 (약봉투 전용)
# =========================
def call_openai_envelope(image_b64: str, model: str = "gpt-4o-mini") -> str:
    """
    약봉투(Envelope) 전용 분석.
    필드:
      - patient_name (환자명)
      - age (나이, 숫자)
      - dispense_date (조제일자, YYYY-MM-DD 또는 YYYY.MM.DD)
      - pharmacy_name (약국명)
      - prescription_number (처방전/조제 번호, 숫자/영문 혼합 가능)
      - medicine_name (약품명)
      - dosage_instructions (복용법, 예: '아침, 저녁, 취침 전' 등)
      - frequency (복용횟수/기간, 예: '1일 1회 총 30일분')
      - med_features: { description, indications, cautions }
    """
    text_prompt = (
        "다음 약봉투 이미지를 분석하여 아래 스키마의 정확한 JSON만 출력하세요.\n"
        "가능하면 숫자/날짜는 포맷을 맞추세요.\n"
        "{\n"
        '  "patient_name": "환자명(문자열)",\n'
        '  "age": "나이(숫자 또는 빈 문자열)",\n'
        '  "dispense_date": "조제일자(YYYY-MM-DD 또는 YYYY.MM.DD)",\n'
        '  "pharmacy_name": "약국명",\n'
        '  "prescription_number": "처방전 또는 조제 번호",\n'
        '  "medicine_name": "약품명",\n'
        '  "dosage_instructions": "복용법(예: 아침, 저녁, 취침 전)",\n'
        '  "frequency": "복용횟수/기간(예: 1일 1회 총 30일분)",\n'
        '  "med_features": {\n'
        '    "description": "약의 한줄 설명",\n'
        '    "indications": "어디에 좋은지(적응증)",\n'
        '    "cautions": "주의사항(상호작용/부작용/주의대상 간단 요약)"\n'
        "  }\n"
        "}\n"
        "주의: 오타를 피하고, 사진 속 정보만 사용하세요. 모를 경우 빈 문자열로 두세요. 설명 문장이나 코드펜스 없이 JSON만 출력합니다."
    )

    client = get_openai_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system",
             "content": "너는 한국 약봉투 OCR/정보추출 전문가다. 반드시 유효한 JSON만 출력한다. 사진에 없는 정보는 공란('')으로 남긴다."},
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
        max_tokens=1000,
        temperature=0.1
    )
    return response.choices[0].message.content

# =========================
# 3) 카메라 미리보기 + ROI 가이드 + 버스트 촬영
# =========================
def draw_overlay(frame, roi_rect: Tuple[int, int, int, int]):
    """ROI 박스와 안내 텍스트 오버레이."""
    x, y, w, h = roi_rect
    # 반투명 마스크
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], frame.shape[0]), (0, 0, 0), -1)
    cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 0, 0), -1)  # 구멍
    alpha = 0.35
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    # ROI 테두리
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # 안내 문구
    cv2.putText(frame, "ROI inside the green box.", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, "Press SPACE / C / Q to capture (3 shots). ESC or Q to cancel.",
                (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 255, 200), 2, cv2.LINE_AA)

def capture_burst_with_roi(camera_index=2, width=1920, height=1080,
                           warmup_frames=6, burst_count=3, interval_s=0.5,
                           roi_rel=(0.15, 0.2, 0.70, 0.55),
                           window_name="Medicine Envelope Scanner") -> List:
    """
    실행 즉시 미리보기 + ROI 안내 표시.
    SPACE/C/Q -> 3연사 촬영 시작, ESC/Q -> 취소.
    ROI는 화면 중앙 상대비율(roi_rel)로 그려지고, 촬영 이미지는 ROI로 크롭해서 반환.
    반환: [cropped_frame1, cropped_frame2, cropped_frame3]
    """
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"카메라(index={camera_index})를 열 수 없습니다.")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  float(width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    # 워밍업
    for _ in range(warmup_frames):
        cap.read()

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

    # ROI 절대 좌표 계산
    ret, sample = cap.read()
    if not ret or sample is None:
        cap.release()
        cv2.destroyAllWindows()
        raise RuntimeError("카메라 프레임을 가져오지 못했습니다.")
    H, W = sample.shape[:2]
    rx, ry, rw, rh = roi_rel
    roi_rect = (int(W * rx), int(H * ry), int(W * rw), int(H * rh))

    print("정렬 후 스페이스/ C / Q 로 3연사 촬영을 시작합니다. ESC/Q 로 취소.")

    # 미리보기 루프
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            vis = frame.copy()
            draw_overlay(vis, roi_rect)
            cv2.imshow(window_name, vis)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')):  # ESC or q => cancel
                raise KeyboardInterrupt("촬영이 취소되었습니다.")
            if key in (32, ord('c'), ord('Q')):  # Space or c or Q => start capture
                break
    except KeyboardInterrupt:
        cap.release()
        cv2.destroyAllWindows()
        raise

    # 3연사 촬영 (ROI 크롭)
    cropped_frames = []
    x, y, w, h = roi_rect
    for i in range(burst_count):
        if i > 0:
            time.sleep(interval_s)
        ok, fr = cap.read()
        if not ok or fr is None:
            continue
        crop = fr[y:y+h, x:x+w].copy()
        cropped_frames.append(crop)

    cap.release()
    cv2.destroyAllWindows()
    if len(cropped_frames) == 0:
        raise RuntimeError("촬영된 이미지가 없습니다.")
    return cropped_frames

# =========================
# 4) 인코딩
# =========================
def encode_frame_to_b64_jpeg(frame, jpeg_quality=95) -> str:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok:
        raise RuntimeError("JPEG 인코딩 실패")
    return base64.b64encode(buf.tobytes()).decode("utf-8")

# =========================
# 5) 병합 로직(필드별 휴리스틱)
# =========================
def _majority_merge(values: List[str]) -> Tuple[str, float]:
    """가장 많이 나온 값을 선택, 동률이면 가장 긴 문자열."""
    cleaned = [v.strip() for v in values if isinstance(v, str)]
    non_empty = [v for v in cleaned if v]
    if not non_empty:
        return "", 0.0
    cnt = Counter(non_empty)
    top = cnt.most_common()
    top_freq = top[0][1]
    candidates = [v for v, c in top if c == top_freq]
    winner = max(candidates, key=lambda s: len(s))
    conf = cnt[winner] / max(1, len(values))
    return winner, round(conf, 3)

def _digits_only(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())

def merge_envelope_json(json_list: List[Dict]) -> Tuple[Dict, Dict]:
    """
    약봉투 결과 병합:
      - patient_name, pharmacy_name, medicine_name, dosage_instructions, frequency: 다수결
      - prescription_number: 숫자만 비교 우선(다수결), 그 다음 일반 다수결
      - age: 숫자만 추출해 다수결
      - dispense_date: 다수결(포맷은 모델이 맞춰줬다고 가정)
      - med_features: 내부 필드(설명/적응증/주의사항)도 각자 다수결
    """
    fields = [
        "patient_name", "age", "dispense_date", "pharmacy_name",
        "prescription_number", "medicine_name", "dosage_instructions", "frequency"
    ]
    merged = {}
    diag = {}

    # 평탄화
    results = []
    for d in json_list:
        if not isinstance(d, dict):
            results.append({})
            continue
        res = dict(d)
        mf = res.get("med_features", {})
        if not isinstance(mf, dict):
            mf = {}
        res["_mf_description"] = str(mf.get("description", "") or "").strip()
        res["_mf_indications"] = str(mf.get("indications", "") or "").strip()
        res["_mf_cautions"] = str(mf.get("cautions", "") or "").strip()
        results.append(res)

    # 일반 필드
    for k in fields:
        vals = [str(r.get(k, "") or "").strip() for r in results]
        if k == "age":
            norm = [_digits_only(v) for v in vals]
            best, conf = _majority_merge(norm)
            merged[k] = best
            diag[k] = {"per_shot": vals, "normalized": norm, "selected": best, "confidence": conf}
        elif k == "prescription_number":
            only_digits = [_digits_only(v) for v in vals]
            best_d, conf_d = _majority_merge(only_digits)
            if best_d:
                merged[k] = best_d
                diag[k] = {"per_shot": vals, "digits_only": only_digits, "selected": best_d, "confidence": conf_d}
            else:
                best, conf = _majority_merge(vals)
                merged[k] = best
                diag[k] = {"per_shot": vals, "selected": best, "confidence": conf}
        else:
            best, conf = _majority_merge(vals)
            merged[k] = best
            diag[k] = {"per_shot": vals, "selected": best, "confidence": conf}

    # med_features 내부
    for subk in ["description", "indications", "cautions"]:
        key = f"_mf_{subk}"
        vals = [r.get(key, "") for r in results]
        best, conf = _majority_merge(vals)
        diag[key] = {"per_shot": vals, "selected": best, "confidence": conf}

    merged["med_features"] = {
        "description": diag["_mf_description"]["selected"],
        "indications": diag["_mf_indications"]["selected"],
        "cautions": diag["_mf_cautions"]["selected"],
    }

    # 보기 좋게 diag 키 정리
    del diag["_mf_description"]
    del diag["_mf_indications"]
    del diag["_mf_cautions"]

    return merged, diag

# =========================
# 6) 메인
# =========================
def main():
    print("\n=== 약봉투 스캔 프로그램(ROI 가이드 + 3연사) ===")

    # 촬영
    try:
        frames = capture_burst_with_roi(
            camera_index=2,            # 필요 시 0/1/2로 바꿔 테스트
            width=1920, height=1080,
            burst_count=3, interval_s=0.5,
            roi_rel=(0.15, 0.20, 0.70, 0.55)  # (x,y,w,h) 비율: 화면 중앙 70%x55%
        )
    except KeyboardInterrupt:
        print("촬영이 취소되었습니다.")
        return
    except Exception as e:
        print(f"오류: {e}")
        return

    # 저장·인코딩
    ts = time.strftime("%Y%m%d_%H%M%S")
    cap_dir = Path("captures")
    cap_dir.mkdir(parents=True, exist_ok=True)
    b64_list = []
    shot_paths = []
    for i, fr in enumerate(frames, 1):
        p = cap_dir / f"envelope_crop_{ts}_{i}.jpg"
        ok = cv2.imwrite(str(p), fr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not ok:
            print(f"경고: {p} 저장 실패")
        shot_paths.append(str(p))
        b64_list.append(encode_frame_to_b64_jpeg(fr))

    print("\n이미지 3장을 촬영했습니다. 분석을 시작합니다...")

    # 각 샷 분석
    raw_list, json_list = [], []
    for idx, b64 in enumerate(b64_list, 1):
        try:
            raw = call_openai_envelope(b64)
            cleaned = strip_code_fence(raw)
            try:
                parsed = json.loads(cleaned)
            except Exception:
                parsed = {}
            raw_list.append(cleaned)
            json_list.append(parsed)
            # 개별 결과 출력(요약)
            print(f"\n[샷 {idx}] 추출 키: {list(parsed.keys()) if parsed else 'JSON 파싱 실패'}")
        except Exception as e:
            raw_list.append(f"ERROR: {e}")
            json_list.append({})
            print(f"\n[샷 {idx}] 분석 실패: {e}")

    # 병합
    merged, diag = merge_envelope_json(json_list)

    # 최종 결과 출력
    print("\n=== 최종 병합 결과(JSON) ===")
    print(json.dumps(merged, ensure_ascii=False, indent=2))

    # 상세 진단
    print("\n=== 필드별 비교/신뢰도 ===")
    for k, info in diag.items():
        print(f"\n[{k}]")
        for i, v in enumerate(info.get("per_shot", []), 1):
            print(f"  샷{i}: {v}")
        if "normalized" in info:
            print(f"  정규화: {info['normalized']}")
        if "digits_only" in info:
            print(f"  숫자만: {info['digits_only']}")
        print(f"  선택값: {info.get('selected','')}")
        print(f"  신뢰도: {info.get('confidence',0)}")

    # 결과 저장
    out_dir = Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"envelope_result_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "analysis_type": "envelope",
                "shots": [
                    {"image_path": p, "raw": r, "json": j}
                    for p, r, j in zip(shot_paths, raw_list, json_list)
                ],
                "merged": merged,
                "diagnostics": diag,
            },
            f, ensure_ascii=False, indent=2
        )
    print(f"\n결과 저장: {out_path}")

    print("\n촬영 이미지:")
    for p in shot_paths:
        print(" -", p)

if __name__ == "__main__":
    main()
