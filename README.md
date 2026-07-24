# Ứng dụng Giám sát dịch bệnh — phiên bản 0.10.1

Quản lý ca bệnh, ổ dịch, lọc trùng và chia sẻ dữ liệu — CDC Hải Phòng. Hiện có **2 kiến trúc chạy
song song** trong lúc chuyển đổi (xem [`TASKS.md`](TASKS.md) mục "Đang làm"):

- **Web App tập trung** (mới, khuyến nghị cho triển khai thật) — 1 máy chủ duy nhất chạy dịch vụ
  Windows (FastAPI/Uvicorn), quản trị hoàn toàn qua trình duyệt. Xem mục "Web App tập trung" bên
  dưới.
- **Desktop (PyQt6)** — ứng dụng cài trên từng máy (máy đơn lẻ/máy trạm/máy chủ LAN), vẫn hoạt
  động bình thường, giữ nguyên cho tới khi Web App được xác nhận thay thế đủ chức năng trên máy
  thật. Phần còn lại của tài liệu này mô tả bản desktop.

Kiến trúc đầy đủ, schema CSDL, vận hành Google Apps Script: xem [`CLAUDE.md`](CLAUDE.md).
Việc còn lại/backlog: xem [`TASKS.md`](TASKS.md).

## Web App tập trung (mới)

1 bản cài duy nhất: **`CDC-GiamSatDichBenh-Server-Setup-vX.Y.Z.exe`** (GitHub Releases) — cài
như dịch vụ Windows (`CDCGiamSatDichBenh`), cần quyền Administrator. Sau khi cài, mở
`http://127.0.0.1:<cổng>/cdc/login` (mặc định cổng `8765`, hoặc qua tên miền công khai nếu đã
cấu hình Cloudflare Tunnel) — không cần cài gì thêm trên máy trạm quản trị viên.

Hướng dẫn chi tiết: [`docs/huong-dan/6-may-chu-web-tap-trung.html`](docs/huong-dan/6-may-chu-web-tap-trung.html).
Kiến trúc/route/vai trò tài khoản: xem `CLAUDE.md` mục "Web App tập trung (`webapp/`)".

## Cài đặt (bản desktop)

3 bản cài trong GitHub Releases, dùng chung 1 ứng dụng — chỉ khác cấu hình mặc định do installer ghi ra. Người dùng không cần cài Python hoặc tự build.

- **`GiamSatDichBenh-Setup-vX.Y.Z.exe`** (bản tổng hợp): hỏi chọn 1 trong 3 chế độ — Máy đơn lẻ, Máy trạm, hoặc Máy chủ. Phù hợp dùng thử hoặc triển khai nhỏ/không tách vai trò.
- **`GiamSatDichBenh-Server-Setup-vX.Y.Z.exe`**: luôn cài chế độ **Máy chủ** — cài **duy nhất 1 lần** trên máy đóng vai trò máy chủ chính. Có tính năng **Chuyển máy chủ** (tab Server) để đồng bộ toàn bộ dữ liệu sang máy chủ mới và tự đóng máy cũ khi cần thay đổi phần cứng.
- **`GiamSatDichBenh-Admin-Setup-vX.Y.Z.exe`**: luôn cài chế độ **Máy trạm**, dùng cho từng quản trị viên kết nối tới máy chủ qua IP LAN. Sau khi cài, vào **Kết nối máy chủ LAN → Đăng nhập quản trị viên** để đăng nhập **tài khoản cá nhân riêng** (khác mật khẩu dùng chung của máy chủ) — CDC tạo tài khoản này ở tab **Hàng đợi → Tài khoản quản trị...** trên máy chủ.

Bộ cài (cả 3 bản) hỏi:

1. **Máy đơn lẻ** (chỉ bản tổng hợp): ứng dụng và CSDL chạy trên một máy, không chia sẻ LAN.
2. **Máy trạm**: nhập địa chỉ máy chủ dạng `http://192.168.1.10:8765` và mật khẩu dùng chung nếu máy chủ có đặt.
3. **Máy chủ**: tự tạo CSDL trên máy chủ, mở API HTTP trong LAN và hiện thêm tab **Server**. Mật khẩu để trống nghĩa là không yêu cầu mật khẩu dùng chung.

Máy trạm không mở trực tiếp file SQLite. Mọi thao tác được gửi qua API của máy chủ để tránh nhiều máy cùng ghi trực tiếp vào một file `.db`.

## Vị trí dữ liệu

Bản phát hành không chứa dữ liệu mẫu hoặc dữ liệu thật. Dữ liệu được tạo sau khi cài tại:

```text
%LOCALAPPDATA%\CDC_HaiPhong\GiamSatDichBenh\
├─ deployment.json
├─ data\giam_sat_dich_benh.db
├─ backups\
└─ update_cache\
```

GitHub Actions từ chối phát hành nếu phát hiện `.db`, SQLite, Excel, CSV hoặc các thư mục dữ liệu trong mã nguồn/sản phẩm build.

## Chức năng chính

- Dashboard thống kê ca bệnh, ổ dịch, ca mắc, tử vong và cảnh báo chất lượng.
- Nhập Excel ca bệnh/ổ dịch; nhận diện tiêu đề biến thể và file XLSX khai báo sai phạm vi.
- Chống nhập lại đúng nguyên dòng bằng SHA-256.
- **Lọc trùng nghiệp vụ**:
  - Ca bệnh: mã ca, CCCD/CMND, họ tên, năm sinh, giới, điện thoại, địa bàn, chẩn đoán, ngày khởi phát.
  - Ổ dịch: tên bệnh, địa điểm chuẩn hóa, địa bàn, thời gian khởi phát và đơn vị báo cáo.
  - Phân loại `Trùng chắc chắn` và `Nghi trùng`.
  - Cấu hình trọng số và ngưỡng xác định trùng.
  - Chọn giá trị tốt nhất từng trường để tạo bản ghi hợp nhất.
  - Bản còn lại được đưa vào Thùng rác và có thể khôi phục; CSDL được sao lưu trước thao tác.
- Tìm kiếm, lọc, phân trang, xem chi tiết và xuất Excel/CSV.
- Thêm, sửa, xóa ổ dịch.
- Kiểm tra chất lượng dữ liệu và SQL chỉ đọc.
- Menu ứng dụng: nhập dữ liệu, lọc trùng, sao lưu, cập nhật, cấu hình máy trạm/máy chủ và trợ giúp.
- Máy chủ LAN có cổng và mật khẩu tùy chọn; tab Server chỉ xuất hiện ở chế độ máy chủ.
- Tự dò máy chủ trong LAN bằng UDP, tự kết nối lại khi mạng chập chờn.
- Server hiển thị danh sách máy trạm, nhật ký yêu cầu và chuyển sang chỉ đọc trong lúc sao lưu.
- Sao lưu tự động theo chu kỳ; lưu giữ bản ngày/tuần/tháng, kiểm tra toàn vẹn và phục hồi có bản an toàn.
- Có thể chọn thư mục NAS, OneDrive hoặc Google Drive for Desktop làm đích sao lưu.

## Lưu ý mạng LAN

- Máy chủ mặc định nghe tại cổng `8765` trên mọi card mạng (`0.0.0.0`).
- Bộ cài chế độ Máy chủ tạo quy tắc TCP `8765` và UDP tự dò `8766` cho **Private networks / Mạng riêng tư**; tab Server cũng có nút cấu hình lại.
- Mặc định khuyến nghị **không** chuyển tiếp cổng server ra Internet — API hiện được thiết kế
  cho mạng LAN tin cậy, chưa có TLS. Nếu không đặt mật khẩu, mọi máy biết IP và cổng đều có thể
  kết nối. Chi tiết cách mở ra Internet an toàn hơn (bắt buộc mật khẩu + reverse proxy HTTPS):
  xem `CLAUDE.md` mục "Mở máy chủ chính ra Internet".

## Phát hành

Workflow `.github/workflows/release.yml` chạy kiểm thử trên Windows, build bằng PyInstaller, tạo Setup bằng Inno Setup, quét dữ liệu cấm, xác nhận Web App cài đặt/chạy được như dịch vụ Windows thật, và sinh:

- `CDC-GiamSatDichBenh-Server-Setup-vX.Y.Z.exe` (Web App tập trung, mới)
- `GiamSatDichBenh-Setup-vX.Y.Z.exe` (desktop, tổng hợp 3 chế độ)
- `GiamSatDichBenh-Server-Setup-vX.Y.Z.exe` (desktop, chế độ Máy chủ)
- `GiamSatDichBenh-Admin-Setup-vX.Y.Z.exe` (desktop, chế độ Máy trạm)
- `GiamSatDichBenh-Portable-vX.Y.Z.zip` (desktop, không cần cài)
- `SHA256SUMS.txt`

Pull request chỉ build/test và tải artifact; chỉ push vào `main` hoặc chạy workflow thủ công mới tạo GitHub Release.

## Kiểm thử

```bat
python -m pytest -q
```

## Cấu trúc

Danh sách file chính và vai trò từng file: xem `CLAUDE.md` mục "File chính".

## Nộp dữ liệu qua Web và hàng đợi nhập liệu

Theo mặc định, máy chủ chính chỉ nghe trong LAN nội bộ CDC, nên **Trạm Y tế xã ở xa không vào
thẳng được máy chủ chính**. Kênh nộp chính thức, cố định gửi cho các xã:
**`https://cdc-hp.github.io/bcbtn/`** (trang GitHub Pages, iframe tới Google Apps Script — tự
chuyển tiếp vào hàng đợi máy chủ chính nếu CDC đã mở máy chủ ra Internet, hoặc lưu tạm trên
Google rồi CDC đồng bộ bù). Khi ở ngay trong LAN của CDC còn có thể vào thẳng
`http://<địa-chỉ-máy-chủ>:<cổng>/xa` (yêu cầu tài khoản riêng của xã).

Khi chạy ở chế độ Máy chủ, còn có `http://<địa-chỉ-máy-chủ>:<cổng>/cdc/hang-doi` (CDC duyệt
hàng đợi, nhập CSDL, đồng bộ máy chủ phụ, quản lý tài khoản xã, xem nhật ký kiểm toán).

Kiến trúc đầy đủ (GAS, hàng đợi 2 tầng, `SHARED_KEY`, tài khoản xã/quản trị): xem `CLAUDE.md`.
