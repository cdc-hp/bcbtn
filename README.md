# Ứng dụng Giám sát dịch bệnh — phiên bản 0.6.0

Ứng dụng desktop Windows dùng **Python + SQLite + PyQt6** để quản lý ca bệnh, ổ dịch, lọc trùng và chia sẻ dữ liệu trong mạng LAN.

Thiết kế giai đoạn kế tiếp (nộp dữ liệu qua Web theo xã, lọc trùng theo tiêu chí chọn, xuất
Excel chia theo xã, hàng đợi nhập liệu hai tầng): xem [`WEB_DEDUP_DESIGN.md`](WEB_DEDUP_DESIGN.md).

## Cài đặt

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
  cho mạng LAN tin cậy, chưa có TLS. Nếu cần Trạm Y tế xã ở xa nộp trực tiếp (không qua đệm
  Google Apps Script), xem `google_apps_script/README.md` mục "Mở máy chủ chính ra Internet" —
  **bắt buộc đặt mật khẩu máy chủ** trước khi làm việc này, và cân nhắc đặt sau reverse proxy
  có HTTPS vì bản thân `lan_server.py` chưa hỗ trợ TLS.
- Nếu không đặt mật khẩu, mọi máy biết IP và cổng đều có thể kết nối (trong LAN, hoặc từ
  Internet nếu đã chuyển tiếp cổng).

## Phát hành

Workflow `.github/workflows/release.yml` chạy kiểm thử trên Windows, build bằng PyInstaller, tạo Setup bằng Inno Setup, quét dữ liệu cấm và sinh:

- `GiamSatDichBenh-Setup-vX.Y.Z.exe`
- `GiamSatDichBenh-Portable-vX.Y.Z.zip`
- `SHA256SUMS.txt`

Pull request chỉ build/test và tải artifact; chỉ push vào `main` hoặc chạy workflow thủ công mới tạo GitHub Release.

## Kiểm thử

```bat
python -m pytest -q
```

## Cấu trúc

```text
app.py                 Giao diện, menu, lọc trùng, máy trạm và tab Server
core.py                SQLite, nhập/xuất, chất lượng và thuật toán lọc trùng
deployment_config.py   Cấu hình standalone/workstation/server
lan_server.py          HTTP API, theo dõi client và khóa ghi khi sao lưu
lan_discovery.py       Tự dò máy chủ trong mạng LAN
remote_core.py         Lớp gọi API, retry và trạng thái kết nối máy trạm
backup_manager.py      Chính sách, kiểm tra, lưu giữ và phục hồi sao lưu
duplicate_config.py   Trọng số và ngưỡng lọc trùng
update_manager.py      Cập nhật ứng dụng
setup.iss              Bộ cài và trang chọn mô hình triển khai
.github/workflows/     Kiểm thử, build và Release tự động
tests/                  Kiểm thử lõi, lọc trùng, cấu hình và LAN
secondary_sync.py      Đồng bộ hàng đợi từ máy chủ phụ (Google Apps Script) khi online lại
google_apps_script/    Code.gs + hướng dẫn triển khai máy chủ phụ (Google Sheet/Drive)
WEB_DEDUP_DESIGN.md    Thiết kế nền tảng Web, lọc trùng theo tiêu chí, hàng đợi hai tầng
```

## Nộp dữ liệu qua Web và hàng đợi nhập liệu

Theo mặc định, máy chủ chính chỉ nghe trong LAN nội bộ CDC (xem mục "Lưu ý mạng LAN"), nên
**Trạm Y tế xã ở xa không vào thẳng được máy chủ chính** trừ khi CDC chủ động mở cổng ra
Internet. Có 2 kênh nộp:

- **Link chính mà xã lưu và dùng hằng tuần**: URL Web App của Google Apps Script (luôn chạy
  trên hạ tầng công cộng của Google, xã nào cũng vào được). Nếu CDC đã mở máy chủ chính ra
  Internet (domain/IP công khai + cấu hình `MAIN_SERVER_URL`), mỗi lần nộp qua link này được
  Apps Script **chuyển tiếp thẳng** vào hàng đợi máy chủ chính ngay lập tức; nếu chưa mở hoặc
  máy chủ chính tạm thời không phản hồi, dữ liệu tự lưu tạm trên Google và CDC đồng bộ bù sau.
  Xem `google_apps_script/README.md` để triển khai và lấy link gửi cho các xã.
- `http://<địa-chỉ-máy-chủ>:<cổng>/xa` — chỉ dùng được khi đang ở ngay trong LAN của CDC (ví dụ
  xã ghé văn phòng CDC), yêu cầu đăng nhập bằng tài khoản riêng của xã.

Khi chạy ở chế độ Máy chủ, máy chủ phục vụ thêm:

- `http://<địa-chỉ-máy-chủ>:<cổng>/cdc/hang-doi` — CDC xem hàng đợi chia theo xã (gồm cả dữ
  liệu đã đồng bộ từ Google Apps Script), nhập vào CSDL chính, bấm đồng bộ máy chủ phụ, quản lý
  tài khoản xã (dùng cho `/xa`) và xem nhật ký kiểm toán. Xem `WEB_DEDUP_DESIGN.md` để biết
  chi tiết kiến trúc.

**Lưu ý khi bật tài khoản xã**: ngay khi CDC tạo tài khoản xã đầu tiên, trang `/xa` bắt buộc
đăng nhập cho *mọi* xã (không còn chấp nhận nộp tự do). Tài khoản này chỉ áp dụng cho `/xa`
trên máy chủ chính — Google Apps Script vẫn dùng một khóa `SHARED_KEY` chung cho mọi xã (xem
`google_apps_script/README.md`).
