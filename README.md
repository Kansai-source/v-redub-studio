# V-reDub Studio - Trình Biên Tập & Lồng Tiếng Video Tự Động

**V-reDub Studio** là ứng dụng web cho phép người dùng tự động dịch thuật phụ đề, quét giọng nói (diarization), lồng tiếng đè (TTS Voiceover) và áp dụng các hiệu ứng hình ảnh giúp tối ưu nội dung video, phục vụ cho việc re-up, lách bản quyền chuyên nghiệp.

---

## 📌 Các Tính Năng Nổi Bật

1. **Phân Tách Giọng Nói (Speaker Diarization)** với Gemini: Nhận diện giọng nói của từng nhân vật trong audio gốc.
2. **Dịch Thuật Tự Động (Transcription & Translation)** bằng Gemini hoặc Local (Whisper + Google Translate).
3. **Thiết Kế Giọng Nói (Zero-shot Voice Designer)**: Nhập văn bản mô tả để tự sinh giọng lồng tiếng mới theo sở thích.
4. **Trình Dựng Timeline NLE Chuyên Nghiệp**: Giao diện dòng thời gian đầy đủ, trực quan hóa từng phân đoạn thoại. 
5. **Biên Tập Kéo Thả Trực Quan**: Kéo các khối câu thoại trên timeline để căn chỉnh mốc giây (start/end) và đổi giọng đọc cụ thể.
6. **Che Phụ Đề Gốc Cực Khớp (Auto-fit Drawbox)**: Tự động vẽ khối màu che phụ đề cũ trên video khớp với chiều dài văn bản dịch.
7. **Chế Độ Chỉ Chèn Phụ Đề (VietSub Only Mode)**: Tắt "Lồng tiếng (TTS Voiceover)" để chạy kết xuất siêu nhanh chỉ với phụ đề Việt ngữ và hiệu ứng hình ảnh.

---

## 🛠️ Yêu Cầu Cài Đặt Hệ Thống

Để chạy được V-reDub Studio, máy tính của bạn cần được cài đặt sẵn:

1. **Python** (Từ phiên bản `3.9` đến `3.11` được khuyến nghị).
2. **Node.js** (Phiên bản `18.0` trở lên) & **npm**.
3. **FFmpeg** (Bắt buộc phải cài đặt và đưa vào biến môi trường `PATH`).
4. **Git** (để quản lý mã nguồn và tải về).

> [!TIP]
> **Cách cài đặt nhanh cho Windows (Qua PowerShell):**
> Nhấp chuột phải vào nút Start -> chọn **PowerShell (Admin)** và chạy các lệnh sau để tự động tải và cài đặt Node.js và FFmpeg trong 5 giây:
> ```powershell
> # Cài đặt Node.js
> winget install OpenJS.NodeJS
>
> # Cài đặt FFmpeg
> winget install Gyan.FFmpeg
> ```
> *Sau khi cài đặt xong, hãy tắt và mở lại PowerShell rồi chạy thử `ffmpeg -version` để kiểm tra.*

---

## 🚀 1. Hướng Dẫn Dành Cho Máy Windows (Nhanh Nhất)

Nếu bạn chạy ứng dụng trên hệ điều hành **Windows**, bạn không cần gõ lệnh thủ công. Chỉ cần chạy các tệp bấm đúp sau:

1. **Cài đặt lần đầu tiên:**
   * Bấm đúp chuột trái vào tệp **`setup.bat`** ở thư mục gốc của dự án.
   * Chương trình sẽ tự động tạo môi trường ảo Python (`venv`), cài đặt thư viện cần thiết cho Backend và chạy `npm install` cho Frontend React. bạn chỉ cần đợi cho đến khi hoàn thành.
2. **Khởi chạy ứng dụng:**
   * Sau khi hoàn tất cài đặt, hãy bấm đúp chuột trái vào tệp **`start.bat`** ở thư mục gốc.
   * Lệnh này sẽ mở tự động 2 cửa sổ chạy đồng thời cả Server Backend (cổng 8000) và Client Frontend (cổng 5173). Trình duyệt của bạn sẽ tự động mở trang web giao diện phòng biên tập Studio.

---

## ⚙️ 2. Hướng Dẫn Cài Đặt và Khởi Chạy Thủ Công (Cho macOS / Linux)

Nếu bạn chạy trên hệ điều hành **macOS** hoặc **Linux**, hãy thực hiện tuần tự các bước cấu hình thủ công sau:

### Bước A: Cấu hình Backend (Python Fast-API)
1. Mở Cửa sổ Dòng lệnh tại thư mục `backend/`:
   ```bash
   cd backend
   ```
2. Tạo môi trường ảo (Virtual Environment):
   ```bash
   python -m venv venv
   ```
3. Kích hoạt môi trường ảo:
   ```bash
   source venv/bin/activate
   ```
4. Cài đặt các thư viện phụ thuộc:
   ```bash
   pip install -r requirements.txt
   ```

### Bước B: Cấu hình Frontend (React + TypeScript + Vite)
1. Mở Cửa sổ Dòng lệnh mới tại thư mục `frontend/`:
   ```bash
   cd frontend
   ```
2. Cài đặt các gói tài nguyên Node và chạy runtime:
   ```bash
   npm install
   ```

### Bước C: Khởi chạy thủ công
* **Chạy Server Backend:** Tại thư mục `backend`, chạy `python main.py`
* **Chạy Client Frontend:** Tại thư mục `frontend`, chạy `npm run dev`


---

## 🍪 3. Hướng Dẫn Cấu Hình Cookies (Bắt Buộc cho Video Bị Chặn/Hạn Chế)

Mặc định, hệ thống sẽ tự động quét thông tin Cookie từ các trình duyệt hiện tại (Chrome, Edge, Firefox) trên máy người dùng để tải video. Tuy nhiên, để đảm bảo việc tải xuống các video bị giới hạn tuổi, bị chặn địa lý hoặc chặn IP do bot diễn ra trơn tru nhất, bạn nên cung cấp file `cookies.txt` riêng biệt:

### Các bước lấy và cài đặt `cookies.txt`:
1. **Cài đặt tiện ích mở rộng (Extension) xuất Cookies trên Trình duyệt:**
   * Cài đặt extension **Get cookies.txt LOCALLY** (dành cho Chrome/Edge/Opera) hoặc tiện ích tương đương từ Chôm Web Store.
2. **Xuất file Cookies từ YouTube hoặc Bilibili:**
   * Truy cập trang web nguồn (như [youtube.com](https://www.youtube.com/) hoặc [bilibili.com](https://www.bilibili.com/)) trên trình duyệt của bạn (đảm bảo đã **đăng nhập** tài khoản để có quyền tối đa).
   * Bấm vào biểu tượng tiện ích **Get cookies.txt LOCALLY** đã cài ở góc phải thanh công cụ.
   * Chọn **Export** hoặc **Download** để tải tệp tin dạng cookies.
3. **Cấu hình vào thư mục dự án:**
   * Đổi tên tệp tải về thành đúng **`cookies.txt`**.
   * Sao chép tệp này và dán trực tiếp vào **Thư mục gốc** (thư mục `Tool download`) của dự án trên máy tính của bạn.
   * Hệ thống download của backend sẽ tự động ưu tiên đọc file này trước tiên để vượt qua các lớp bảo mật và giới hạn chất lượng.

> [!IMPORTANT]
> **Giới hạn độ phân giải khi tải Video Bilibili / YouTube:**
> * **Không có Cookies:** Bạn chỉ có thể tải video từ Bilibili ở chất lượng mặc định tối đa là **480p** (hoặc gặp lỗi chặn ở YouTube).
> * **Có Cookies (đăng nhập sẵn tài khoản):** Sẽ tải được tối ưu chất lượng gốc cao nhất của video như **720p** và **1080p** cực mượt mà.

---

## 🌐 Hướng Dẫn Đẩy Dự Án Lên GitHub & Chia Sẻ

Để đưa mã nguồn này lưu trữ lên GitHub cá nhân của bạn để chia sẻ cho người khác, làm theo các bước sau:

1. **Tạo Kho Chứa (Repository) Mới Trên GitHub:**
   * Truy cập [github.com](https://github.com/) và bấm nút **New** để tạo repository.
   * Đặt tên repository (ví dụ: `v-redub-studio`) và không cần tích chọn README.md hay .gitignore vì dự án đã có sẵn.
   * Sao chép URL của Repository vừa tạo (dạng `https://github.com/<tên-tài-khoản>/v-redub-studio.git`).

2. **Khởi tạo và Đẩy Source Code Lên (Phải chạy từ thư mục gốc của dự án):**
   Mở terminal tại thư mục gốc chứa cả thư mục `backend` và `frontend`:
   ```bash
   # Khởi tạo Git cục bộ
   git init

   # Cập nhật danh sách file chuẩn bị upload
   git add .

   # Ghi nhận các file đầu tiên (Commit)
   git commit -m "Initial commit: V-reDub Studio"

   # Tạo nhánh branch chính là main
   git branch -M main

   # Liên kết với kho lưu trữ GitHub từ xa
   git remote add origin https://github.com/<tên-tài-khoản>/v-redub-studio.git

   # Push mã nguồn lên
   git push -u origin main
   ```
   *(Lưu ý: Tệp `.gitignore` trong dự án đã cấu hình tự động bỏ qua các thư mục nặng như `node_modules`, `venv` và các file video được xử lý tạm thời để tránh làm nặng repo).*
