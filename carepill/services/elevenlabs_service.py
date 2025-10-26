import requests
import os
from pathlib import Path
from django.conf import settings


class ElevenLabsService:
    """ElevenLabs API 통합 서비스"""

    def __init__(self):
        self.api_key = os.getenv('ELEVENLABS_API_KEY', '')
        self.base_url = "https://api.elevenlabs.io/v1"
        self.headers = {
            "xi-api-key": self.api_key
        }

    def create_voice_clone(self, voice_file_path, voice_name="User Voice", remove_bg_noise=True):
        """
        음성 샘플로 Voice Clone 생성

        Args:
            voice_file_path: 음성 파일 경로 (15초 이상)
            voice_name: 생성할 음성의 이름
            remove_bg_noise: 배경 소음 제거 여부

        Returns:
            dict: {
                'success': bool,
                'voice_id': str or None,
                'message': str
            }
        """
        try:
            url = f"{self.base_url}/voices/add"

            # 파일 열기
            with open(voice_file_path, 'rb') as f:
                files = {'files': f}
                data = {
                    'name': voice_name,
                    'remove_background_noise': str(remove_bg_noise).lower(),
                    'description': 'CarePill user voice clone'
                }

                response = requests.post(
                    url,
                    headers=self.headers,
                    files=files,
                    data=data
                )

            if response.status_code == 200:
                result = response.json()
                voice_id = result.get('voice_id')
                return {
                    'success': True,
                    'voice_id': voice_id,
                    'message': '음성 클론 생성 성공'
                }
            else:
                return {
                    'success': False,
                    'voice_id': None,
                    'message': f'Voice clone 생성 실패: {response.status_code} - {response.text}'
                }

        except Exception as e:
            return {
                'success': False,
                'voice_id': None,
                'message': f'오류 발생: {str(e)}'
            }

    def text_to_speech(self, voice_id, text, output_path=None):
        """
        Text-to-Speech 변환

        Args:
            voice_id: ElevenLabs voice ID
            text: 변환할 텍스트
            output_path: 출력 파일 경로 (None이면 바이너리 반환)

        Returns:
            bytes or bool: output_path가 None이면 오디오 바이너리, 아니면 성공 여부
        """
        try:
            url = f"{self.base_url}/text-to-speech/{voice_id}"

            headers = {
                **self.headers,
                "Content-Type": "application/json"
            }

            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }

            response = requests.post(url, headers=headers, json=data)

            if response.status_code == 200:
                if output_path:
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    return True
                else:
                    return response.content
            else:
                print(f"TTS 변환 실패: {response.status_code} - {response.text}")
                return None if not output_path else False

        except Exception as e:
            print(f"TTS 오류: {str(e)}")
            return None if not output_path else False

    def get_voices(self):
        """
        생성된 음성 목록 조회

        Returns:
            list: 음성 목록
        """
        try:
            url = f"{self.base_url}/voices"
            response = requests.get(url, headers=self.headers)

            if response.status_code == 200:
                return response.json().get('voices', [])
            else:
                return []

        except Exception as e:
            print(f"음성 목록 조회 오류: {str(e)}")
            return []

    def delete_voice(self, voice_id):
        """
        음성 삭제

        Args:
            voice_id: ElevenLabs voice ID

        Returns:
            bool: 성공 여부
        """
        try:
            url = f"{self.base_url}/voices/{voice_id}"
            response = requests.delete(url, headers=self.headers)
            return response.status_code == 200

        except Exception as e:
            print(f"음성 삭제 오류: {str(e)}")
            return False
