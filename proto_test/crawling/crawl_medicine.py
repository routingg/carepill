import os
import django
import time
import requests
from bs4 import BeautifulSoup

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medicine_project.settings')
django.setup()

from medicines.models import Medicine

def crawl_medicine_detail(item_seq):
    """식약처 의약품안전나라에서 상세정보 크롤링"""
    
    # 방법 1: getItemDetail
    url1 = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    
    # 방법 2: getItemDetailCache
    url2 = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetailCache?cacheSeq={item_seq}"
    
    for url in [url1, url2]:
        try:
            print(f"    시도 중: {url[:70]}...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, timeout=10, headers=headers)
            
            if response.status_code != 200:
                print(f"    ✗ 상태 코드: {response.status_code}")
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            data = {}
            
            # 효능효과 (_ee_doc)
            effect_section = soup.find('div', {'id': '_ee_doc'})
            if effect_section:
                text = effect_section.get_text(separator=' ', strip=True)
                if text and len(text) > 5:  # 최소 5자 이상
                    data['effect'] = text
                    print(f"    ✓ 효능효과 발견: {len(text)}자")
            
            # 용법용량 (_ud_doc)
            usage_section = soup.find('div', {'id': '_ud_doc'})
            if usage_section:
                text = usage_section.get_text(separator=' ', strip=True)
                if text and len(text) > 5:
                    data['usage'] = text
                    print(f"    ✓ 용법용량 발견: {len(text)}자")
            
            # 사용상 주의사항 (_nb_doc)
            warning_section = soup.find('div', {'id': '_nb_doc'})
            if warning_section:
                text = warning_section.get_text(separator=' ', strip=True)
                if text and len(text) > 5:
                    data['warning_general'] = text
                    print(f"    ✓ 주의사항 발견: {len(text)}자")
            
            # 저장방법 (테이블에서 추출)
            storage_th = soup.find('th', string='저장방법')
            if storage_th:
                storage_td = storage_th.find_next_sibling('td')
                if storage_td:
                    text = storage_td.get_text(strip=True)
                    if text:
                        data['storage'] = text
                        print(f"    ✓ 저장방법 발견: {text}")
            
            # 데이터가 있으면 성공
            if data:
                print(f"    ✅ 총 {len(data)}개 필드 발견!")
                return data
            else:
                print(f"    ⚠️ 데이터 없음")
            
        except Exception as e:
            print(f"    ✗ 에러: {str(e)}")
            continue
    
    return None

def fill_empty_fields():
    """빈 필드가 있는 의약품 정보 채우기"""
    
    # effect가 비어있는 의약품들 가져오기
    empty_medicines = Medicine.objects.filter(effect__isnull=True)
    
    print(f"📊 빈 필드가 있는 의약품: {empty_medicines.count()}개")
    print("🕷️ 크롤링 시작...\n")
    
    success = 0
    failed = 0
    
    for idx, medicine in enumerate(empty_medicines, 1):
        print(f"\n[{idx}/{len(empty_medicines)}] {medicine.item_name} (item_seq: {medicine.item_seq})")
        print("-" * 70)
        
        data = crawl_medicine_detail(medicine.item_seq)
        
        if data:
            # 데이터가 있으면 업데이트
            Medicine.objects.filter(item_seq=medicine.item_seq).update(**data)
            print(f"    🎉 DB 업데이트 완료!\n")
            success += 1
        else:
            print(f"    ❌ 실패\n")
            failed += 1
        
        # 서버 부하 방지를 위한 딜레이
        time.sleep(2)  # 2초로 늘림
        
        # 10개마다 중간 결과 출력
        if idx % 10 == 0:
            print(f"\n{'='*70}")
            print(f"📈 중간 결과: 성공 {success}개 ({success*100//idx}%), 실패 {failed}개")
            print(f"{'='*70}\n")
    
    print("\n" + "="*70)
    print(f"✅ 크롤링 완료!")
    print(f"   성공: {success}개 ({success*100//(success+failed) if (success+failed) > 0 else 0}%)")
    print(f"   실패: {failed}개")
    print("="*70)

if __name__ == "__main__":
    fill_empty_fields()