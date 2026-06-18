export interface Voice {
  id: string;
  name: string;
  type: string;
  gender: string;
  instruct?: string;
  file_path?: string;
}

export interface Segment {
  id: number;
  start: number;
  end: number;
  original_text: string;
  text: string;
  gender: string;
  speaker_id?: string;
}

export interface LogLine {
  text: string;
  type: "info" | "success" | "warning" | "error";
  time: string;
}

export interface DownloadInfo {
  file_path: string;
  filename: string;
  title: string;
  duration: number;
  thumbnail: string;
  url: string;
  audio_path?: string;
}

export interface FinalVideo {
  filename: string;
  video_path: string;
  size_bytes: number;
  url: string;
}
