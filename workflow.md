# Sơ đồ Quy Trình (Workflow Diagram) - V-reDub Studio

Dưới đây là sơ đồ chi tiết về luồng xử lý video, âm thanh, dịch thuật và lách bản quyền nghệ thuật trong hệ thống V-reDub Studio từ tệp tin gốc cho đến video đầu ra cuối cùng.

## Sơ đồ luồng xử lý (Mermaid Diagram)

```mermaid
graph TD
    %% Định nghĩa các lớp màu sắc (Styling)
    classDef inputColor fill:#4f5d75,stroke:#2d3142,stroke-width:2px,color:#fff;
    classDef processColor fill:#2d87bb,stroke:#1a5f8a,stroke-width:2px,color:#fff;
    classDef editColor fill:#f15a24,stroke:#c0392b,stroke-width:2px,color:#fff;
    classDef outputColor fill:#27ae60,stroke:#1e8449,stroke-width:2px,color:#fff;

    %% Luồng Dữ liệu Đầu vào (Input Block)
    subgraph INPUT ["1. NGUỒN VÀO (VIDEO INPUT)"]
        A1["Tải Video URL (YouTube / Bilibili)"]
        A2["Tải Video Cục Bộ (Local MP4)"]
        COOKIES("Tệp cookies.txt (Vượt chặn & Lấy độ phân giải 1080p)")
        
        A1 -->|Đọc Cookies| COOKIES
        A2 --> B["Thư mục Tạm (TEMP_DIR)"]
        A1 --> B
    end
    class A1,A2,COOKIES,B inputColor;

    %% Luồng Phiên âm & Dịch thuật (Transcription & Translation)
    subgraph TRANSLATION ["2. PHÂN TÁCH & DỊCH THUẬT"]
        C["Trích xuất Audio (ffmpeg -orig.wav)"]
        B --> C
        
        C --> D{"LỰA CHỌN CHẾ ĐỘ DỊCH"}
        
        %% Chế độ Cloud Gemini
        D -->|Cloud Mode| E["Gặp Gemini API (Inline Base64 MP3)"]
        E --> E1["Gemini nhận diện nhân vật & Dịch sang Target Lang"]
        E1 --> E2["Prompts chia nhỏ câu thoại (3 - 12 từ)"]
        
        %% Chế độ Local Whisper
        D -->|Local Mode| F["Local Whisper Model (base/small/medium/large-v3)"]
        F -->|Source Lang| F1["Quét lời thoại & Trích xuất Timestamps"]
        F1 --> F2["Google Translate API (Đa ngôn ngữ dịch)"]
        F2 --> F3["Thuật toán Phân tách Câu thoại dài (split_long_segment)"]
        
        E2 --> G["Danh sách Phân đoạn Hội thoại (Segments JSON)"]
        F3 --> G
    end
    class C,D,E,E1,E2,F,F1,F2,F3,G processColor;

    %% Luồng Dựng phim & Biên tập (Interactive Studio Timeline)
    subgraph EDITING ["3. BIÊN TẬP & CÀI ĐẶT (HUMAN-IN-THE-LOOP)"]
        G --> H["Giao diện Dòng thời gian (NLE Timeline)"]
        
        %% Tương tác điều chỉnh
        H --> I1["Kéo thả chỉnh mốc Giây (Start/End)"]
        H --> I2["Gán nhân vật / Tạo giọng mới (Zero-shot Voice)"]
        H --> I3["Cắn lề Zoom (Thụt trên/dưới) dọn Watermark"]
        H --> I4["Kéo vị trí/Cỡ chữ Sub Việt nằm dưới phụ đề gốc"]
        
        I1 --> J["Cấu hình Kết xuất (Export Options)"]
        I2 --> J
        I3 --> J
        I4 --> J
    end
    class H,I1,I2,I3,I4,J editColor;

    %% Luồng Kết xuất & Output (Render Pipe)
    subgraph RENDER ["4. KẾT XUẤT PHIM (RENDER PIPELINE)"]
        J --> K["Hậu phương FFmpeg Engine"]
        
        %% Bẻ luồng xử lý
        K --> L1["Dynamic Watermark Crop-Blur (Shave top / shave bottom)"]
        K --> L2["Chạy lồng tiếng (TTS Speed Fitting & Ducking Volume)"]
        K --> L3["In phụ đề ASS mềm mại dưới chân gốc (Soft Shadow)"]
        
        L1 --> M["Bộ mã hóa GPU Nvidia NVENC (Gác CPU libx264 Fallback)"]
        L2 --> M
        L3 --> M
        
        M --> N["VIDEO ĐẦU RA HOÀN CHỈNH (Re-up & Lách bản quyền)"]
    end
    class K,L1,L2,L3,M,N outputColor;
```

## Chi tiết các bước hoạt động trong Workflow

1. **Bước 1 (Input):** Video được tiếp nhận từ URL hoặc ổ đĩa. Trình tải `yt-dlp` tự dò tìm `cookies.txt` tại gốc để vượt qua mã hóa, xác minh độ tuổi của YouTube hoặc giữ độ phân giải tối ưu của Bilibili.
2. **Bước 2 (Phân tách & dịch thuật):** Audio gốc được giải nén.
   * **Gemini (Cloud):** Nén MP3 24kbps cực nhẹ truyền trực tiếp inline giúp trả về phân vai thoại xúc cảm và dịch nghĩa.
   * **Whisper (Local):** Gọi nhận diện chính xác theo ngôn ngữ gốc rồi tự động tính toán dùng chia câu đều đặn qua code Python.
3. **Bước 3 (Biên tập):** Studio kết xuất JSON tạm để vẽ đồ họa Timeline, cho phép biên tập viên điều chỉnh căn lề watermark bằng cách di chuyển vùng cắt hoặc thay đổi cỡ chữ phụ đề Việt hiển thị phía dưới một cách an toàn.
4. **Bước 4 (Kết xuất):** FFmpeg tổ hợp: cắt & bù mờ dải viền watermark, lồng tiếng ép vừa cung thời gian thoại của nhân vật, dính phụ đề Ass nền mờ rồi render cực nhanh bằng CUDA/NVENC.
