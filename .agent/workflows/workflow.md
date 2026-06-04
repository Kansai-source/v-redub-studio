---
description: Quy trình thiết lập và khởi chạy ứng dụng V-reDub Studio để biên tập, dịch thuật và lồng tiếng video tự động
---

# Quy Trình Cài Đặt và Khởi Chạy V-reDub Studio

Tài liệu này hướng dẫn chi tiết các bước để thiết lập, cấu hình cookies và vận hành trôi chảy dự án V-reDub Studio trên các hệ điều hành khác nhau.

## Bước 1: Chuẩn bị Môi trường & Cài đặt hệ thống
Bạn có thể cài đặt tự động trên Windows hoặc thực hiện thủ công trên macOS / Linux.

### Lựa chọn A: Cài đặt tự động trên Windows (Khuyên dùng)
1. Mở thư mục dự án trên máy tính (`Tool download`).
2. Bấm đúp chuột trái (hoặc chạy từ terminal) tệp tin **`setup.bat`**:
   ```cmd
   .\setup.bat
   ```
3. Hệ thống sẽ tự động quét, kiểm tra xem máy tính của bạn đã cài đặt Python, Node.js và FFmpeg chưa. Nếu chưa có, nó sẽ tự động dùng công cụ `winget` của Microsoft để cài đặt chúng tự động. Sau đó tạo môi trường ảo Python `venv` cùng với cài đặt các thư viện Frontend (`npm install`) và Backend (`pip install -r requirements.txt`).

### Lựa chọn B: Thiết lập thủ công (dành cho macOS hoặc Linux)
1. Cấu hình Backend:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Cấu hình Frontend:
   ```bash
   cd ../frontend
   npm install
   ```

## Bước 2: Cài đặt Cookies để tránh lỗi tải Video (Bắt buộc cho video giới hạn/chất lượng cao)
Mặc định hệ thống tự phát hiện cookies trình duyệt, tuy nhiên bạn nên xuất cookies trực tiếp để đảm bảo không bị chặn:
1. Cài đặt tiện ích mở rộng **Get cookies.txt LOCALLY** trên trình duyệt Chrome/Edge của bạn.
2. Truy cập [youtube.com](https://www.youtube.com/) hoặc [bilibili.com](https://www.bilibili.com/) (đăng nhập tài khoản của bạn).
3. Bấm vào icon Extension ở góc công cụ trình duyệt, chọn **Export** để tải xuống tệp cookie dưới dạng text.
4. Đổi tên tệp đã tải về thành **`cookies.txt`** và đặt trực tiếp vào thư mục gốc của dự án (`c:\Users\Asus\Desktop\Tool download\cookies.txt`).

## Bước 3: Khởi chạy V-reDub Studio

### Lựa chọn A: Khởi chạy trên Windows
1. Đảm bảo bạn đang ở thư mục gốc của dự án.
2. Bấm đúp chuột trái vào tệp tin **`start.bat`** (hoặc chạy từ terminal):
   ```cmd
   .\start.bat
   ```
3. Tệp này sẽ tự động khởi động đồng thời cả Backend Server (FastAPI cổng 8000) và Frontend Client (Vite cổng 5173), đồng thời tự động kích hoạt trình duyệt truy cập vào giao diện web của ứng dụng Studio.

### Lựa chọn B: Khởi chạy thủ công (macOS / Linux)
1. Mở một terminal ở thư mục `backend/` đã kích hoạt môi trường ảo `venv` và chạy:
   ```bash
   python main.py
   ```
2. Mở một terminal thứ hai ở thư mục `frontend/` và chạy:
   ```bash
   npm run dev
   ```
3. Truy cập vào đường link cổng hiển thị trên terminal frontend (thông thường là `http://localhost:5173`) để sử dụng ứng dụng web.
