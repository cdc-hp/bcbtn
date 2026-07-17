# Máy chủ phụ (Google Apps Script)

Dùng khi máy chủ chính offline — xem `WEB_DEDUP_DESIGN.md` mục 7 và `secondary_sync.py`.

## Triển khai (thao tác thủ công trên Google, không tự động hoá được từ repo)

1. Tạo một Google Sheet mới (ví dụ đặt tên "GSBTN - Hàng đợi phụ"). Sheet dữ liệu
   (`HangDoiPhu`) và các cột sẽ tự tạo khi script chạy lần đầu — không cần tạo tay.
2. Trong Sheet đó: **Tiện ích mở rộng → Apps Script**. Xoá nội dung mặc định, dán toàn bộ
   nội dung file `Code.gs` vào.
3. **Project Settings (biểu tượng bánh răng) → Script Properties → Add script property**:
   - Key: `SHARED_KEY`
   - Value: một chuỗi bí mật tự đặt (không dùng chung với mật khẩu LAN của máy chủ chính).
     Đây là khóa mà Trạm Y tế xã và `secondary_sync.py` phải cung cấp để ghi/đọc hàng đợi phụ.
4. **Triển khai → Triển khai mới (Deploy → New deployment)**:
   - Loại: **Web app**.
   - Execute as: **Me** (tài khoản CDC sở hữu Sheet/Drive).
   - Who has access: **Anyone** (để Trạm Y tế xã truy cập được mà không cần đăng nhập Google) —
     bảo mật dựa vào `SHARED_KEY`, không dựa vào quyền Google.
   - Bấm Deploy, cấp quyền khi được hỏi, sao chép **Web app URL** (dạng
     `https://script.google.com/macros/s/XXXXXXXX/exec`).
5. Cấu hình máy chủ chính: mở app desktop ở chế độ Máy chủ, điền `secondary_webapp_url` =
   URL vừa sao chép và `secondary_shared_key` = giá trị `SHARED_KEY` ở bước 3 (lưu trong
   `deployment.json` qua màn hình cấu hình máy chủ).
6. Gửi cho các Trạm Y tế xã: **URL Web app** (dùng khi máy chủ chính offline) và **khóa
   `SHARED_KEY`** — đây là "đường dẫn dự phòng" nhắc tới trong trang `/xa` của máy chủ chính.

## Vận hành

- Xã mở URL Web app khi không nộp được vào máy chủ chính, điền form, nộp — file được lưu vào
  Google Drive (thư mục `MayChuPhu_GSBTN/<xã>/<tuần>/`) và ghi một dòng trạng thái
  `cho_dong_bo` vào sheet `HangDoiPhu`.
- Khi máy chủ chính online lại, CDC bấm **"Đồng bộ máy chủ phụ"** trên trang
  `/cdc/hang-doi` (hoặc gọi `secondary_sync.pull_secondary_queue(...)`): hệ thống kéo các dòng
  `cho_dong_bo` vào hàng đợi chính (`import_queue`, nguồn `server_phu`), rồi báo lại cho Apps
  Script đánh dấu `da_dong_bo` để không kéo trùng lần sau.
- Có thể đặt một trình kích hoạt theo thời gian (Triggers → Time-driven) gọi lại
  `pull_secondary_queue` định kỳ từ phía máy chủ chính (ví dụ cron/scheduled task chạy Python)
  thay vì chỉ bấm tay — script trong repo không tự lập lịch việc này.

## Giới hạn đã biết

- File càng lớn thì thời gian mã hoá base64/tải qua Apps Script càng lâu; Apps Script giới hạn
  thời gian chạy mỗi lần gọi khoảng 6 phút — phù hợp với quy mô danh sách ca bệnh hằng tuần của
  một xã, không phù hợp để chuyển file rất lớn.
- `Who has access: Anyone` nghĩa là ai có URL + khóa đều gọi được — khóa cần được xem như một
  mật khẩu, thay định kỳ nếu nghi lộ, và không nên gửi qua kênh không an toàn.
