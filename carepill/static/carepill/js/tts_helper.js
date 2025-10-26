/**
 * ElevenLabs TTS 헬퍼 함수
 * 모든 페이지에서 공통으로 사용
 */

window.CarePillTTS = {
  // 현재 재생 중인 오디오
  currentAudio: null,

  /**
   * 텍스트를 ElevenLabs TTS로 변환하여 재생
   * @param {string} text - 변환할 텍스트
   * @param {object} options - 옵션 { onStart, onEnd, onError }
   */
  async speak(text, options = {}) {
    if (!text || !text.trim()) {
      console.warn('TTS: 빈 텍스트');
      return;
    }

    // 기존 재생 중지
    this.stop();

    try {
      if (options.onStart) options.onStart();

      const response = await fetch('/api/tts/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.trim() })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `TTS API 오류: ${response.status}`);
      }

      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);

      this.currentAudio = audio;

      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        this.currentAudio = null;
        if (options.onEnd) options.onEnd();
      };

      audio.onerror = (err) => {
        console.error('TTS 재생 오류:', err);
        URL.revokeObjectURL(audioUrl);
        this.currentAudio = null;
        if (options.onError) options.onError(err);
      };

      await audio.play();
      console.log('TTS 재생:', text.substring(0, 50) + '...');

    } catch (err) {
      console.error('TTS 오류:', err);
      if (options.onError) options.onError(err);

      // 사용자에게 알림 (음성이 등록되지 않은 경우)
      if (err.message && err.message.includes('등록된 음성이 없습니다')) {
        alert('먼저 홈 화면에서 "나의 음성 등록하기"를 완료해주세요.');
      }
    }
  },

  /**
   * 현재 재생 중지
   */
  stop() {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
      this.currentAudio = null;
    }
  },

  /**
   * 재생 중인지 확인
   */
  isPlaying() {
    return this.currentAudio && !this.currentAudio.paused;
  }
};
