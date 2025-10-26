import requests
import os
from pathlib import Path

class ElevenLabsVoiceCloner:
    def __init__(self, api_key):
        """
        ElevenLabs API 초기화
        
        Args:
            api_key: ElevenLabs API 키
        """
        self.api_key = api_key
        self.base_url = "https://api.elevenlabs.io/v1"
        self.headers = {
            "xi-api-key": api_key
        }
    
    def clone_and_speak(self, voice_sample_path, text, output_path="output.mp3", 
                       voice_name="My Cloned Voice", remove_bg_noise=True):
        """
        음성 샘플로 voice clone 생성 후 텍스트를 해당 음성으로 변환
        
        Args:
            voice_sample_path: 음성 샘플 파일 경로 (10초 가량의 오디오)
            text: 음성으로 변환할 텍스트
            output_path: 출력 오디오 파일 경로
            voice_name: 생성할 음성의 이름
            remove_bg_noise: 배경 소음 제거 여부
            
        Returns:
            dict: {
                'success': bool,
                'voice_id': str,
                'output_file': str,
                'message': str
            }
        """
        try:
            # Step 1: Instant Voice Clone 생성
            print("Step 1: 음성 클론 생성 중...")
            voice_id = self._create_voice_clone(
                voice_sample_path, 
                voice_name, 
                remove_bg_noise
            )
            
            if not voice_id:
                return {
                    'success': False,
                    'voice_id': None,
                    'output_file': None,
                    'message': '음성 클론 생성 실패'
                }
            
            print(f"✓ 음성 클론 생성 완료! Voice ID: {voice_id}")
            
            # Step 2: 생성된 voice로 TTS 실행
            print("Step 2: 텍스트를 음성으로 변환 중...")
            success = self._text_to_speech(voice_id, text, output_path)
            
            if success:
                print(f"✓ 음성 생성 완료! 파일: {output_path}")
                return {
                    'success': True,
                    'voice_id': voice_id,
                    'output_file': output_path,
                    'message': '성공적으로 음성이 생성되었습니다'
                }
            else:
                return {
                    'success': False,
                    'voice_id': voice_id,
                    'output_file': None,
                    'message': 'TTS 변환 실패'
                }
                
        except Exception as e:
            return {
                'success': False,
                'voice_id': None,
                'output_file': None,
                'message': f'오류 발생: {str(e)}'
            }
    
    def _create_voice_clone(self, voice_sample_path, voice_name, remove_bg_noise):
        """
        Instant Voice Clone 생성 (내부 함수)
        """
        url = f"{self.base_url}/voices/add"
        
        # multipart/form-data로 전송
        files = {
            'files': open(voice_sample_path, 'rb')
        }
        
        data = {
            'name': voice_name,
            'remove_background_noise': str(remove_bg_noise).lower(),
            'description': 'Instant voice clone for TTS'
        }
        
        response = requests.post(
            url,
            headers=self.headers,
            files=files,
            data=data
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get('voice_id')
        else:
            print(f"Voice clone 생성 실패: {response.status_code}")
            print(f"응답: {response.text}")
            return None
    
    def _text_to_speech(self, voice_id, text, output_path):
        """
        Text-to-Speech 변환 (내부 함수)
        """
        url = f"{self.base_url}/text-to-speech/{voice_id}"
        
        headers = {
            **self.headers,
            "Content-Type": "application/json"
        }
        
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",  # 다국어 지원 모델
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            # 오디오 데이터를 파일로 저장
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return True
        else:
            print(f"TTS 변환 실패: {response.status_code}")
            print(f"응답: {response.text}")
            return False


# 사용 예시
if __name__ == "__main__":
    # API 키 설정
    API_KEY = "sk_b6d8bd63a5aed48f69d13b3ba385fefdcdb8b74fca94c6a3"
    
    # 클로너 초기화
    cloner = ElevenLabsVoiceCloner(API_KEY)
    
    # 음성 샘플로 클론 생성 후 TTS 실행
    result = cloner.clone_and_speak(
        voice_sample_path="Wjg_voice.mp3",  # 10초 가량의 내 목소리 녹음 파일
        text="오늘 아침약은 감기약 한알과 두통약 두알입니다",
        output_path="첫시도.mp3",
        voice_name="wjg",
        remove_bg_noise=True  # 배경 소음 제거
    )
    
    print(f"\n결과: {result}")
    
    # 같은 voice_id로 다시 사용하기
    if result['success']:
        voice_id = result['voice_id']
        print(f"\n저장된 Voice ID: {voice_id}")
        print("이 Voice ID를 저장해두면 다음에 clone 생성 없이 바로 TTS 사용 가능합니다!")