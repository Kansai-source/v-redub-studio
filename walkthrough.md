# V-reDub Studio - Hướng Dẫn Sử Dụng & Tổng Quan Hệ Thống

Dự án cung cấp cho bạn **2 lựa chọn linh hoạt** để nhận diện giọng nói & phụ đề dịch:

1. **Local Whisper (Miễn phí hoàn toàn & Tiêu chuẩn)**: Chạy cục bộ thông qua mô hình `faster-whisper` trên máy của bạn (sử dụng GPU CUDA hoặc CPU tối ưu Int8). Dịch ngôn ngữ miễn phí qua Google Translate.
2. **Gemini API (Cloud AI)**: Gửi file audio lên Google Gemini API. **Hệ thống tự động cắt chia nhỏ audio thành các đoạn ngắn 15 phút** để tránh lỗi tràn dung lượng và giới hạn output token của Gemini, tự động phân tích chi tiết giọng nói Nam / Nữ, trả về cấu trúc phụ đề chính xác và dịch nghĩa ngữ cảnh cao cấp.

---

## 📂 Tổng Quan Cấu Trúc Mã Nguồn

Hệ thống được chia ra thành 2 phần chính phối hợp nhịp nhàng:

### 1. Backend (FastAPI Local)
Chịu trách nhiệm thực hiện các tác vụ nặng cần quyền truy cập ổ cứng và GPU:
- **[config.py](file:///c:/Users/Asus/Desktop/Tool%20download/backend/config.py)**: Chứa cấu hình thư mục làm việc tạm thời (`temp/`) và trỏ trực tiếp đến thư viện giọng gốc của bạn tại `Voice_ref` bên thư mục `test ai`.
- **[download_service.py](file:///c:/Users/Asus/Desktop/Tool%20download/backend/download_service.py)**: Sử dụng thư viện `yt-dlp` để tải và trích xuất luồng video/audio chất lượng gốc từ link Douyin/Bilibili.
- **[video_service.py](file:///c:/Users/Asus/Desktop/Tool%20download/backend/video_service.py)**: Bộ xử lý **FFmpeg** hợp nhất chạy trong 1 luồng xử lý duy nhất để tối ưu tốc độ. Thực hiện phóng to (Zoom), chỉnh màu sắc (Brightness, Contrast, Saturation), lật ngang (hflip) để lách thuật toán bản quyền, vẽ dải màu che sub cũ, và lồng ghép tiếng lồng tiếng cùng vietsub.
- **[ai_service.py](file:///c:/Users/Asus/Desktop/Tool%20download/backend/ai_service.py)**: Tích hợp **local `faster-whisper`** tự động nhận diện tiếng gốc. Tích hợp thêm **Gemini API Mode** tự động cắt nhỏ tệp WAV thành các phần 15 phút, tải lên qua Files API, gọi cấu trúc JSON mong muốn cùng mô hình bạn chọn (Gemini 2.0 / 2.5 Flash/Pro hoặc các bản tùy chỉnh), sau đó tự động xóa tệp cloud và bù đắp dữ liệu thời gian (Offset) để khớp lại trục thời gian gốc của video.
- **[tts_service.py](file:///c:/Users/Asus/Desktop/Tool%20download/backend/tts_service.py)**: Cầu nối sang thư viện `omnivoice`. Nó tải mô hình TTS local một cách lazy-load (khi bắt đầu sinh) và ghép các phân đoạn audio chạy khớp từng mili-giây lên timeline.
- **[main.py](file:///c:/Users/Asus/Desktop/Tool%20download/backend/main.py)**: Định nghĩa các API endpoints và hỗ trợ tính năng stream dung lượng lớn (Byte-range requests) để trình duyệt xem thử mượt mà.

### 2. Frontend (Vite + React)
Giao diện người dùng sang trọng, đáp ứng cao:
- **[App.tsx](file:///c:/Users/Asus/Desktop/Tool%20download/frontend/src/App.tsx)**: Logic React để đồng bộ hóa tùy chọn dịch thuật, quản lý khóa Gemini API, hiển thị các chế độ hoạt động và chỉnh sửa phụ đề trực tiếp.
- **[index.css](file:///c:/Users/Asus/Desktop/Tool%20download/frontend/src/index.css)**: Giao diện tối (Dark-mode Obsidian), viền bóng neon cao cấp, các thanh kéo sliders, các nút switch bật/tắt mượt mà.

---

## ⚡ Hướng Dẫn Vận Hành Click-And-Run

Tôi đã chuẩn bị sẵn file chạy nhanh một chạm:
📁 **[start_tool.bat](file:///c:/Users/Asus/Desktop/Tool%20download/start_tool.bat)**

1. **Khởi động**: Bạn chỉ cần **click đúp vào file `start_tool.bat`**.
2. **Quá trình**: File bat sẽ tự động:
   - Kích hoạt FastAPI trên file python venv của thư mục `test ai`.
   - Chạy Frontend server Vite phục vụ trên địa chỉ `http://localhost:5173`.
   - Mở trình duyệt mặc định vào thẳng trang ứng dụng.

---

## 💡 Hướng Dẫn Sử Dụng Trên Web UI

1. **Bước 1: Tải Video**
   - Nhập link video Douyin hoặc Bilibili và bấm nút **Tải (Download)**. Tiến độ tải sẽ hiển thị ở bảng Console Logs ở góc dưới bên phải.
2. **Bước 2: Cấu Hình Dịch Thuật & Phụ Đề**
   - Trước khi bấm dịch, bạn sẽ thấy bảng cấu hình ở giữa:
     - **Chế độ Local Whisper**: Không cần kết nối internet hay token trả phí, tự dịch qua Google Translate.
     - **Chế độ Gemini API**: Chọn model (Flash/Pro) và nhập API Key của bạn. Hệ thống sẽ tự cắt nhỏ âm thanh thành từng blocks 15 phút, gửi lên Google Cloud để phân tách cụ thể giới tính nhân vật (Nam/Nữ) và dịch phụ đề chi tiết.
   - Bấm **Phiên âm & Dịch Phụ Đề**. Kết quả sau đó hiển thị dạng thẻ, cho phép sửa text hoặc gán đè giọng TTS mẫu.
3. **Bước 3: Tinh Chỉnh Lách Bản Quyền**
   - Ở cột bên trái, điều chỉnh các thanh gạt lách bản quyền: Zoom (khuyên dùng 10%-12%), độ sáng, độ bão hòa, lật hình.
   - Bật **Che phụ đề gốc** và điều chỉnh vị trí dải màu. Sau đó cấu hình âm lượng gốc so với tiếng lồng TTS.
   - **Tốc độ Video (Speed)**: Tăng/giảm tốc độ từ `0.5x` đến `2.0x`.
   - **Reframe 9:16**: Lựa chọn đổi tỷ lệ khung hình ngang thành dọc: `Center Crop` (Cắt giữa) hoặc `Blur Background` (Nền mờ nghệ thuật).
4. **Bước 4: Xuất Video Thành Phẩm**
   - Bấm nút **Lồng tiếng & Xuất Video Lách** để backend tổng hợp video mượt mà.

---

## 🌟 Các chức năng nâng cấp mới (Cập nhật 05/2026)

Hệ thống đã được bổ sung 5 nâng cấp mạnh mẽ cho việc sản xuất video ngắn (Shorts/TikTok/Reels):
1. **Tự động áp dụng voice được gán cho từng đoạn thoại**: Đồng bộ hóa cụ thể voice ID do người dùng lựa chọn cho từng segment trong json payload `/api/dub-and-edit` thay vì chỉ sử dụng Default male/female.
2. **Sửa lỗi hiển thị UI dropdown**: Khắc phục lỗi tương phản màu chữ tùy thuộc nền mặc định của trình duyệt cho thẻ select option ở giao diện Obsidian Dark Mode.
3. **Speed & Aspect Crop Filter (FFmpeg)**: Tích hợp logic xử lý hình ảnh và phối lại audio chuẩn khớp tốc độ thời gian thực.
4. **Cân lề dời trục Zoom (Xóa Watermark góc)**: Thêm tùy chọn căn lề Zoom (Chính giữa, Căn dưới - cắt mép trên, Căn trên - cắt mép dưới) giúp triệt tiêu logo/watermark góc đỉnh (như Bilibili) mà không cắt mất chân hay phần chính của khung hoạt cảnh.
5. **Tải lên giọng đọc mẫu từ Web UI**: Panel "Tải lên giọng clone (.wav)" ở Sidebar cho phép bạn upload trực tiếp file thu âm mẫu (.wav 3s-10s) ngay trên web. Hệ thống sẽ tự động lưu và làm mới danh sách giọng đọc ở các khối phụ đề tức thì để bạn áp dụng lồng tiếng ngay lập tức.
6. **Gemini Speaker Diarization (Phân tách & Đồng bộ hóa nhân vật)**: Khi dịch bằng Gemini API, mô hình tự động phân tách các giọng nói khác nhau thành các mã nhân vật chuyên biệt (như `MALE 1`, `FEMALE 1`, `MALE 2`...). Khi bạn đổi giọng lồng tiếng của một câu thuộc nhân vật nào đó, toàn bộ các câu thoại khác của nhân vật đó sẽ được đồng bộ tự động.
7. **Nghe thử giọng trước (Audio Voice Previews)**: Kế bên các dropdown lựa chọn giọng Clone, một nút Play (▶/⏹) cho phép phát thử trực tiếp file WAV của giọng đọc đó ngay từ máy chủ mà không cần xuất (render) video.
8. **Thiết Kế Giọng Nói Tự Tạo (Zero-shot Voice Designer)**: Ở Sidebar bên trái, Panel **6. Thiết kế giọng (Zero-shot)** cho phép bạn nhập từ khoá tiếng Anh mô tả (Ví dụ: `male, low pitch, warm voice`). Bạn bấm **Sinh thử giọng mới** để mô hình tự động tạo ra một giọng đọc ngẫu nhiên tức thời, bấm **Play** nghe thử, nếu ưng ý thì nhập tên bất kỳ và bấm **Lưu & Khóa Giọng Sử Dụng** để đưa vào Timeline dùng ngay lập tức.
9. **Dòng Thời Gian Toàn Màn Hình Tích Hợp (Dedicated Full-width Timeline Tab)**: Cung cấp giao diện biên tập phi tuyến chuyên nghiệp. Sau khi chọn giọng tại Phòng Biên Tập, bấm nút **🔄 Đồng bộ Timeline** để chuyển toàn bộ câu thoại sang hệ thống track. Sau đó chuyển sang Tab **Trình Dựng Timeline** ở Header để xem màn hình xem trước lớn và dòng thời gian dạng ngang đầy đủ mọi nhân vật.
10. **Co Giãn Thanh Che Cũ Thông Minh (Auto-fit Drawbox)**: Tự động tính toán và điều chỉnh độ rộng (width) cùng vị trí căn lề (X position) của thanh phụ đề đè (Drawbox) cho từng câu thoại dựa trên chiều dài văn bản dịch, giúp giữ thẩm mỹ tối đa mà không bị che quá khung hình gốc.
11. **Chế Độ Chỉ Chèn Phụ Đề (VietSub Only Mode)**: Thêm công tắc "Lồng tiếng (TTS Voiceover)" ở sidebar panel Cấu hình âm thanh. Khi tắt đi, hệ thống sẽ bỏ qua bước sinh tiếng nhân vật hoàn toàn giúp render video tốc độ cực cao, chỉ giữ lại phụ đề ViệtSub và các hiệu ứng hình ảnh lách bản quyền được kích hoạt.
12. **Giao Diện Biên Tập Dựng Trực Quan (Interactive NLE Timeline)**: Trình dựng Timeline hiện đã hỗ trợ kéo thả (drag) trực quan trực tiếp trên các khối câu thoại để xê dịch thời gian (shfiting) hoặc thu phóng đầu/cuối (left/right resizing) để vi chỉnh thời lượng thoại khớp khung hình. Đồng thời hỗ trợ click vào khối câu thoại bất kỳ để mở bảng **Hiệu chỉnh phân đoạn đã chọn** bên phải (sửa văn bản phụ đề dịch, xem hoặc chỉnh mốc giây bắt đầu/kết thúc, và thay đổi nhanh giọng đọc lồng tiếng tương ứng).
13. **Tối Ưu Độ Đục & Màu Sắc Thanh Che (Drawbox Opacity & Vibrancy)**: Độ đục (opacity) của thanh che trên khung xem trước (preview overlay) được tăng từ 60% lên 95% giúp cải thiện trực quan, đồng thời thiết lập màu vàng neon (gold) ánh xạ chính xác sang mã màu vàng tươi thuần khiết (R:255, G:255, B:0) ở cả giao diện lẫn backend FFmpeg để đạt hiệu quả che đè tối ưu, không bị mờ nhạt hay lộ chữ gốc.
14. **Thiết Kế Lại Giao Diện Tab Điều Khiển Cao Cấp (Segmented Control Pill-tab UI)**: Toàn bộ hệ thống nút chuyển tab ở đầu trang chính, các tab màn hình xem trước (video gốc vs dubbed) và tab nhật ký hệ thống được tái cấu trúc thành các thanh trượt viên nang (Pill-shaped Segmented Group) với hiệu ứng đổi màu hover êm ái, bo tròn góc, nền bán trong suốt glassmorphic cùng biểu tượng Lucide động tinh tế giúp giao diện tổng thể sang trọng và chuyên nghiệp hơn rất nhiều.
15. **Tài Liệu Hướng Dẫn Cài Đặt & Đẩy Code Lên GitHub (Setup & Deployment Doc)**: Tạo tệp `README.md` toàn diện ở thư mục gốc hướng dẫn chi tiết yêu cầu cài đặt (FFmpeg, Node.js, Python), cách kích hoạt môi trường ảo backend và chạy dự án. Trực tiếp đi kèm là tệp `.gitignore` tự động bỏ qua các thư mục nặng như `node_modules`, `venv` và các file video tạm thời, giúp người dùng đẩy toàn bộ mã nguồn lên GitHub nhanh chóng và an toàn chỉ với vài câu lệnh cơ bản.
16. **Phím Tắt Khởi Chạy Và Setup Một Click (setup.bat & start.bat)**: Tạo thêm phím tắt tệp cài đặt `setup.bat` (tự động tạo môi trường Python `venv`, cài thư viện backend, chạy cài đặt gói npm frontend) và tệp khởi động `start.bat` (mở song song server backend lẫn frontend trong 2 cửa sổ terminal riêng biệt và khởi chạy trình duyệt web) dành riêng cho máy Windows, giúp người dùng cuối khởi chạy Studio ngay tức khắc mà không cần biết viết lệnh terminal.
17. **Cấu Hình Môi Trường Di Động Không Cứng (Relative Path Portability)**: Khắc phục triệt để lỗi tìm đường dẫn tuyệt đối cũ chứa thư mục `test ai` hay các ổ cứng cố định bằng cách chuyển đổi tham số cấu hình thư mục giọng nói `DEFAULT_VOICE_REF_DIR` và lệnh gọi Python của các tệp chạy `.bat` sang dạng động/tương đối (Relative PATH). Đồng thời điều chỉnh `start.bat` hiển thị màn hình mở (`cmd /k`) khi lỗi để người dùng kiểm duyệt nội dung logs khởi động chuẩn xác.











