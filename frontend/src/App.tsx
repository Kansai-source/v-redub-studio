import { useState, useEffect, useRef } from "react";
import {
  Download,
  Video,
  Eye,
  Sparkles,
  CheckCircle,
  User,
  Sliders,
  Type,
  FileVideo,
  Layers
} from "lucide-react";

// Types
interface Voice {
  id: string;
  name: string;
  type: string;
  gender: string;
  instruct?: string;
  file_path?: string;
}

interface Segment {
  id: number;
  start: number;
  end: number;
  original_text: string;
  text: string;
  gender: string;
  speaker_id?: string;
}

interface LogLine {
  text: string;
  type: "info" | "success" | "warning" | "error";
  time: string;
}

interface DownloadInfo {
  file_path: string;
  filename: string;
  title: string;
  duration: number;
  thumbnail: string;
  url: string;
  audio_path?: string;
}

interface FinalVideo {
  filename: string;
  video_path: string;
  size_bytes: number;
  url: string;
}

const BACKEND_URL = "http://localhost:8000";

export default function App() {
  // Config & API Keys
  const [url, setUrl] = useState("");

  // Transcribe options
  const [transcribeMode, setTranscribeMode] = useState<"local" | "gemini">("local");
  const [geminiKey, setGeminiKey] = useState(() => localStorage.getItem("gemini_api_key") || "");
  const [geminiModel, setGeminiModel] = useState("gemini-3.5-flash");
  const [customModel, setCustomModel] = useState("gemini-3.1-pro");
  const [geminiAPIEndpoint, setGeminiAPIEndpoint] = useState(() => localStorage.getItem("vredub_api_endpoint") || "");

  // Persist api endpoint to localStorage
  useEffect(() => {
    localStorage.setItem("vredub_api_endpoint", geminiAPIEndpoint);
  }, [geminiAPIEndpoint]);

  // States
  const [isDownloading, setIsDownloading] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isDubbing, setIsDubbing] = useState(false);

  const [downloadInfo, setDownloadInfo] = useState<DownloadInfo | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [finalVideo, setFinalVideo] = useState<FinalVideo | null>(null);
  const [videoAspectRatio, setVideoAspectRatio] = useState<number | null>(null);
  const [playerTime, setPlayerTime] = useState<number>(0);

  // Custom Voice Assignment state
  const [defaultMaleVoice, setDefaultMaleVoice] = useState("instruct_male_low");
  const [defaultFemaleVoice, setDefaultFemaleVoice] = useState("instruct_female_young");
  const [segmentVoices, setSegmentVoices] = useState<Record<string, string>>({});

  // Video Options
  const [zoomLevel, setZoomLevel] = useState<number>(10);
  const [zoomAlign, setZoomAlign] = useState<string>("center"); // center, top, bottom
  const [brightness, setBrightness] = useState<number>(0.0);
  const [contrast, setContrast] = useState<number>(1.0);
  const [saturation, setSaturation] = useState<number>(1.0);
  const [hflip, setHflip] = useState<boolean>(true);
  const [rotateAngle, setRotateAngle] = useState<number>(0.0); // angle in degrees -2 to 2
  const [enableDynamicPan, setEnableDynamicPan] = useState<boolean>(false); // camera shake/pan effect

  const [coverSub, setCoverSub] = useState<boolean>(false);
  const [cleanWatermark, setCleanWatermark] = useState<boolean>(false);
  const [watermarkCropPct, setWatermarkCropPct] = useState<number>(15);
  const [coverColor, setCoverColor] = useState<string>("gold");
  const [coverHOffset, setCoverHOffset] = useState<number>(65); // Height in pixels
  const [coverYPos, setCoverYPos] = useState<number>(0.82); // 82% from top
  const [coverWPct, setCoverWPct] = useState<number>(1.0);
  const [coverXPct, setCoverXPct] = useState<number>(0.0);
  const [coverAutoFit, setCoverAutoFit] = useState<boolean>(true);
  const [selectedTimelineSegIndex, setSelectedTimelineSegIndex] = useState<number | null>(null);

  const [originalVol, setOriginalVol] = useState<number>(0.15); // Ducked volume
  const [ttsVol, setTtsVol] = useState<number>(1.0);
  const [enableDucking, setEnableDucking] = useState<boolean>(false);
  const [duckingVolume, setDuckingVolume] = useState<number>(0.15);
  const [enableDubbing, setEnableDubbing] = useState<boolean>(true);

  // Custom Speed & Aspect Ratio
  const [videoSpeed, setVideoSpeed] = useState<number>(1.0);
  const [targetLang, setTargetLang] = useState<string>("vi");
  const [whisperModel, setWhisperModel] = useState<string>("base");
  const [sourceLang, setSourceLang] = useState<string>("auto");
  const [aspectRatioMode, setAspectRatioMode] = useState<string>("original"); // original, crop_9_16, blur_9_16
  const [subMarginV, setSubMarginV] = useState<number>(20); // vertical margin for burned subtitles
  const [enableSubtitles, setEnableSubtitles] = useState<boolean>(true);

  // Voice Upload States
  const [uploadVoiceName, setUploadVoiceName] = useState<string>("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploadingVoice, setIsUploadingVoice] = useState<boolean>(false);
  const [isUploadingVideo, setIsUploadingVideo] = useState<boolean>(false);

  // Zero-shot Designer States
  const [designerInstruct, setDesignerInstruct] = useState<string>("female, moderate pitch, young adult");
  const [isDesigning, setIsDesigning] = useState<boolean>(false);
  const [hasDesignedTemp, setHasDesignedTemp] = useState<boolean>(false);
  const [playingDesigner, setPlayingDesigner] = useState<boolean>(false);
  const [designerSaveName, setDesignerSaveName] = useState<string>("");
  const [isSavingDesign, setIsSavingDesign] = useState<boolean>(false);
  const designerAudioRef = useRef<HTMLAudioElement | null>(null);
  const [hasDraft, setHasDraft] = useState<boolean>(false);

  const handleVideoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploadingVideo(true);
    addLog(`Đang tải video cục bộ "${file.name}" lên server...`, "info");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${BACKEND_URL}/api/video/upload`, {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setDownloadInfo({
          file_path: data.file_path,
          filename: data.filename,
          title: data.title,
          duration: data.duration,
          thumbnail: data.thumbnail,
          url: data.url
        });
        setSegments([]);
        setVideoAspectRatio(null);

        if (data.detected_subtitles && data.detected_subtitles.detected) {
          setCoverYPos(data.detected_subtitles.cover_y_pct);
          setCoverHOffset(data.detected_subtitles.cover_h_px);
          addLog(`💡 Đã tự động dò ra vùng phụ đề gốc: Y=${Math.round(data.detected_subtitles.cover_y_pct * 100)}%, Cao=${data.detected_subtitles.cover_h_px}px.`, "success");
        }

        addLog(`Đã nạp video local thành công: ${data.title} (${Math.round(data.duration)} giây)`, "success");
      } else {
        addLog(`Lỗi tải lên video: ${data.message || data.detail || "Không rõ"}`, "error");
      }
    } catch (err: any) {
      addLog(`Lỗi kết nối khi tải video: ${err.message}`, "error");
    } finally {
      setIsUploadingVideo(false);
    }
  };

  const handleDesignerGenerate = async () => {
    setIsDesigning(true);
    setHasDesignedTemp(false);
    if (designerAudioRef.current) {
      designerAudioRef.current.pause();
      setPlayingDesigner(false);
    }
    try {
      const res = await fetch(`${BACKEND_URL}/api/designer/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruct: designerInstruct })
      });
      if (res.ok) {
        setHasDesignedTemp(true);
        addLog("Sinh thử giọng thành công! Nhấp ▶ để nghe thử.", "success");
      } else {
        const errorText = await res.text();
        addLog(`Lỗi sinh giọng: ${errorText}`, "error");
      }
    } catch (err: any) {
      addLog(`Lỗi kết nối sinh giọng: ${err.message}`, "error");
    } finally {
      setIsDesigning(false);
    }
  };

  const handleTogglePlayDesignerPreview = () => {
    if (playingDesigner) {
      if (designerAudioRef.current) {
        designerAudioRef.current.pause();
        designerAudioRef.current = null;
      }
      setPlayingDesigner(false);
    } else {
      if (designerAudioRef.current) {
        designerAudioRef.current.pause();
      }
      const audio = new Audio(`${BACKEND_URL}/api/designer/preview?t=${Date.now()}`);
      designerAudioRef.current = audio;
      setPlayingDesigner(true);
      audio.play().catch(err => {
        addLog(`Không thể nghe thử giọng thiết kế: ${err.message}`, "error");
        setPlayingDesigner(false);
      });
      audio.onended = () => {
        setPlayingDesigner(false);
      };
    }
  };

  const handleTimelineMouseDown = (
    e: React.MouseEvent,
    segIndex: number,
    type: "move" | "resize-left" | "resize-right"
  ) => {
    e.preventDefault();
    e.stopPropagation();

    const parentElement = e.currentTarget.parentElement;
    if (!parentElement) return;

    const parentRect = parentElement.getBoundingClientRect();
    const timetableWidth = parentRect.width;

    const initialStartX = e.clientX;
    const initialStartVal = segments[segIndex].start;
    const initialEndVal = segments[segIndex].end;
    const durLimit = downloadInfo?.duration || 30.0;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const dx = moveEvent.clientX - initialStartX;
      const dt = (dx / timetableWidth) * durLimit;

      setSegments(prev => {
        const next = [...prev];
        const target = { ...next[segIndex] };

        if (type === "move") {
          const duration = initialEndVal - initialStartVal;
          let newStart = initialStartVal + dt;
          let newEnd = initialEndVal + dt;

          if (newStart < 0) {
            newStart = 0;
            newEnd = duration;
          }
          if (newEnd > durLimit) {
            newEnd = durLimit;
            newStart = newEnd - duration;
          }

          target.start = newStart;
          target.end = newEnd;
        } else if (type === "resize-left") {
          let newStart = initialStartVal + dt;
          if (newStart < 0) newStart = 0;
          if (newStart > target.end - 0.2) newStart = target.end - 0.2;
          target.start = newStart;
        } else if (type === "resize-right") {
          let newEnd = initialEndVal + dt;
          if (newEnd > durLimit) newEnd = durLimit;
          if (newEnd < target.start + 0.2) newEnd = target.start + 0.2;
          target.end = newEnd;
        }

        next[segIndex] = target;
        return next;
      });
    };

    const handleMouseUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  };

  const handleDesignerSave = async () => {
    if (!designerSaveName.trim()) return;
    setIsSavingDesign(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/designer/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: designerSaveName })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setVoices(data.voices);
        setHasDesignedTemp(false);
        setDesignerSaveName("");
        addLog(`Đã lưu & khóa giọng thiết kế mới: ${designerSaveName}`, "success");
      } else {
        addLog(`Lỗi lưu giọng: ${data.message || data.detail || "Không rõ"}`, "error");
      }
    } catch (err: any) {
      addLog(`Lỗi mạng khi lưu giọng: ${err.message}`, "error");
    } finally {
      setIsSavingDesign(false);
    }
  };

  const handleVoiceUpload = async () => {
    if (!uploadFile || !uploadVoiceName.trim()) return;
    setIsUploadingVoice(true);
    addLog(`Đang gửi yêu cầu tải lên file giọng ${uploadVoiceName.trim()}...`, "info");

    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      formData.append("name", uploadVoiceName.trim());

      const res = await fetch(`${BACKEND_URL}/api/upload-voice`, {
        method: "POST",
        body: formData
      });

      const data = await res.json();
      if (res.ok && data.success) {
        setVoices(data.voices || []);
        addLog(`Tải lên thành công giọng Clone: ${uploadVoiceName.trim()}!`, "success");
        setUploadVoiceName("");
        setUploadFile(null);
        // Clear input element
        const fileInput = document.getElementById("voice-file-upload") as HTMLInputElement;
        if (fileInput) fileInput.value = "";
      } else {
        addLog(`Lỗi tải lên: ${data.error || "Không rõ"}`, "error");
      }
    } catch (err: any) {
      addLog(`Lỗi mạng tải lên giọng: ${err.message}`, "error");
    } finally {
      setIsUploadingVoice(false);
    }
  };

  // Audio preview state
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const togglePlayVoice = (voiceId: string) => {
    if (playingVoiceId === voiceId) {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      setPlayingVoiceId(null);
    } else {
      if (audioRef.current) {
        audioRef.current.pause();
      }

      const src = `${BACKEND_URL}/api/voices/file/${voiceId}`;
      const audio = new Audio(src);
      audioRef.current = audio;
      setPlayingVoiceId(voiceId);

      audio.play().catch(err => {
        addLog(`Không thể nghe thử giọng này (Chỉ hỗ trợ giọng Clone): ${err.message}`, "error");
        setPlayingVoiceId(null);
      });

      audio.onended = () => {
        setPlayingVoiceId(null);
      };
    }
  };
  // UI States
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [activeAppTab, setActiveAppTab] = useState<"studio" | "timeline">("studio");
  const [activePlayerTab, setActivePlayerTab] = useState<"original" | "dubbed">("original");
  const [activeConsoleTab, setActiveConsoleTab] = useState<"logs" | "preview">("logs");
  const [isTimelineSynced, setIsTimelineSynced] = useState<boolean>(false);
  const consoleContainerRef = useRef<HTMLDivElement>(null);
  // Load Voices & saved api key
  useEffect(() => {
    fetchVoices();
    addLog("Khởi tạo V-reDub Studio. Hệ thống đã sẵn sàng.", "info");
  }, []);

  // Save gemini key
  useEffect(() => {
    localStorage.setItem("gemini_api_key", geminiKey);
  }, [geminiKey]);

  // Read draft status on mount
  useEffect(() => {
    const savedDraft = localStorage.getItem("vredub_draft_v1");
    if (savedDraft) {
      setHasDraft(true);
    }
  }, []);

  // Autosave when changes occur
  useEffect(() => {
    if (!downloadInfo) return;
    const draft = {
      downloadInfo,
      segments,
      segmentVoices,
      defaultMaleVoice,
      defaultFemaleVoice,
      videoOptions: {
        zoomLevel,
        zoomAlign,
        brightness,
        contrast,
        saturation,
        hflip,
        rotateAngle,
        enableDynamicPan,
        coverSub,
        coverColor,
        coverHOffset,
        coverYPos,
        coverWPct,
        coverXPct,
        coverAutoFit,
        originalVol,
        ttsVol,
        enableDucking,
        duckingVolume,
        enableDubbing,
        videoSpeed,
        aspectRatioMode,
        subMarginV,
        enableSubtitles
      }
    };
    localStorage.setItem("vredub_draft_v1", JSON.stringify(draft));
  }, [
    downloadInfo,
    segments,
    segmentVoices,
    defaultMaleVoice,
    defaultFemaleVoice,
    zoomLevel,
    zoomAlign,
    brightness,
    contrast,
    saturation,
    hflip,
    rotateAngle,
    enableDynamicPan,
    coverSub,
    coverColor,
    coverHOffset,
    coverYPos,
    coverWPct,
    coverXPct,
    coverAutoFit,
    originalVol,
    ttsVol,
    enableDucking,
    duckingVolume,
    enableDubbing,
    videoSpeed,
    aspectRatioMode,
    subMarginV,
    enableSubtitles
  ]);

  const handleRestoreDraft = () => {
    try {
      const savedDraft = localStorage.getItem("vredub_draft_v1");
      if (!savedDraft) return;
      const draft = JSON.parse(savedDraft);
      if (draft.downloadInfo) setDownloadInfo(draft.downloadInfo);
      if (draft.segments) setSegments(draft.segments);
      if (draft.segmentVoices) setSegmentVoices(draft.segmentVoices);
      if (draft.defaultMaleVoice) setDefaultMaleVoice(draft.defaultMaleVoice);
      if (draft.defaultFemaleVoice) setDefaultFemaleVoice(draft.defaultFemaleVoice);

      const opt = draft.videoOptions || {};
      if (opt.zoomLevel !== undefined) setZoomLevel(opt.zoomLevel);
      if (opt.zoomAlign !== undefined) setZoomAlign(opt.zoomAlign);
      if (opt.brightness !== undefined) setBrightness(opt.brightness);
      if (opt.contrast !== undefined) setContrast(opt.contrast);
      if (opt.saturation !== undefined) setSaturation(opt.saturation);
      if (opt.hflip !== undefined) setHflip(opt.hflip);
      if (opt.rotateAngle !== undefined) setRotateAngle(opt.rotateAngle);
      if (opt.enableDynamicPan !== undefined) setEnableDynamicPan(opt.enableDynamicPan);

      if (opt.coverSub !== undefined) setCoverSub(opt.coverSub);
      if (opt.coverColor !== undefined) setCoverColor(opt.coverColor);
      if (opt.coverHOffset !== undefined) setCoverHOffset(opt.coverHOffset);
      if (opt.coverYPos !== undefined) setCoverYPos(opt.coverYPos);
      if (opt.coverWPct !== undefined) setCoverWPct(opt.coverWPct);
      if (opt.coverXPct !== undefined) setCoverXPct(opt.coverXPct);
      if (opt.coverAutoFit !== undefined) setCoverAutoFit(opt.coverAutoFit);

      if (opt.originalVol !== undefined) setOriginalVol(opt.originalVol);
      if (opt.ttsVol !== undefined) setTtsVol(opt.ttsVol);
      if (opt.enableDucking !== undefined) setEnableDucking(opt.enableDucking);
      if (opt.duckingVolume !== undefined) setDuckingVolume(opt.duckingVolume);
      if (opt.enableDubbing !== undefined) setEnableDubbing(opt.enableDubbing);

      if (opt.videoSpeed !== undefined) setVideoSpeed(opt.videoSpeed);
      if (opt.aspectRatioMode !== undefined) setAspectRatioMode(opt.aspectRatioMode);
      if (opt.subMarginV !== undefined) setSubMarginV(opt.subMarginV);
      if (opt.enableSubtitles !== undefined) setEnableSubtitles(opt.enableSubtitles);

      addLog("Khôi phục bản nháp tiến trình thành công!", "success");
      setHasDraft(false);
    } catch (e: any) {
      addLog(`Lỗi phục hồi bản nháp: ${e.message}`, "error");
    }
  };

  const handleDiscardDraft = () => {
    localStorage.removeItem("vredub_draft_v1");
    setHasDraft(false);
    addLog("Đã bỏ qua & xóa bản nháp cũ.", "info");
  };



  // Autoscroll logs
  useEffect(() => {
    if (consoleContainerRef.current) {
      consoleContainerRef.current.scrollTop = consoleContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const fetchVoices = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/voices`);
      if (res.ok) {
        const data = await res.json();
        setVoices(data.voices || []);
        addLog(`Đã tải thành công danh sách ${data.voices?.length || 0} giọng đọc từ local Voice_ref.`, "success");
      } else {
        addLog("Không thể nạp danh sách giọng đọc từ Service. Vui lòng kiểm tra backend.", "error");
      }
    } catch (err) {
      addLog(`Lỗi kết nối server: ${err}`, "error");
    }
  };

  const addLog = (text: string, type: "info" | "success" | "warning" | "error" = "info") => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, { text, type, time: timestamp }]);
  };

  const startSSEListener = (
    taskId: string,
    onSuccess: (result: any) => void,
    onFailure: (errorMsg: string) => void,
    onProgress: (pct: number, msg: string) => void
  ) => {
    const eventSource = new EventSource(`${BACKEND_URL}/api/tasks/${taskId}/progress`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onProgress(data.progress, data.message);

        if (data.status === "completed") {
          eventSource.close();
          onSuccess(data.result);
        } else if (data.status === "failed") {
          eventSource.close();
          onFailure(data.error || data.message || "Tác vụ thất bại.");
        }
      } catch (e: any) {
        eventSource.close();
        onFailure(`Lỗi dữ liệu tiến độ: ${e.message}`);
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      onFailure("Mất kết nối với máy chủ theo dõi tiến độ.");
    };
  };

  // 1. Tải Video
  const handleDownload = async () => {
    if (!url.trim()) {
      alert("Vui lòng điền link video!");
      return;
    }

    setIsDownloading(true);
    setDownloadInfo(null);
    setSegments([]);
    setFinalVideo(null);
    setSegmentVoices({});
    setVideoAspectRatio(null);

    addLog("Bắt đầu tải video từ URL...", "info");
    addLog(`Đang gửi yêu cầu download yt-dlp cho URL: ${url}`, "info");

    try {
      const res = await fetch(`${BACKEND_URL}/api/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Tải video thất bại.");
      }

      const resData = await res.json();
      if (!resData.success || !resData.task_id) {
        throw new Error("Không nhận được ID tiến trình tải.");
      }

      addLog(`Đã đăng ký tác vụ tải ngầm. ID: ${resData.task_id}`, "info");

      startSSEListener(
        resData.task_id,
        (result) => {
          setDownloadInfo(result);
          addLog(`Lưu video gốc thành công: ${result.filename}`, "success");
          addLog(`Tiêu đề: "${result.title}" (${Math.round(result.duration)} giây)`, "success");
          addLog("Đã tách âm thanh WAV thành công. Bạn có thể tiến hành tách phụ đề Whisper.", "info");

          if (result.detected_subtitles && result.detected_subtitles.detected) {
            setCoverYPos(result.detected_subtitles.cover_y_pct);
            setCoverHOffset(result.detected_subtitles.cover_h_px);
            addLog(`💡 Đã tự động dò ra vùng phụ đề gốc: Y=${Math.round(result.detected_subtitles.cover_y_pct * 100)}%, Cao=${result.detected_subtitles.cover_h_px}px.`, "success");
          }

          setActivePlayerTab("original");
          setIsDownloading(false);
        },
        (errorMsg) => {
          addLog(`Lỗi tải video: ${errorMsg}`, "error");
          setIsDownloading(false);
        },
        (pct, msg) => {
          addLog(`[Tiến trình tải ${pct}%] ${msg}`, "info");
        }
      );
    } catch (err: any) {
      addLog(`Lỗi tải video: ${err.message}`, "error");
      setIsDownloading(false);
    }
  };

  // 2. Tách dịch phụ đề (Whisper + GPT)
  const handleTranscribe = async () => {
    if (!downloadInfo) return;

    setIsTranscribing(true);
    if (transcribeMode === "local") {
      addLog("Khởi chạy bộ dịch Whisper local trên máy của bạn...", "info");
      addLog("Đang nhận dạng giọng nói gốc bằng Whisper Model (base) ở local...", "info");
      addLog("Đang tiến hành dịch hội thoại sang tiếng Việt (miễn phí)...", "info");
    } else {
      const activeModel = geminiModel === "custom" ? customModel : geminiModel;
      addLog(`Khởi chạy phân tích Gemini API (${activeModel}). Hệ thống tự động cắt âm thanh thành đoạn 15 phút...`, "info");
      addLog("Đang gửi và xử lý dữ liệu qua Gemini API...", "info");
    }

    try {
      const res = await fetch(`${BACKEND_URL}/api/transcribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_path: downloadInfo.file_path,
          mode: transcribeMode,
          gemini_key: transcribeMode === "gemini" ? geminiKey : undefined,
          gemini_model: transcribeMode === "gemini" ? (geminiModel === "custom" ? customModel : geminiModel) : undefined,
          gemini_chunk_size: 900,
          gemini_api_endpoint: transcribeMode === "gemini" && geminiAPIEndpoint ? geminiAPIEndpoint : undefined,
          target_lang: targetLang,
          whisper_model: whisperModel,
          source_lang: sourceLang
        })
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(errorText || "Tách tiếng thất bại.");
      }

      const resData = await res.json();
      if (!resData.success || !resData.task_id) {
        throw new Error("Không nhận được ID bộ phiên phiên âm.");
      }

      addLog(`Tác vụ dịch chạy ngầm đã kích hoạt. ID: ${resData.task_id}`, "info");

      startSSEListener(
        resData.task_id,
        (result) => {
          setSegments(result.segments || []);

          // Auto-assign default voices by gender recommendation
          const initialAssignments: Record<string, string> = {};
          result.segments.forEach((seg: Segment) => {
            initialAssignments[`seg_${seg.id}`] = seg.gender === "male" ? defaultMaleVoice : defaultFemaleVoice;
          });
          setSegmentVoices(initialAssignments);

          addLog(`Tách hội thoại hoàn tất! Tìm thấy ${result.segments.length} câu thoại dịch Việt.`, "success");
          setIsTranscribing(false);
        },
        (errorMsg) => {
          addLog(`Lỗi phiên dịch: ${errorMsg}`, "error");
          setIsTranscribing(false);
        },
        (pct, msg) => {
          addLog(`[Tiến trình dịch ${pct}%] ${msg}`, "info");
        }
      );
    } catch (err: any) {
      addLog(`Lỗi nhận diện giọng nói: ${err.message}`, "error");
      setIsTranscribing(false);
    }
  };

  // Custom API Endpoint Model Scanner
  const handleScanModels = async () => {
    if (!geminiKey) {
      addLog("Lỗi quét mô hình: Chưa cung cấp Gemini API Key!", "error");
      return;
    }

    addLog(`Đang thực hiện quét danh sách mô hình từ kết nối: ${geminiAPIEndpoint || "Mặc định (Google)"}...`, "info");

    try {
      const urlParams = new URLSearchParams({
        gemini_key: geminiKey
      });
      if (geminiAPIEndpoint) {
        urlParams.append("gemini_api_endpoint", geminiAPIEndpoint);
      }

      const res = await fetch(`${BACKEND_URL}/api/models?${urlParams.toString()}`);
      const data = await res.json();

      if (data.success && data.models) {
        addLog(`Quét thành công! Tìm thấy ${data.models.length} mô hình được hỗ trợ bởi Endpoint này.`, "success");
        addLog(`Danh sách mô hình khả dụng:\n- ${data.models.join("\n- ")}`, "success");
      } else {
        addLog(`Quét mô hình thất bại: ${data.error || "Lỗi không xác định"}`, "error");
      }
    } catch (e: any) {
      addLog(`Lỗi xử lý quét mô hình: ${e.message}`, "error");
    }
  };

  // 3. Phối trộn Edit & Dub Video
  const handleDubAndEdit = async () => {
    const needsTranscription = enableDubbing || enableSubtitles;
    if (!downloadInfo || (needsTranscription && segments.length === 0)) {
      alert("Vui lòng tải video và thực hiện dịch phụ đề / lồng tiếng trước!");
      return;
    }

    setIsDubbing(true);
    setFinalVideo(null);
    setActiveConsoleTab("logs");
    addLog("Bắt đầu biên dịch và lồng tiếng hoàn chỉnh...", "info");
    addLog("Đang khởi tạo OmniVoice model trên local (vui lòng kết nối CUDA)...", "info");

    // Package voices settings
    const voiceDefinitions = {
      male: defaultMaleVoice,
      female: defaultFemaleVoice,
      ...segmentVoices
    };

    const requestPayload = {
      video_path: downloadInfo.file_path,
      segments: segments,
      voice_definitions: voiceDefinitions,
      video_options: {
        zoom_level: zoomLevel,
        brightness: brightness,
        contrast: contrast,
        saturation: saturation,
        hflip: hflip,
        cover_sub: coverSub,
        cover_color: coverColor,
        cover_y_pct: coverYPos,
        cover_h_px: coverHOffset,
        cover_w_pct: coverWPct,
        cover_x_pct: coverXPct,
        original_audio_vol: originalVol,
        tts_audio_vol: ttsVol,
        speed: videoSpeed,
        aspect_ratio_mode: aspectRatioMode,
        zoom_align: zoomAlign,
        enable_ducking: enableDucking,
        ducking_volume: duckingVolume,
        cover_auto_fit: coverAutoFit,
        enable_dubbing: enableDubbing,
        subtitle_margin_v: subMarginV,
        rotate_angle: rotateAngle,
        enable_dynamic_pan: enableDynamicPan,
        clean_watermark: cleanWatermark,
        watermark_crop_pct: watermarkCropPct,
        enable_subtitles: enableSubtitles
      }
    };

    try {
      const res = await fetch(`${BACKEND_URL}/api/dub-and-edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestPayload)
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(errorText || "Lồng tiếng và chỉnh sửa video thất bại.");
      }

      const resData = await res.json();
      if (!resData.success || !resData.task_id) {
        throw new Error("Không nhận được ID kết xuất video.");
      }

      addLog(`Lệnh render đã vào hàng đợi của hệ thống. ID: ${resData.task_id}`, "info");

      startSSEListener(
        resData.task_id,
        (result) => {
          setFinalVideo(result);
          addLog("Lồng tiếng Omni TTS thành công!", "success");
          addLog(`FFmpeg biên dựng video lách bản quyền hoàn tất: ${result.filename}`, "success");
          addLog(`Dung lượng video: ${(result.size_bytes / (1024 * 1024)).toFixed(2)} MB`, "success");

          // Auto toggle to dubbed view
          setActivePlayerTab("dubbed");
          addLog("Hoàn thành! Bạn có thể xem kết quả lồng tiếng lách bản quyền.", "success");
          setIsDubbing(false);
        },
        (errorMsg) => {
          addLog(`Lỗi xử lý video: ${errorMsg}`, "error");
          setIsDubbing(false);
        },
        (pct, msg) => {
          addLog(`[Tiến trình Render ${pct}%] ${msg}`, "info");
        }
      );
    } catch (err: any) {
      addLog(`Lỗi xử lý video: ${err.message}`, "error");
      setIsDubbing(false);
    }
  };

  const handleSegmentTextChange = (id: number, val: string) => {
    setSegments((prev) =>
      prev.map((seg) => (seg.id === id ? { ...seg, text: val } : seg))
    );
  };

  const handleSegmentVoiceChange = (segId: number, voiceId: string) => {
    const currentSeg = segments.find(s => s.id === segId);
    const speakerId = currentSeg?.speaker_id;

    setSegmentVoices((prev) => {
      const nextSegmentVoices = { ...prev, [`seg_%ID%`.replace('%ID%', String(segId))]: voiceId };

      // Auto-synchronize segments with same speaker ID only in gemini mode
      if (transcribeMode === "gemini" && speakerId) {
        segments.forEach((seg) => {
          if (seg.speaker_id === speakerId) {
            nextSegmentVoices[`seg_%ID%`.replace('%ID%', String(seg.id))] = voiceId;
          }
        });
      }
      return nextSegmentVoices;
    });
  };

  return (
    <div className="app-container">
      {/* SVG Gradient Definition */}
      <svg width="0" height="0" style={{ position: "absolute" }}>
        <defs>
          <linearGradient id="brand-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#d946ef" />
          </linearGradient>
        </defs>
      </svg>

      {/* Header */}
      <header className="app-header glass-panel">
        <div className="brand-section">
          <div className="brand-logo">
            <Sparkles size={24} />
            V-reDub Studio
          </div>
        </div>

        <div className="segmented-tabs-container">
          <button
            className={`segmented-tab-btn ${activeAppTab === "studio" ? "active" : ""}`}
            onClick={() => setActiveAppTab("studio")}
          >
            <Sparkles size={14} style={{ opacity: activeAppTab === "studio" ? 1 : 0.7 }} />
            Phòng Biên Tập (Studio)
          </button>
          <button
            className={`segmented-tab-btn ${activeAppTab === "timeline" ? "active" : ""}`}
            onClick={() => {
              if (downloadInfo) {
                setActiveAppTab("timeline");
              }
            }}
            disabled={!downloadInfo}
            title={!downloadInfo ? "Vui lòng tải video ở Phòng Biên Tập trước" : ""}
          >
            <Layers size={14} style={{ opacity: activeAppTab === "timeline" ? 1 : 0.7 }} />
            Trình Dựng Timeline
          </button>
        </div>
        <div className="api-settings">
          <span className="badge-neon" style={{ background: "linear-gradient(90deg, #10B981, #059669)", padding: "4px 10px", borderRadius: "12px", border: "1px solid rgba(16, 185, 129, 0.3)" }}>
            Local Offline Mode
          </span>
        </div>
      </header>

      {/* Workspace Dashboard */}
      {activeAppTab === "studio" ? (
        <main className="dashboard-grid">

          {/* ================= COLUMN 1: SIDEBAR OPTIONS ================= */}
          <section className="sidebar-panel glass-panel">
            <div className="panel-title text-primary">
              <Sliders size={18} />
              Cấu hình lách & tải
            </div>

            {/* Download Module */}
            <div className="panel-section subtly-boxed">
              <div className="section-label">1. Tải video gốc</div>
              <div className="input-with-button">
                <input
                  type="text"
                  placeholder="Link Bilibili, Douyin..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  disabled={isDownloading || isUploadingVideo}
                />
                <button
                  className="btn-primary"
                  onClick={handleDownload}
                  disabled={isDownloading || !url || isUploadingVideo}
                >
                  {isDownloading ? <div className="spinner" /> : <Download size={16} />}
                </button>
              </div>

              <div style={{ marginTop: "12px", borderTop: "1px dashed rgba(255,255,255,0.1)", paddingTop: "8px" }}>
                <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>
                  Hoặc tải lên từ máy tính:
                </span>
                <label
                  className="btn-primary"
                  style={{
                    width: "100%",
                    fontSize: "12px",
                    padding: "8px 12px",
                    cursor: (isUploadingVideo || isDownloading) ? "not-allowed" : "pointer",
                    opacity: (isUploadingVideo || isDownloading) ? 0.6 : 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                    background: "rgba(255,255,255,0.05)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    color: "#fff",
                    boxShadow: "none"
                  }}
                >
                  {isUploadingVideo ? (
                    <>
                      <div className="spinner" /> Đang tải video lên...
                    </>
                  ) : (
                    <>
                      <Video size={14} /> Chọn tệp video (.mp4, .mov...)
                    </>
                  )}
                  <input
                    type="file"
                    accept="video/*"
                    onChange={handleVideoUpload}
                    disabled={isUploadingVideo || isDownloading}
                    style={{ display: "none" }}
                  />
                </label>
              </div>

              {downloadInfo && (
                <div className="status-banner success" style={{ marginTop: 8 }}>
                  <CheckCircle size={14} />
                  Đã nạp video gốc!
                </div>
              )}
            </div>

            {/* FFmpeg Hack Options */}
            <div className="panel-section subtly-boxed">
              <div className="section-label">2. Video filter lách bản quyền</div>

              {/* Zoom Slider */}
              <div className="slider-group">
                <div className="slider-label-row">
                  <span>Phóng to (Crop Zoom):</span>
                  <span className="slider-value">{zoomLevel}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="25"
                  step="1"
                  value={zoomLevel}
                  onChange={(e) => {
                    const val = parseInt(e.target.value);
                    setZoomLevel(val);
                    if (val > 0) {
                      setCleanWatermark(false);
                    }
                  }}
                />
              </div>

              {/* Zoom Alignment Dropdown */}
              <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "8px", marginBottom: "8px" }}>
                <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>CÂN LỀ ZOOM (CẮT WATERMARK):</span>
                <select
                  value={zoomAlign}
                  onChange={(e) => setZoomAlign(e.target.value)}
                  style={{ padding: "6px 10px", fontSize: "13px" }}
                >
                  <option value="center">Chính giữa (Mặc định)</option>
                  <option value="bottom">Căn dưới (Shave top - Cắt watermark trên)</option>
                  <option value="top">Căn trên (Shave bottom - Cắt watermark dưới)</option>
                </select>
              </div>

              {/* Brightness Slider */}
              <div className="slider-group">
                <div className="slider-label-row">
                  <span>Độ sáng (Brightness):</span>
                  <span className="slider-value">{brightness > 0 ? `+${brightness}` : brightness}</span>
                </div>
                <input
                  type="range"
                  min="-0.2"
                  max="0.2"
                  step="0.01"
                  value={brightness}
                  onChange={(e) => setBrightness(parseFloat(e.target.value))}
                />
              </div>

              {/* Contrast Slider */}
              <div className="slider-group">
                <div className="slider-label-row">
                  <span>Độ tương phản (Contrast):</span>
                  <span className="slider-value">{contrast}x</span>
                </div>
                <input
                  type="range"
                  min="0.8"
                  max="1.3"
                  step="0.01"
                  value={contrast}
                  onChange={(e) => setContrast(parseFloat(e.target.value))}
                />
              </div>

              {/* Saturation Slider */}
              <div className="slider-group">
                <div className="slider-label-row">
                  <span>Độ bão hòa màu:</span>
                  <span className="slider-value">{saturation}x</span>
                </div>
                <input
                  type="range"
                  min="0.8"
                  max="1.4"
                  step="0.01"
                  value={saturation}
                  onChange={(e) => setSaturation(parseFloat(e.target.value))}
                />
              </div>

              {/* Flip toggle */}
              <div className="toggle-row">
                <span style={{ fontSize: "14px" }}>Lật ngược video (Xoay ngang):</span>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={hflip}
                    onChange={(e) => setHflip(e.target.checked)}
                  />
                  <span className="slider-switch"></span>
                </label>
              </div>

              {/* Subtitle toggle */}
              <div className="toggle-row">
                <span style={{ fontSize: "14px" }}>Ghép phụ đề vào video:</span>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={enableSubtitles}
                    onChange={(e) => setEnableSubtitles(e.target.checked)}
                  />
                  <span className="slider-switch"></span>
                </label>
              </div>

              {/* Video Speed Slider */}
              <div className="slider-group" style={{ marginTop: "12px", borderTop: "1px solid rgba(255, 255, 255, 0.05)", paddingTop: "12px" }}>
                <div className="slider-label-row">
                  <span>Tốc độ video:</span>
                  <span className="slider-value">{videoSpeed}x</span>
                </div>
                <input
                  type="range"
                  min="0.5"
                  max="2.0"
                  step="0.05"
                  value={videoSpeed}
                  onChange={(e) => setVideoSpeed(parseFloat(e.target.value))}
                />
              </div>

              {/* Aspect Ratio 9:16 Reframe Dropdown */}
              <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "8px" }}>
                <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>ĐỔI KHUNG HÌNH (REFRAME):</span>
                <select
                  value={aspectRatioMode}
                  onChange={(e) => setAspectRatioMode(e.target.value)}
                  style={{ padding: "6px 10px", fontSize: "13px" }}
                >
                  <option value="original">Giữ nguyên gốc (16:9)</option>
                  <option value="crop_9_16">Cắt giữa 9:16 (Center Crop)</option>
                  <option value="blur_9_16">Lồng nền mờ 9:16 (Blur Background)</option>
                  <option value="black_9_16">Nền đen 9:16 (Fit Black Bars)</option>
                </select>
              </div>

              {/* Anti-Copyright Rotation & Panning */}
              <div style={{ borderTop: "1px dashed rgba(255,255,255,0.08)", marginTop: "12px", paddingTop: "12px", display: "flex", flexDirection: "column", gap: "10px" }}>
                <div className="slider-group">
                  <div className="slider-label-row">
                    <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>XOAY GÓC SIÊU NHỎ:</span>
                    <span className="slider-value" style={{ fontSize: "12px" }}>{rotateAngle}°</span>
                  </div>
                  <input
                    type="range"
                    min="-2.0"
                    max="2.0"
                    step="0.1"
                    value={rotateAngle}
                    onChange={(e) => setRotateAngle(parseFloat(e.target.value))}
                  />
                </div>

                <div className="toggle-row" style={{ marginTop: "10px", borderTop: "1px dashed rgba(255,255,255,0.05)", paddingTop: "10px" }}>
                  <span style={{ fontSize: "13px" }}>Cắt & Bù mờ watermark đỉnh đầu:</span>
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={cleanWatermark}
                      onChange={(e) => {
                        const checked = e.target.checked;
                        setCleanWatermark(checked);
                        if (checked) {
                          setZoomLevel(0);
                        }
                      }}
                    />
                    <span className="slider-switch"></span>
                  </label>
                </div>

                {cleanWatermark && (
                  <div className="slider-group" style={{ marginTop: "8px" }}>
                    <div className="slider-label-row">
                      <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Tỷ lệ cắt đỉnh đầu:</span>
                      <span className="slider-value" style={{ fontSize: "12px" }}>{watermarkCropPct}%</span>
                    </div>
                    <input
                      type="range"
                      min="5"
                      max="25"
                      step="1"
                      value={watermarkCropPct}
                      onChange={(e) => setWatermarkCropPct(parseInt(e.target.value))}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Cover Old Subtitles with drawbox */}
            <div className="panel-section subtly-boxed">
              <div className="section-label">3. Che phụ để gốc (Drawbox)</div>

              <div className="toggle-row" style={{ paddingBottom: "10px" }}>
                <span style={{ fontSize: "14px" }}>Bật che sub bằng thanh màu:</span>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={coverSub}
                    onChange={(e) => setCoverSub(e.target.checked)}
                  />
                  <span className="slider-switch"></span>
                </label>
              </div>

              {coverSub && (
                <>
                  <div className="toggle-row" style={{ paddingBottom: "10px", borderBottom: "1px dashed rgba(255,255,255,0.08)" }}>
                    <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Co giãn tự động theo độ dài sub:</span>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={coverAutoFit}
                        onChange={(e) => setCoverAutoFit(e.target.checked)}
                      />
                      <span className="slider-switch"></span>
                    </label>
                  </div>

                  <div style={{ display: "flex", gap: "8px", marginBottom: "8px", marginTop: "8px" }}>
                    <div style={{ flex: 1 }}>
                      <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Màu thanh đè:</span>
                      <select
                        value={coverColor}
                        onChange={(e) => setCoverColor(e.target.value)}
                        style={{ padding: "6px", fontSize: "12px", marginTop: "4px" }}
                      >
                        <option value="inpaint">Tẩy chữ (Inpaint - Chậm)</option>
                        <option value="blur">Làm mờ (Gaussian Blur)</option>
                        <option value="gold">Vàng neon</option>
                        <option value="black">Đen tuyền</option>
                        <option value="white">Trắng</option>
                        <option value="red">Đỏ đậm</option>
                      </select>
                    </div>
                    <div style={{ flex: 1 }}>
                      <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Chiều cao (Offset px):</span>
                      <input
                        type="text"
                        value={coverHOffset}
                        onChange={(e) => setCoverHOffset(parseInt(e.target.value) || 40)}
                        style={{ padding: "6px", fontSize: "12px", marginTop: "4px", textAlign: "center" }}
                      />
                    </div>
                  </div>

                  <div className="slider-group">
                    <div className="slider-label-row">
                      <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Vị trí dọc (Y-pct):</span>
                      <span className="slider-value" style={{ fontSize: "12px" }}>{Math.round(coverYPos * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min="0.50"
                      max="0.95"
                      step="0.01"
                      value={coverYPos}
                      onChange={(e) => setCoverYPos(parseFloat(e.target.value))}
                    />
                  </div>

                  <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                    <div style={{ flex: 1 }} className="slider-group">
                      <div className="slider-label-row">
                        <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Độ rộng (%):</span>
                        <span className="slider-value" style={{ fontSize: "11px" }}>{Math.round(coverWPct * 100)}%</span>
                      </div>
                      <input
                        type="range"
                        min="0.10"
                        max="1.00"
                        step="0.05"
                        value={coverWPct}
                        onChange={(e) => setCoverWPct(parseFloat(e.target.value))}
                      />
                    </div>
                    <div style={{ flex: 1 }} className="slider-group">
                      <div className="slider-label-row">
                        <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Vị trí ngang (%):</span>
                        <span className="slider-value" style={{ fontSize: "11px" }}>{Math.round(coverXPct * 100)}%</span>
                      </div>
                      <input
                        type="range"
                        min="0.00"
                        max="0.90"
                        step="0.01"
                        value={coverXPct}
                        onChange={(e) => setCoverXPct(parseFloat(e.target.value))}
                      />
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Sound Controls */}
            <div className="panel-section subtly-boxed">
              <div className="section-label">4. Cấu hình âm thanh</div>

              <div className="toggle-row" style={{ paddingBottom: "10px", borderBottom: "1px dashed rgba(255,255,255,0.08)", marginBottom: "10px" }}>
                <span style={{ fontSize: "14px", fontWeight: "600" }}>Lồng tiếng (TTS Voiceover):</span>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={enableDubbing}
                    onChange={(e) => setEnableDubbing(e.target.checked)}
                  />
                  <span className="slider-switch"></span>
                </label>
              </div>

              <div className="slider-group">
                <div className="slider-label-row">
                  <span>Nhạc/Vocal gốc (BGM):</span>
                  <span className="slider-value">{Math.round(originalVol * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="1.0"
                  step="0.05"
                  value={originalVol}
                  onChange={(e) => setOriginalVol(parseFloat(e.target.value))}
                />
              </div>

              <div className="slider-group">
                <div className="slider-label-row">
                  <span>Giọng đọc TTS lồng tiếng:</span>
                  <span className="slider-value">{Math.round(ttsVol * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0.5"
                  max="1.5"
                  step="0.05"
                  value={ttsVol}
                  onChange={(e) => setTtsVol(parseFloat(e.target.value))}
                />
              </div>

              <div className="slider-group">
                <div className="slider-label-row">
                  <span>Vị trí chữ phụ đề (Y-Margin):</span>
                  <span className="slider-value">{subMarginV} px</span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="300"
                  step="5"
                  value={subMarginV}
                  onChange={(e) => setSubMarginV(parseInt(e.target.value))}
                />
              </div>

              {/* Auto Ducking Toggle */}
              <div className="toggle-row" style={{ marginTop: "12px", borderTop: "1px solid rgba(255, 255, 255, 0.05)", paddingTop: "10px" }}>
                <span style={{ fontSize: "14px" }}>Né tiếng nhạc nền (Auto-Ducking):</span>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={enableDucking}
                    onChange={(e) => setEnableDucking(e.target.checked)}
                  />
                  <span className="slider-switch"></span>
                </label>
              </div>

              {enableDucking && (
                <div className="slider-group" style={{ marginTop: "8px" }}>
                  <div className="slider-label-row">
                    <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Âm lượng gốc khi thuyết minh:</span>
                    <span className="slider-value" style={{ fontSize: "12px" }}>{Math.round(duckingVolume * 100)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="0.5"
                    step="0.01"
                    value={duckingVolume}
                    onChange={(e) => setDuckingVolume(parseFloat(e.target.value))}
                  />
                </div>
              )}
            </div>

            {/* Upload Custom Clone Voice */}
            <div className="panel-section subtly-boxed">
              <div className="section-label">5. Tải lên giọng clone (.wav)</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div>
                  <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>Tên giọng lồng (không dấu, viết liền):</span>
                  <input
                    type="text"
                    placeholder="Ví dụ: ronaldo, mi-na"
                    value={uploadVoiceName}
                    onChange={(e) => setUploadVoiceName(e.target.value)}
                    style={{ width: "100%", padding: "6px 8px", fontSize: "12px", border: "1px solid rgba(255, 255, 255, 0.1)", borderRadius: "4px", backgroundColor: "rgba(0,0,0,0.2)", color: "#fff" }}
                  />
                </div>
                <div>
                  <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>Chọn file âm thanh mẫu (WAV 3s-10s):</span>
                  <input
                    id="voice-file-upload"
                    type="file"
                    accept=".wav"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setUploadFile(e.target.files[0]);
                      }
                    }}
                    style={{ fontSize: "12px", width: "100%" }}
                  />
                </div>
                <button
                  onClick={handleVoiceUpload}
                  disabled={isUploadingVoice || !uploadFile || !uploadVoiceName.trim()}
                  className="btn-accent"
                  style={{
                    padding: "6px 12px",
                    fontSize: "12px",
                    marginTop: "6px",
                    cursor: (isUploadingVoice || !uploadFile || !uploadVoiceName.trim()) ? "not-allowed" : "pointer",
                    opacity: (isUploadingVoice || !uploadFile || !uploadVoiceName.trim()) ? 0.5 : 1,
                    backgroundColor: (isUploadingVoice || !uploadFile || !uploadVoiceName.trim()) ? "rgba(255, 255, 255, 0.05)" : "var(--color-primary)",
                    border: (isUploadingVoice || !uploadFile || !uploadVoiceName.trim()) ? "1px solid rgba(255, 255, 255, 0.1)" : "none",
                    borderRadius: "4px",
                    color: (isUploadingVoice || !uploadFile || !uploadVoiceName.trim()) ? "rgba(255, 255, 255, 0.3)" : "#fff",
                    fontWeight: "bold"
                  }}
                >
                  {isUploadingVoice ? "Đang tải..." : "Tải lên giọng đọc mẫu"}
                </button>
              </div>
            </div>

            {/* 6. Thiết Kế Giọng Nói tự chọn (Zero-shot) */}
            <div className="panel-section subtly-boxed">
              <div className="section-label">6. Thiết kế giọng (Zero-shot)</div>
              <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block", marginBottom: "6px" }}>
                Thiết kế giọng nói ngẫu nhiên bằng cách nhập từ khoá tiếng Anh mô tả (giới tính, độ tuổi, tông giọng, style...).
              </span>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div>
                  <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>Mô tả giọng (Instruct Prompt):</span>
                  <input
                    type="text"
                    placeholder="Ví dụ: female, high pitch, excited tone"
                    value={designerInstruct}
                    onChange={(e) => setDesignerInstruct(e.target.value)}
                    style={{ width: "100%", padding: "6px 8px", fontSize: "12px", border: "1px solid rgba(255, 255, 255, 0.1)", borderRadius: "4px", backgroundColor: "rgba(0,0,0,0.2)", color: "#fff" }}
                  />
                </div>

                <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                  <button
                    onClick={handleDesignerGenerate}
                    disabled={isDesigning || !designerInstruct.trim()}
                    className="btn-accent"
                    style={{
                      flex: 1,
                      padding: "6px 12px",
                      fontSize: "12px",
                      cursor: (isDesigning || !designerInstruct.trim()) ? "not-allowed" : "pointer",
                      opacity: (isDesigning || !designerInstruct.trim()) ? 0.5 : 1,
                      backgroundColor: (isDesigning || !designerInstruct.trim()) ? "rgba(255, 255, 255, 0.05)" : "var(--color-accent)",
                      border: (isDesigning || !designerInstruct.trim()) ? "1px solid rgba(255, 255, 255, 0.1)" : "none",
                      borderRadius: "4px",
                      color: (isDesigning || !designerInstruct.trim()) ? "rgba(255, 255, 255, 0.3)" : "#000",
                      fontWeight: "bold"
                    }}
                  >
                    {isDesigning ? "Đang sinh giọng..." : "Sinh thử giọng mới"}
                  </button>

                  {hasDesignedTemp && (
                    <button
                      onClick={handleTogglePlayDesignerPreview}
                      style={{
                        width: "32px",
                        height: "32px",
                        borderRadius: "4px",
                        border: "none",
                        backgroundColor: playingDesigner ? "#ff4a4a" : "#28a745",
                        color: "#fff",
                        cursor: "pointer",
                        fontSize: "14px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center"
                      }}
                      title={playingDesigner ? "Dừng nghe thử" : "Nghe thử giọng vừa sinh"}
                    >
                      {playingDesigner ? "⏹" : "▶"}
                    </button>
                  )}
                </div>

                {hasDesignedTemp && (
                  <div style={{ marginTop: "6px", borderTop: "1px dashed rgba(255,255,255,0.1)", paddingTop: "8px", display: "flex", flexDirection: "column", gap: "8px" }}>
                    <div>
                      <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>Ưng ý? Nhập tên để khóa & lưu giọng:</span>
                      <input
                        type="text"
                        placeholder="Ví dụ: giong-ngot-ngao"
                        value={designerSaveName}
                        onChange={(e) => setDesignerSaveName(e.target.value)}
                        style={{ width: "100%", padding: "6px 8px", fontSize: "12px", border: "1px solid rgba(255, 255, 255, 0.1)", borderRadius: "4px", backgroundColor: "rgba(0,0,0,0.2)", color: "#fff" }}
                      />
                    </div>
                    <button
                      onClick={handleDesignerSave}
                      disabled={isSavingDesign || !designerSaveName.trim()}
                      className="btn-accent"
                      style={{
                        padding: "6px 12px",
                        fontSize: "12px",
                        cursor: (isSavingDesign || !designerSaveName.trim()) ? "not-allowed" : "pointer",
                        opacity: (isSavingDesign || !designerSaveName.trim()) ? 0.5 : 1,
                        backgroundColor: (isSavingDesign || !designerSaveName.trim()) ? "rgba(255, 255, 255, 0.05)" : "var(--color-primary)",
                        border: (isSavingDesign || !designerSaveName.trim()) ? "1px solid rgba(255, 255, 255, 0.1)" : "none",
                        borderRadius: "4px",
                        color: (isSavingDesign || !designerSaveName.trim()) ? "rgba(255, 255, 255, 0.3)" : "#fff",
                        fontWeight: "bold"
                      }}
                    >
                      {isSavingDesign ? "Đang lưu..." : "Lưu & Khóa Giọng Sử Dụng"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* ================= COLUMN 2: CENTER WORKSPACE ================= */}
          <section className="editor-panel glass-panel">
            <div className="panel-title text-secondary" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <Type size={18} />
                Dịch & gán giọng lồng tiếng
              </div>
              {segments.length > 0 && (
                <button
                  onClick={() => {
                    setIsTimelineSynced(true);
                    addLog("Đã đồng bộ các câu thoại sang Timeline lồng tiếng dạng ngang!", "success");
                  }}
                  className={`btn ${isTimelineSynced ? "btn-accent" : "btn-primary"}`}
                  style={{ padding: "4px 10px", fontSize: "11px", display: "flex", alignItems: "center", gap: "4px" }}
                >
                  🔄 Đồng bộ Timeline
                </button>
              )}
            </div>

            {/* Draft Notification Banner */}
            {hasDraft && !downloadInfo && (
              <div className="subtly-boxed" style={{ margin: "16px 20px 0 20px", border: "1px dashed var(--color-primary)", display: "flex", justifyContent: "space-between", alignItems: "center", backgroundColor: "rgba(255, 215, 0, 0.05)", padding: "12px 16px", borderRadius: "8px" }}>
                <div style={{ color: "#fff", fontSize: "13px", display: "flex", alignItems: "center", gap: "6px" }}>
                  <span>💡</span> <span>Phát hiện bản nháp phiên làm việc trước chưa lưu. Bạn có muốn phục hồi không?</span>
                </div>
                <div style={{ display: "flex", gap: "8px" }}>
                  <button className="btn-accent" onClick={handleRestoreDraft} style={{ padding: "4px 12px", fontSize: "12px", height: "auto" }}>
                    Khôi phục
                  </button>
                  <button className="btn-secondary" onClick={handleDiscardDraft} style={{ padding: "4px 12px", fontSize: "12px", height: "auto" }}>
                    Bỏ qua
                  </button>
                </div>
              </div>
            )}

            {/* Subtitles Workspace area */}
            <div className="subtitles-workspace">
              {!downloadInfo ? (
                <div className="viewport-placeholder">
                  <FileVideo size={48} />
                  <h3>Chưa có video gốc</h3>
                  <p>Hãy dán link video Douyin/Bilibili ở cột bên trái và tải về trước khi tiến hành dịch phụ đề.</p>
                </div>
              ) : segments.length === 0 ? (
                <div className="viewport-placeholder">
                  <Sparkles size={48} />
                  <h3>Sẵn sàng phiên dịch</h3>
                  <p style={{ marginBottom: "16px" }}>Dự án "{downloadInfo.title}" đã được tải về local. Hãy cấu hình bên dưới và chạy phiên dịch.</p>

                  {/* Mode Selector */}
                  <div className="subtly-boxed" style={{ width: "100%", maxWidth: "420px", textAlign: "left", marginBottom: "20px", display: "flex", flexDirection: "column", gap: "12px" }}>
                    <div className="section-label" style={{ marginBottom: 0 }}>Cấu hình nhận diện giọng nói</div>

                    <div style={{ display: "flex", gap: "16px" }}>
                      <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "14px", cursor: "pointer" }}>
                        <input
                          type="radio"
                          name="transcribeMode"
                          value="local"
                          checked={transcribeMode === "local"}
                          onChange={() => setTranscribeMode("local")}
                        />
                        Local Whisper (Bản Free)
                      </label>
                      <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "14px", cursor: "pointer" }}>
                        <input
                          type="radio"
                          name="transcribeMode"
                          value="gemini"
                          checked={transcribeMode === "gemini"}
                          onChange={() => setTranscribeMode("gemini")}
                        />
                        Gemini API (Cloud AI)
                      </label>
                    </div>

                    {transcribeMode === "gemini" && (
                      <>
                        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                          <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>GEMINI API KEY:</span>
                          <input
                            type="password"
                            placeholder="Nhập API Key (AIzaSy...)"
                            value={geminiKey}
                            onChange={(e) => setGeminiKey(e.target.value)}
                            style={{ padding: "6px 10px", fontSize: "13px" }}
                          />
                        </div>

                        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                          <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>MODEL ĐƯỢC CHỌN:</span>
                          <select
                            value={geminiModel}
                            onChange={(e) => setGeminiModel(e.target.value)}
                            style={{ padding: "6px 10px", fontSize: "13px" }}
                          >
                            <option value="gemini-3.5-flash">Gemini 3.5 Flash (Recommended)</option>
                            <option value="gemini-3.1-pro">Gemini 3.1 Pro (Advanced)</option>
                            <option value="gemini-3-flash">Gemini 3 Flash</option>
                            <option value="gemini-3.1-flash-lite">Gemini 3.1 Flash Lite</option>
                            <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                            <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
                            <option value="custom">Nhập model tùy chọn khác...</option>
                          </select>
                        </div>

                        {geminiModel === "custom" && (
                          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                            <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>TÊN MODEL TÙY CHỌN:</span>
                            <input
                              type="text"
                              placeholder="Nhập chuỗi model khác (e.g. gemini-2.5-flash-001)"
                              value={customModel}
                              onChange={(e) => setCustomModel(e.target.value)}
                              style={{ padding: "6px 10px", fontSize: "13px" }}
                            />
                          </div>
                        )}

                        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                          <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>URL ENDPOINT KHÁC (TÙY CHỌN proxy/gateway):</span>
                          <div style={{ display: "flex", gap: "8px" }}>
                            <input
                              type="text"
                              placeholder="https://generativelanguage.googleapis.com"
                              value={geminiAPIEndpoint}
                              onChange={(e) => setGeminiAPIEndpoint(e.target.value)}
                              style={{ flex: 1, padding: "6px 10px", fontSize: "13px" }}
                            />
                            <button
                              type="button"
                              onClick={handleScanModels}
                              className="btn-accent"
                              style={{ padding: "6px 12.0px", fontSize: "12.0px", whiteSpace: "nowrap", height: "auto" }}
                            >
                              🔍 Quét Models
                            </button>
                          </div>
                        </div>
                      </>
                    )}

                    <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "4px" }}>
                        <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>NGÔN NGỮ GỐC VIDEO:</span>
                        <select
                          value={sourceLang}
                          onChange={(e) => setSourceLang(e.target.value)}
                          style={{ padding: "6px 10px", fontSize: "13px", backgroundColor: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "4px", color: "#fff" }}
                        >
                          <option value="auto">Tự động đoán (Auto)</option>
                          <option value="zh">Tiếng Trung (Chinese)</option>
                          <option value="en">Tiếng Anh (English)</option>
                          <option value="ko">Tiếng Hàn (Korean)</option>
                          <option value="ja">Tiếng Nhật (Japanese)</option>
                        </select>
                      </div>

                      {transcribeMode === "local" && (
                        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "4px" }}>
                          <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>MÔ HÌNH WHISPER:</span>
                          <select
                            value={whisperModel}
                            onChange={(e) => setWhisperModel(e.target.value)}
                            style={{ padding: "6px 10px", fontSize: "13px", backgroundColor: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "4px", color: "#fff" }}
                          >
                            <option value="base">base (Mặc định)</option>
                            <option value="small">small (Tốt)</option>
                            <option value="medium">medium (Rất tốt)</option>
                            <option value="large-v3">large-v3 (Chuyên nghiệp)</option>
                          </select>
                        </div>
                      )}
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "8px", marginBottom: "8px" }}>
                      <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>NGÔN NGỮ PHỤ ĐỀ DỊCH:</span>
                      <select
                        value={targetLang}
                        onChange={(e) => setTargetLang(e.target.value)}
                        style={{ padding: "6px 10px", fontSize: "13px", width: "100%", backgroundColor: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "4px", color: "#fff" }}
                      >
                        <option value="vi">Tiếng Việt (Vietsub)</option>
                        <option value="en">Tiếng Anh (Engsub)</option>
                        <option value="ko">Tiếng Hàn (Kor-sub)</option>
                        <option value="zh">Tiếng Trung (Chisub)</option>
                        <option value="ja">Tiếng Nhật (Japasub)</option>
                      </select>
                    </div>
                  </div>

                  <button
                    className="btn-primary"
                    onClick={handleTranscribe}
                    disabled={isTranscribing}
                    style={{ padding: "12px 24px" }}
                  >
                    {isTranscribing ? (
                      <>
                        <div className="spinner" /> Phiên âm Whisper...
                      </>
                    ) : (
                      <>
                        <Sparkles size={16} /> Phiên âm & Dịch Phụ Đề
                      </>
                    )}
                  </button>
                </div>
              ) : (
                <>
                  {/* Default Gender Voice Mapping Setting */}
                  <div className="subtly-boxed" style={{ display: "flex", gap: "16px", marginBottom: "8px" }}>
                    <div style={{ flex: 1 }}>
                      <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>GIỌNG NAM MẶC ĐỊNH:</span>
                      <select
                        value={defaultMaleVoice}
                        onChange={(e) => {
                          setDefaultMaleVoice(e.target.value);

                          addLog(`Thay đổi giọng Nam mặc định thành ${voices.find(v => v.id === e.target.value)?.name}`, "info");
                        }}
                        style={{ marginTop: "4px" }}
                      >
                        {voices.filter(v => v.gender === "male").map(v => (
                          <option key={v.id} value={v.id}>{v.name}</option>
                        ))}
                        {voices.filter(v => v.type === "preset" && v.gender === "male").length === 0 && (
                          <option value="instruct_male_low">Nam trầm (Instruct)</option>
                        )}
                      </select>
                    </div>

                    <div style={{ flex: 1 }}>
                      <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "600" }}>GIỌNG NỮ MẶC ĐỊNH:</span>
                      <select
                        value={defaultFemaleVoice}
                        onChange={(e) => {
                          setDefaultFemaleVoice(e.target.value);
                          addLog(`Thay đổi giọng Nữ mặc định thành ${voices.find(v => v.id === e.target.value)?.name}`, "info");
                        }}
                        style={{ marginTop: "4px" }}
                      >
                        {voices.filter(v => v.gender === "female").map(v => (
                          <option key={v.id} value={v.id}>{v.name}</option>
                        ))}
                        {voices.filter(v => v.type === "preset" && v.gender === "female").length === 0 && (
                          <option value="instruct_female_young">Nữ trẻ (Instruct)</option>
                        )}
                      </select>
                    </div>
                  </div>

                  {/* Subtitle Lists */}
                  {segments.map((seg) => {
                    const selectId = segmentVoices[`seg_${seg.id}`] || (seg.gender === "male" ? defaultMaleVoice : defaultFemaleVoice);
                    const selectedVoiceObj = voices.find(v => v.id === selectId);
                    const isClone = selectedVoiceObj?.type === "clone";

                    return (
                      <div key={seg.id} className="subtitle-item-card">
                        <div className="sub-meta-row">
                          <span className="sub-times">{seg.start.toFixed(2)}s ➔ {seg.end.toFixed(2)}s</span>
                          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                            <span className={`speaker-badge ${seg.gender === "male" ? "gender-male" : "gender-female"}`}>
                              <User size={10} />
                              {seg.speaker_id ? seg.speaker_id.toUpperCase().replace("_", " ") : (seg.gender === "male" ? "GIỌNG NAM" : "GIỌNG NỮ")}
                            </span>

                            {/* Pick voice speaker override */}
                            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                              <select
                                value={selectId}
                                onChange={(e) => handleSegmentVoiceChange(seg.id, e.target.value)}
                                style={{ padding: "2px 8px", width: "160px", fontSize: "12px", background: "none" }}
                              >
                                <option value="">(Chọn giọng lồng tiếng)</option>
                                {voices.map((v) => (
                                  <option key={v.id} value={v.id}>{v.name}</option>
                                ))}
                              </select>

                              {isClone && (
                                <button
                                  onClick={() => togglePlayVoice(selectId)}
                                  style={{
                                    padding: "2px 6px",
                                    fontSize: "11px",
                                    cursor: "pointer",
                                    background: playingVoiceId === selectId ? "#ef4444" : "#10b981",
                                    color: "#fff",
                                    border: "none",
                                    borderRadius: "4px",
                                    fontWeight: "bold",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    minWidth: "24px"
                                  }}
                                  title="Nghe thử giọng"
                                >
                                  {playingVoiceId === selectId ? "⏹" : "▶"}
                                </button>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="orig-text">{seg.original_text}</div>

                        <div className="edited-text-area">
                          <textarea
                            rows={2}
                            value={seg.text}
                            onChange={(e) => handleSegmentTextChange(seg.id, e.target.value)}
                          />
                        </div>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          </section>

          {/* ================= COLUMN 3: PREVIEW PORT & EXPORT ================= */}
          <section className="preview-panel glass-panel">
            <div className="panel-title text-accent">
              <Eye size={18} />
              Màn hình hiển thị
            </div>
            <div className="tab-container" style={{ borderBottom: "none", marginBottom: "14px" }}>
              <div className="segmented-tabs-container">
                <button
                  className={`segmented-tab-btn ${activePlayerTab === "original" ? "active" : ""}`}
                  onClick={() => setActivePlayerTab("original")}
                >
                  Video gốc
                </button>
                <button
                  className={`segmented-tab-btn ${activePlayerTab === "dubbed" ? "active" : ""}`}
                  onClick={() => setActivePlayerTab("dubbed")}
                  disabled={!finalVideo}
                >
                  Video dubbed {finalVideo && <span className="badge-neon" style={{ marginLeft: "4px" }}>Xong</span>}
                </button>
              </div>
            </div>

            {/* Media Player */}
            <div className="media-viewport" style={{ display: "flex", justifyContent: "center", alignItems: "center", position: "relative", overflow: "hidden" }}>
              {activePlayerTab === "original" && downloadInfo ? (
                <div style={{ position: "relative", height: "100%", aspectRatio: videoAspectRatio ? String(videoAspectRatio) : "auto", display: "flex", alignItems: "center", justifyContent: "center", containerType: "size" }}>
                  <video
                    src={`${BACKEND_URL}/api/preview/${downloadInfo.filename}`}
                    controls
                    style={{ width: "100%", height: "100%", objectFit: "contain" }}
                    onLoadedMetadata={(e) => setVideoAspectRatio(e.currentTarget.videoWidth / e.currentTarget.videoHeight)}
                    onTimeUpdate={(e) => setPlayerTime(e.currentTarget.currentTime)}
                  />
                  {coverSub && (
                    <div
                      style={{
                        position: "absolute",
                        left: `${coverXPct * 100}%`,
                        width: `${coverWPct * 100}%`,
                        top: `${coverYPos * 100}%`,
                        height: `${(coverHOffset / 720) * 100}%`,
                        backgroundColor: coverColor === "inpaint" ? "rgba(0, 0, 0, 0.25)" : (coverColor === "blur" ? "rgba(0, 0, 0, 0.4)" : (coverColor === "gold" ? "#ffff00" : (coverColor === "black" ? "#000000" : (coverColor === "white" ? "#ffffff" : coverColor)))),
                        border: coverColor === "inpaint" ? "2px dashed rgba(255, 255, 255, 0.4)" : "none",
                        backdropFilter: coverColor === "blur" ? "blur(10px)" : "none",
                        WebkitBackdropFilter: coverColor === "blur" ? "blur(10px)" : "none",
                        opacity: 0.95,
                        pointerEvents: "none",
                        zIndex: 2
                      }}
                    />
                  )}
                  {(() => {
                    const activeSegment = segments.find(seg => playerTime >= seg.start && playerTime <= seg.end);
                    if (!activeSegment) return null;
                    const computedFontSize = 13; // Match backend fontSize
                    const fontSizeCqh = (computedFontSize / 288) * 100; // Match baseline scaling
                    
                    // Dynamically position below original subtitle range
                    const sub_bottom = coverYPos * 720 + coverHOffset;
                    const rem_h = Math.max(0, 720 - sub_bottom);
                    const margin_v_ref = Math.max(6, rem_h * 0.25);
                    const bottomPct = (margin_v_ref / 720) * 100;
                    
                    return (
                      <div
                        style={{
                          position: "absolute",
                          left: "5%",
                          width: "90%",
                          top: "auto",
                          bottom: `${bottomPct}%`,
                          height: "auto",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          pointerEvents: "none",
                          zIndex: 3,
                          color: "#ffffff",
                          fontSize: `${fontSizeCqh}cqh`,
                          fontWeight: "bold",
                          textAlign: "center",
                          textShadow: "1px 1px 2px #000, -1px -1px 2px #000, 1px -1px 2px #000, -1px 1px 2px #000",
                          padding: "4px",
                          overflow: "hidden"
                        }}
                      >
                        <div style={{ whiteSpace: "pre-line", maxHeight: "100%", overflow: "hidden" }}>
                          {activeSegment.text}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              ) : activePlayerTab === "dubbed" && finalVideo ? (
                <div style={{ position: "relative", height: "100%", aspectRatio: videoAspectRatio ? String(videoAspectRatio) : "auto", display: "flex", alignItems: "center", justifyContent: "center", containerType: "size" }}>
                  <video
                    src={`${BACKEND_URL}/api/preview/${finalVideo.filename}`}
                    controls
                    style={{ width: "100%", height: "100%", objectFit: "contain" }}
                    onLoadedMetadata={(e) => setVideoAspectRatio(e.currentTarget.videoWidth / e.currentTarget.videoHeight)}
                    onTimeUpdate={(e) => setPlayerTime(e.currentTarget.currentTime)}
                  />
                  {coverSub && (
                    <div
                      style={{
                        position: "absolute",
                        left: `${coverXPct * 100}%`,
                        width: `${coverWPct * 100}%`,
                        top: `${coverYPos * 100}%`,
                        height: `${(coverHOffset / 720) * 100}%`,
                        backgroundColor: coverColor === "blur" ? "rgba(0, 0, 0, 0.4)" : (coverColor === "gold" ? "#ffff00" : (coverColor === "black" ? "#000000" : (coverColor === "white" ? "#ffffff" : coverColor))),
                        backdropFilter: coverColor === "blur" ? "blur(10px)" : "none",
                        WebkitBackdropFilter: coverColor === "blur" ? "blur(10px)" : "none",
                        opacity: 0.95,
                        pointerEvents: "none",
                        zIndex: 2
                      }}
                    />
                  )}
                </div>
              ) : (
                <div className="viewport-placeholder">
                  <FileVideo size={40} />
                  <span>Không có nguồn video hiển thị</span>
                </div>
              )}
            </div>

            {/* Action trigger compile button */}
            <button
              className="btn-primary"
              onClick={handleDubAndEdit}
              disabled={isDubbing || !downloadInfo || ((enableDubbing || enableSubtitles) && segments.length === 0)}
              style={{ width: "100%", padding: "14px 20px" }}
            >
              {isDubbing ? (
                <>
                  <div className="spinner" style={{ marginRight: "8px" }} /> Đang chạy Omni TTS & FFmpeg...
                </>
              ) : (
                <>
                  <Video size={18} /> Lồng tiếng & Xuất Video Lách
                </>
              )}
            </button>

            {/* Terminal Console Logs */}
            <div style={{ marginTop: "12px" }}>
              <div className="tab-container" style={{ borderBottom: "none", marginBottom: "8px" }}>
                <div className="segmented-tabs-container">
                  <button
                    className={`segmented-tab-btn ${activeConsoleTab === "logs" ? "active" : ""}`}
                    onClick={() => setActiveConsoleTab("logs")}
                  >
                    Nhật ký xử lý (Logs)
                  </button>
                </div>
              </div>
              <div className="console-output" ref={consoleContainerRef}>
                {logs.map((log, idx) => (
                  <div key={idx} className={`log-line log-${log.type}`}>
                    [{log.time}] {log.text}
                  </div>
                ))}
              </div>
            </div>
          </section>

        </main>
      ) : (
        <div className="timeline-page-container" style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "16px", height: "calc(100vh - 140px)", overflow: "hidden" }}>
          {/* Top Half: Video Player Center & Cover-up preview controls */}
          <div style={{ flex: 1.2, display: "flex", gap: "16px", minHeight: 0 }}>
            {/* Left: Video Player */}
            <div style={{ flex: 1.5, background: "#000", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.08)", overflow: "hidden", display: "flex", justifyContent: "center", alignItems: "center", position: "relative" }}>
              {downloadInfo ? (
                <div style={{ position: "relative", height: "100%", aspectRatio: videoAspectRatio ? String(videoAspectRatio) : "auto", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <video
                    src={`${BACKEND_URL}/api/preview/${activePlayerTab === "dubbed" && finalVideo ? finalVideo.filename : downloadInfo.filename}`}
                    controls
                    style={{ width: "100%", height: "100%", objectFit: "contain" }}
                    onLoadedMetadata={(e) => setVideoAspectRatio(e.currentTarget.videoWidth / e.currentTarget.videoHeight)}
                    onTimeUpdate={(e) => setPlayerTime(e.currentTarget.currentTime)}
                  />
                  {coverSub && (
                    <div
                      style={{
                        position: "absolute",
                        left: `${coverXPct * 100}%`,
                        width: `${coverWPct * 100}%`,
                        top: `${coverYPos * 100}%`,
                        height: `${(coverHOffset / 720) * 100}%`,
                        backgroundColor: coverColor === "gold" ? "#ffff00" : (coverColor === "black" ? "#000000" : (coverColor === "white" ? "#ffffff" : coverColor)),
                        opacity: 0.95,
                        pointerEvents: "none",
                        zIndex: 2
                      }}
                    />
                  )}
                  {activePlayerTab !== "dubbed" && (() => {
                    const activeSegment = segments.find(seg => playerTime >= seg.start && playerTime <= seg.end);
                    if (!activeSegment) return null;
                    return (
                      <div
                        style={{
                          position: "absolute",
                          left: coverSub ? `${coverXPct * 100}%` : "5%",
                          width: coverSub ? `${coverWPct * 100}%` : "90%",
                          top: coverSub ? `${coverYPos * 100}%` : "auto",
                          bottom: coverSub ? "auto" : `${(subMarginV / 720) * 100}%`,
                          height: coverSub ? `${(coverHOffset / 720) * 100}%` : "auto",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          pointerEvents: "none",
                          zIndex: 3,
                          color: coverSub ? (["gold", "yellow", "white"].includes(coverColor) ? "#000000" : "#ffff00") : "#ffffff",
                          fontSize: coverSub ? `${Math.max(10, Math.min(24, coverHOffset * 0.35))}px` : "16px",
                          fontWeight: "bold",
                          textAlign: "center",
                          textShadow: coverSub ? "none" : "1px 1px 2px #000, -1px -1px 2px #000, 1px -1px 2px #000, -1px 1px 2px #000",
                          padding: "4px"
                        }}
                      >
                        <div style={{ whiteSpace: "pre-line" }}>
                          {activeSegment.text}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px", alignItems: "center", color: "var(--text-muted)" }}>
                  <FileVideo size={48} />
                  <span>Hãy tải video ở Studio trước</span>
                </div>
              )}
            </div>

            {/* Right: Controls & Overlay parameters */}
            <div className="glass-panel" style={{ flex: 1, padding: "16px", display: "flex", flexDirection: "column", gap: "16px", overflowY: "auto" }}>
              <div style={{ fontSize: "14px", fontWeight: "bold", borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "6px" }} className="text-accent">
                Căn Chỉnh Vùng Che Phụ Đề
              </div>
              {/* Subtitle Cover panel completely removed per user request */}

              {/* Selected Segment Editor Panel */}
              {selectedTimelineSegIndex !== null && segments[selectedTimelineSegIndex] && (
                <div
                  style={{
                    borderTop: "1px dashed rgba(255,255,255,0.12)",
                    paddingTop: "16px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px"
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: "11px", fontWeight: "bold", color: "var(--color-primary)" }}>HIỆU CHỈNH PHÂN ĐOẠN ĐÃ CHỌN</span>
                    <button
                      onClick={() => setSelectedTimelineSegIndex(null)}
                      style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: "11px", padding: 0 }}
                    >
                      Đóng [X]
                    </button>
                  </div>
                  <div>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Nội dung thoại:</span>
                    <textarea
                      value={segments[selectedTimelineSegIndex].text}
                      onChange={(e) => {
                        const txt = e.target.value;
                        setSegments(prev => {
                          const next = [...prev];
                          next[selectedTimelineSegIndex!] = { ...next[selectedTimelineSegIndex!], text: txt };
                          return next;
                        });
                      }}
                      style={{
                        width: "100%",
                        height: "55px",
                        padding: "8px",
                        fontSize: "12px",
                        marginTop: "4px",
                        borderRadius: "4px",
                        background: "rgba(255,255,255,0.06)",
                        border: "1px solid rgba(255,255,255,0.12)",
                        color: "#fff",
                        resize: "none"
                      }}
                    />
                  </div>
                  <div style={{ display: "flex", gap: "8px" }}>
                    <div style={{ flex: 1 }}>
                      <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Bắt đầu (giây):</span>
                      <input
                        type="number"
                        step="0.05"
                        value={parseFloat(segments[selectedTimelineSegIndex].start.toFixed(3))}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value) || 0;
                          setSegments(prev => {
                            const next = [...prev];
                            next[selectedTimelineSegIndex!] = { ...next[selectedTimelineSegIndex!], start: val };
                            return next;
                          });
                        }}
                        style={{ width: "100%", padding: "5px 6px", fontSize: "12px", marginTop: "4px", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "#fff", borderRadius: "4px" }}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Kết thúc (giây):</span>
                      <input
                        type="number"
                        step="0.05"
                        value={parseFloat(segments[selectedTimelineSegIndex].end.toFixed(3))}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value) || 0;
                          setSegments(prev => {
                            const next = [...prev];
                            next[selectedTimelineSegIndex!] = { ...next[selectedTimelineSegIndex!], end: val };
                            return next;
                          });
                        }}
                        style={{ width: "100%", padding: "5px 6px", fontSize: "12px", marginTop: "4px", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "#fff", borderRadius: "4px" }}
                      />
                    </div>
                  </div>

                  <div>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Giọng lồng tiếng:</span>
                    <select
                      value={segmentVoices[selectedTimelineSegIndex] || (segments[selectedTimelineSegIndex].gender === "male" ? defaultMaleVoice : defaultFemaleVoice)}
                      onChange={(e) => {
                        const voiceId = e.target.value;
                        setSegmentVoices(prev => ({
                          ...prev,
                          [selectedTimelineSegIndex!]: voiceId
                        }));
                      }}
                      style={{ width: "100%", padding: "6px", fontSize: "12px", marginTop: "4px", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "#fff", borderRadius: "4px" }}
                    >
                      {voices.map((v) => (
                        <option key={v.id} value={v.id}>{v.name || v.id}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {/* Player tab selection in timeline view */}
              <div style={{ marginTop: "auto", borderTop: "1px dashed rgba(255,255,255,0.1)", paddingTop: "12px", display: "flex", gap: "8px" }}>
                <button className={`btn-primary`} style={{ flex: 1, padding: "8px", fontSize: "12px" }} onClick={() => setActivePlayerTab("original")}>Video gốc</button>
                <button className={`btn-accent`} style={{ flex: 1, padding: "8px", fontSize: "12px" }} onClick={() => setActivePlayerTab("dubbed")} disabled={!finalVideo}>Video dubbed</button>
              </div>
            </div>
          </div>

          {/* Bottom Half: Full-width Timeline */}
          <div className="glass-panel" style={{ flex: 1, padding: "16px", display: "flex", flexDirection: "column", minHeight: 0 }}>
            {!isTimelineSynced ? (
              <div className="viewport-placeholder" style={{ flex: 1 }}>
                <Sparkles size={48} style={{ color: "var(--color-primary)" }} />
                <h3>Chưa đồng bộ Timeline</h3>
                <p style={{ marginBottom: "16px" }}>Bấm nút "🔄 Đồng bộ Timeline" tại Phòng Biên Tập để hiển thị dòng thời gian các câu thoại.</p>
                <button className="btn-primary" onClick={() => setActiveAppTab("studio")}>Quay lại Phòng Biên Tập</button>
              </div>
            ) : downloadInfo ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px", height: "100%", overflow: "hidden" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.06)", paddingBottom: "6px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#10b981" }} />
                    <span style={{ fontSize: "12px", color: "var(--color-primary)", fontWeight: "bold", letterSpacing: "0.05em" }}>POST-PRODUCTION TIMELINE TRACKS</span>
                  </div>
                  <span style={{ fontSize: "11px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>Thời lượng: {downloadInfo.duration.toFixed(1)}s</span>
                </div>

                <div style={{ flex: 1, overflowX: "auto", overflowY: "auto", paddingBottom: "8px" }}>
                  <div style={{ minWidth: "1200px", position: "relative", display: "flex", flexDirection: "column", gap: "8px" }}>
                    {/* Ruler ticks row */}
                    <div style={{ height: "20px", borderBottom: "1px solid rgba(255,255,255,0.1)", position: "relative" }}>
                      {(() => {
                        const ticks = [];
                        const step = downloadInfo.duration > 300 ? 60 : (downloadInfo.duration > 120 ? 30 : (downloadInfo.duration > 60 ? 10 : 2));
                        for (let i = 0; i <= downloadInfo.duration; i += step) {
                          ticks.push(i);
                        }
                        return ticks.map(t => (
                          <span key={t} style={{ position: "absolute", left: `${(t / downloadInfo.duration) * 100}%`, fontSize: "10px", color: "var(--text-muted)", transform: "translateX(-50%)", fontFamily: "var(--font-mono)" }}>
                            {t}s
                          </span>
                        ));
                      })()}
                    </div>

                    {/* Track 1: Original Video Track */}
                    <div style={{ display: "flex", alignItems: "center", height: "30px", background: "rgba(255,255,255,0.01)", borderRadius: "4px" }}>
                      <span style={{ width: "90px", minWidth: "90px", fontSize: "10px", color: "var(--text-muted)", fontWeight: "600", borderRight: "1px solid rgba(255,255,255,0.08)", paddingRight: "8px" }}>
                        📹 VIDEO
                      </span>
                      <div style={{ flex: 1, position: "relative", height: "100%" }}>
                        <div style={{ position: "absolute", left: 0, width: "100%", height: "70%", top: "15%", background: "rgba(99, 102, 241, 0.08)", border: "1px dashed rgba(99, 102, 241, 0.2)", borderRadius: "3px" }} />
                      </div>
                    </div>

                    {/* Dynamic tracks for each speaker */}
                    {(() => {
                      const speakers = Array.from(new Set(segments.map(s => s.speaker_id || s.gender || "GIỌNG ĐỌC")));
                      return speakers.map(spk => {
                        const trackColor = spk.toLowerCase().includes("male") || spk.toLowerCase().includes("nam") ? "rgba(14, 165, 233, 0.12)" : (spk.toLowerCase().includes("female") || spk.toLowerCase().includes("nữ") ? "rgba(236, 72, 153, 0.12)" : "rgba(16, 185, 129, 0.12)");
                        const borderColor = spk.toLowerCase().includes("male") || spk.toLowerCase().includes("nam") ? "rgba(14, 165, 233, 0.4)" : (spk.toLowerCase().includes("female") || spk.toLowerCase().includes("nữ") ? "rgba(236, 72, 153, 0.4)" : "rgba(16, 185, 129, 0.4)");
                        const textColor = spk.toLowerCase().includes("male") || spk.toLowerCase().includes("nam") ? "#38bdf8" : (spk.toLowerCase().includes("female") || spk.toLowerCase().includes("nữ") ? "#f472b6" : "#34d399");
                        const label = spk.toUpperCase();

                        return (
                          <div key={spk} style={{ display: "flex", alignItems: "center", height: "32px", background: "rgba(255,255,255,0.01)", borderRadius: "4px" }}>
                            <span style={{ width: "90px", minWidth: "90px", fontSize: "10px", color: textColor, fontWeight: "600", borderRight: "1px solid rgba(255,255,255,0.08)", paddingRight: "8px" }}>
                              🎙️ {label}
                            </span>
                            <div style={{ flex: 1, position: "relative", height: "100%" }}>
                              {segments
                                .map((seg, globalIdx) => ({ seg, globalIdx }))
                                .filter(item => (item.seg.speaker_id || item.seg.gender || "GIỌNG ĐỌC") === spk)
                                .map(({ seg, globalIdx }) => {
                                  const leftPct = (seg.start / downloadInfo.duration) * 100;
                                  const widthPct = ((seg.end - seg.start) / downloadInfo.duration) * 100;
                                  const isSelected = selectedTimelineSegIndex === globalIdx;
                                  return (
                                    <div
                                      key={globalIdx}
                                      style={{
                                        position: "absolute",
                                        left: `${leftPct}%`,
                                        width: `${widthPct}%`,
                                        height: "80%",
                                        top: "10%",
                                        background: trackColor,
                                        border: isSelected ? "1.5px solid #ffd700" : `1px solid ${borderColor}`,
                                        boxShadow: isSelected ? "0 0 10px rgba(255, 215, 0, 0.6)" : "none",
                                        borderRadius: "4px",
                                        fontSize: "9px",
                                        color: "#fff",
                                        display: "flex",
                                        alignItems: "center",
                                        overflow: "hidden",
                                        cursor: "pointer",
                                        userSelect: "none"
                                      }}
                                      onClick={() => setSelectedTimelineSegIndex(globalIdx)}
                                      title={`[Thoại ${globalIdx + 1} - Click để sửa] [${seg.start.toFixed(2)}s - ${seg.end.toFixed(2)}s] ${seg.text}`}
                                    >
                                      {/* Left resize handle */}
                                      <div
                                        style={{ width: "6px", height: "100%", cursor: "w-resize", zIndex: 10, background: isSelected ? "rgba(255,215,0,0.2)" : "transparent" }}
                                        onMouseDown={(e) => handleTimelineMouseDown(e, globalIdx, "resize-left")}
                                      />
                                      {/* Middle label text & drag area */}
                                      <div
                                        style={{ flex: 1, padding: "0 4px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "grab", height: "100%", display: "flex", alignItems: "center" }}
                                        onMouseDown={(e) => handleTimelineMouseDown(e, globalIdx, "move")}
                                      >
                                        {seg.text}
                                      </div>
                                      {/* Right resize handle */}
                                      <div
                                        style={{ width: "6px", height: "100%", cursor: "e-resize", zIndex: 10, background: isSelected ? "rgba(255,215,0,0.2)" : "transparent" }}
                                        onMouseDown={(e) => handleTimelineMouseDown(e, globalIdx, "resize-right")}
                                      />
                                    </div>
                                  );
                                })}
                            </div>
                          </div>
                        );
                      });
                    })()}
                  </div>
                </div>
              </div>
            ) : (
              <div className="viewport-placeholder" style={{ flex: 1 }}>
                <FileVideo size={48} />
                <span>Nạp video ở Studio để xem dòng thời gian</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
