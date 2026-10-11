import React, { useState, useRef } from 'react';
import { Mic, Square, Play, Pause, Trash2, UploadCloud } from 'lucide-react';
import { Button } from '../ui/Button';

interface VoiceAudioRecorderProps {
  onAudioReady: (blob: Blob | File) => void;
}

export const VoiceAudioRecorder: React.FC<VoiceAudioRecorderProps> = ({
  onAudioReady,
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<any>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorderRef.current.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const url = URL.createObjectURL(audioBlob);
        setAudioUrl(url);
        onAudioReady(audioBlob);
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorderRef.current.start();
      setIsRecording(true);
      setRecordingTime(0);

      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } catch {
      alert('Microphone access denied or not supported by your browser.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
    }
  };

  const togglePlayback = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  const clearAudio = () => {
    setAudioUrl(null);
    setIsPlaying(false);
    setRecordingTime(0);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const url = URL.createObjectURL(file);
      setAudioUrl(url);
      onAudioReady(file);
    }
  };

  return (
    <div className="p-4 bg-slate-850 border border-slate-700/60 rounded-2xl space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
          Voice Announcement Recorder
        </span>
        {isRecording && (
          <span className="text-xs font-bold text-rose-400 animate-pulse flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            Recording ({recordingTime}s)
          </span>
        )}
      </div>

      {!audioUrl ? (
        <div className="flex flex-col sm:flex-row items-center gap-3">
          {isRecording ? (
            <Button
              type="button"
              variant="danger"
              size="md"
              leftIcon={<Square className="w-4 h-4" />}
              onClick={stopRecording}
              className="w-full sm:w-auto"
            >
              Stop Recording ({recordingTime}s)
            </Button>
          ) : (
            <Button
              type="button"
              variant="primary"
              size="md"
              leftIcon={<Mic className="w-4 h-4" />}
              onClick={startRecording}
              className="w-full sm:w-auto"
            >
              Start Microphone Recording
            </Button>
          )}

          <span className="text-xs text-slate-500 font-medium">or</span>

          <label className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2 bg-slate-800 border border-slate-700 hover:border-slate-600 rounded-xl text-xs font-semibold text-slate-300 hover:text-white cursor-pointer transition-colors">
            <UploadCloud className="w-4 h-4 text-emerald-400" />
            <span>Upload Audio File (.mp3 / .wav)</span>
            <input
              type="file"
              accept="audio/*"
              onChange={handleFileUpload}
              className="hidden"
            />
          </label>
        </div>
      ) : (
        <div className="flex items-center justify-between p-3 bg-slate-900 border border-slate-700 rounded-xl">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={togglePlayback}
              className="w-9 h-9 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white flex items-center justify-center transition-colors"
            >
              {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
            </button>
            <audio
              ref={audioRef}
              src={audioUrl}
              onEnded={() => setIsPlaying(false)}
              className="hidden"
            />
            <div>
              <p className="text-xs font-semibold text-white">Voice Announcement Ready</p>
              <p className="text-[10px] text-slate-400">Click play to preview before broadcasting</p>
            </div>
          </div>

          <button
            type="button"
            onClick={clearAudio}
            className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
};
