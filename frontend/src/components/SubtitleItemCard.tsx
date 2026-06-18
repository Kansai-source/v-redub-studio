import { memo } from "react";
import { User } from "lucide-react";
import type { Voice, Segment } from "../types";

export const SubtitleItemCard = memo(function SubtitleItemCard({
  seg,
  selectId,
  voices,
  playingVoiceId,
  togglePlayVoice,
  handleSegmentVoiceChange,
  handleSegmentTextChange,
  isActive
}: {
  seg: Segment;
  selectId: string;
  voices: Voice[];
  playingVoiceId: string | null;
  togglePlayVoice: (voiceId: string) => void;
  handleSegmentVoiceChange: (segId: number, voiceId: string) => void;
  handleSegmentTextChange: (id: number, val: string) => void;
  isActive?: boolean;
}) {
  const selectedVoiceObj = voices.find(v => v.id === selectId);
  const isClone = selectedVoiceObj?.type === "clone";

  return (
    <div 
      className={`subtitle-item-card subtitle-item-card-index-${seg.id} ${isActive ? "active" : ""}`}
      style={isActive ? { border: "1.5px solid #00f5ff", boxShadow: "0 0 10px rgba(0, 245, 255, 0.45)", backgroundColor: "rgba(0, 245, 255, 0.04)" } : undefined}
    >
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
});
