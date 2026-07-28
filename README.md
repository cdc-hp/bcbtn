# Ứng dụng Giám sát dịch bệnh — phiên bản 0.18.2

Quản lý ca bệnh, ổ dịch, lọc trùng và chia sẻ dữ liệu — CDC Hải Phòng. Web App tập trung: 1 máy
chủ duy nhất chạy dịch vụ Windows (FastAPI/Uvicorn), quản trị hoàn toàn qua trình duyệt, không
cần cài gì thêm trên máy quản trị viên.

Kiến trúc đầy đủ, schema CSDL, vận hành Google Apps Script: xem [`CLAUDE.md`](CLAUDE.md).
Việc còn lại/backlog: xem [`TASKS.md`](TASKS.md).

## Cài đặt

1 bản cài duy nhất: **`CDC-GiamSatDichBenh-Server-Setup-vX.Y.Z.exe`** (GitHub Releases) — cài
như dịch vụ Windows (`CDCGiamSatDichBenh`), cần quyền Administrator, cài **một lần duy nhất**
trên máy đóng vai trò máy chủ. Sau khi cài, mở `http://127.0.0.1:<cổng>/cdc/login` (mặc định
cổng `8765`, hoặc qua tên miền công khai nếu đã cấu hình Cloudflare Tunnel) — quản trị viên khác
chỉ cần trình duyệt, không cài gì thêm.

Hướng dẫn chi tiết: [`docs/huong-dan/6-may-chu-web-tap-trung.html`](docs/huong-dan/6-may-chu-web-tap-trung.html).
Kiến trúc/route/vai trò tài khoản: xem `CLAUDE.md` mục "Web App tập trung (`webapp/`)".

Muốn chạy thủ công (không đăng ký dịch vụ Windows, ví dụ máy demo/phát triển): bấm đúp
`Chay_May_Chu.bat` — chạy nền kèm icon khay hệ thống, chuột phải để mở trình duyệt hoặc dừng
hẳn máy chủ.

## Vị trí dữ liệu

Bản phát hành không chứa dữ liệu mẫu hoặc dữ liệu thật. Dữ liệu được tạo sau khi cài tại:

```text
C:\ProgramData\CDC Hai Phong\GiamSatDichBenh\
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
- Xóa nguyên một lần nhập (theo file + đúng thời điểm nhập) khi phát hiện nhập nhầm file.
- **Lọc trùng nghiệp vụ**:
  - Ca bệnh: mã ca, CCCD/CMND, họ tên, năm sinh, giới, điện thoại, địa bàn, chẩn đoán, ngày khởi phát.
  - Ổ dịch: tên bệnh, địa điểm chuẩn hóa, địa bàn, thời gian khởi phát và đơn vị báo cáo.
  - Phân loại `Trùng chắc chắn` và `Nghi trùng`.
  - Cấu hình trọng số và ngưỡng xác định trùng.
  - Chọn giá trị tốt nhất từng trường để tạo bản ghi hợp nhất.
  - Bản còn lại được đưa vào Thùng rác và có thể khôi phục; CSDL được sao lưu trước thao tác.
- Tìm kiếm, lọc, phân trang, xem chi tiết và xuất Excel/CSV.
- Thêm, sửa, xóa ổ dịch.
- Kiểm tra chất lượng dữ liệu.
- Quản lý tài khoản quản trị viên riêng (vai trò super_admin/admin/data_operator/viewer), khoá
  tài khoản sau nhiều lần đăng nhập sai, nhật ký kiểm toán.
- Đồng bộ hàng đợi từ máy chủ phụ (Google Apps Script) tự động theo chu kỳ, chạy nền không cần
  ai mở trình duyệt.
- Sao lưu tự động theo chu kỳ; lưu giữ bản ngày/tuần/tháng, kiểm tra toàn vẹn và phục hồi có bản an toàn.
- Có thể chọn thư mục NAS, OneDrive hoặc Google Drive for Desktop làm đích sao lưu.
- Máy chủ dự phòng (failover thủ công): cài thêm 1-2 máy dự phòng cùng public qua Cloudflare
  Tunnel Replica, tự kéo bản sao CSDL định kỳ; super-admin bấm tay chuyển máy chính khi cần —
  xem CLAUDE.md mục "Máy chủ dự phòng".

## Lưu ý mạng

- Máy chủ mặc định nghe tại cổng `8765` trên mọi card mạng (`0.0.0.0`).
- Mặc định khuyến nghị **không** mở cổng này ra Internet trực tiếp (không TLS, không qua
  Cloudflare Tunnel) — chỉ dùng trong LAN tin cậy. Cách mở ra Internet an toàn hơn (qua
  Cloudflare Tunnel, bắt buộc đặt khoá bí mật trước): xem `CLAUDE.md` mục "Mở máy chủ chính ra
  Internet".

## Phát hành

Workflow `.github/workflows/release.yml` chạy kiểm thử trên Windows, build bằng PyInstaller, tạo Setup bằng Inno Setup, quét dữ liệu cấm, xác nhận Web App cài đặt/chạy được như dịch vụ Windows thật, và sinh:

- `CDC-GiamSatDichBenh-Server-Setup-vX.Y.Z.exe`
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
**`https://cdc-hp.github.io/bcbtn/`** (trang GitHub Pages — form nộp thật, không còn iframe).
Trang này tự thử nộp **thẳng vào máy chủ chính** (nếu CDC đã mở máy chủ ra Internet và cấu hình
`MAIN_SERVER_URL`/`public_submit_key`); chỉ khi không kết nối được mới rơi xuống Google Apps
Script để lưu tạm trên Sheet/Drive, chờ CDC đồng bộ bù.

Trang `/cdc/hang-doi` (đăng nhập quản trị viên) để CDC duyệt hàng đợi, nhập CSDL, đồng bộ máy
chủ phụ, xem nhật ký kiểm toán. Trang `/cdc/lich-su-nhap` để xem/xóa theo từng lần nhập.

Kiến trúc đầy đủ (GAS, hàng đợi 2 tầng, `SHARED_KEY`, tài khoản quản trị viên): xem `CLAUDE.md`.
