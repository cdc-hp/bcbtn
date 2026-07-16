# Ứng dụng Giám sát dịch bệnh — phiên bản 0.3.0

Ứng dụng desktop offline dùng **Python + SQLite + PyQt6** để quản lý dữ liệu ca bệnh và ổ dịch.

## Cài đặt dành cho người dùng cuối

Người dùng không cần cài Python, không cần chạy `build.bat` và không cần biết mã nguồn.

Mỗi GitHub Release tự động tạo hai tệp:

- `GiamSatDichBenh-Setup-vX.Y.Z.exe`: bộ cài Windows, khuyến nghị sử dụng.
- `GiamSatDichBenh-Portable-vX.Y.Z.zip`: bản portable, giải nén rồi chạy.
- `SHA256SUMS.txt`: mã kiểm tra tính toàn vẹn của hai tệp phát hành.

Với bản Setup, người dùng chỉ cần tải file `.exe`, bấm đúp, chọn **Tiếp tục/Cài đặt** rồi mở ứng dụng từ Start Menu hoặc biểu tượng ngoài Desktop.

## Nguyên tắc tách dữ liệu khỏi chương trình

**Bản phát hành không chứa dữ liệu mẫu hoặc dữ liệu thật.** Các tệp sau bị loại khỏi GitHub và Release:

- CSDL `*.db`, `*.sqlite`, `*.sqlite3`.
- Excel `*.xlsx`, `*.xls`, `*.xlsm`.
- CSV `*.csv`.
- Thư mục `data/`, `backups/`, `update_cache/`.

GitHub Actions có bước kiểm tra bắt buộc. Nếu phát hiện bất kỳ tệp dữ liệu nào trong sản phẩm build, workflow sẽ thất bại và không tạo Release.

Sau khi cài, dữ liệu được tạo riêng tại:

```text
%LOCALAPPDATA%\CDC_HaiPhong\GiamSatDichBenh\
├─ data\giam_sat_dich_benh.db
├─ backups\
└─ update_cache\
```

Do dữ liệu nằm ngoài thư mục cài đặt:

- Cài đè phiên bản mới không ghi đè CSDL.
- Gỡ ứng dụng không tự xóa dữ liệu nghiệp vụ.
- Bộ cài và GitHub Release không mang theo dữ liệu bệnh nhân.

## Chức năng chính

- Dashboard thống kê ca bệnh, ổ dịch, ca mắc, tử vong và cảnh báo chất lượng.
- Nhập Excel ca bệnh và ổ dịch, tự dò hàng tiêu đề và biến thể tên cột.
- Chống nhập lặp tuyệt đối bằng SHA-256.
- Tìm kiếm, lọc, phân trang, xem chi tiết và xuất Excel/CSV.
- Thêm, sửa, xóa ổ dịch; tự sao lưu trước thao tác nguy hiểm.
- Kiểm tra chất lượng dữ liệu.
- Truy vấn SQL chỉ đọc.
- Cập nhật trực tiếp từ Google Drive, có kiểm tra SHA-256.

## Quy trình tạo Release tự động trên GitHub

Workflow nằm tại:

```text
.github/workflows/release.yml
```

Mỗi khi mã nguồn được đẩy lên nhánh `main`, GitHub Actions đọc `VERSION.txt` và tự thực hiện:

1. Cài Python và thư viện.
2. Chạy toàn bộ kiểm thử.
3. Build ứng dụng Windows bằng PyInstaller.
4. Tạo bộ cài bằng Inno Setup.
5. Kiểm tra sản phẩm không chứa `.db`, Excel hoặc CSV.
6. Tạo bản portable ZIP.
7. Sinh `SHA256SUMS.txt`.
8. Tạo GitHub Release và đính kèm các tệp đã build.

### Phát hành bằng một lệnh trên máy phát triển

Cập nhật phiên bản trong `VERSION.txt` và `core.py`, sau đó commit và đẩy lên `main`, hoặc chạy:

```bat
release.bat
```

Hoặc thực hiện thủ công:

```bat
git add .
git commit -m "Release v0.3.0"
git push
```

Workflow tự tạo tag `vX.Y.Z`, tạo Release và đính kèm bộ cài. Nếu phiên bản đó đã tồn tại, workflow sẽ dừng và yêu cầu tăng `VERSION.txt`.

## Build thử trên Windows

Chỉ dành cho người phát triển:

```bat
setup.bat
build.bat
```

Kết quả:

```text
dist\GiamSatDichBenh\GiamSatDichBenh.exe
setup_output\GiamSatDichBenh-Setup-vX.Y.Z.exe
```

`build.bat` không sao chép thư mục dữ liệu vào `dist`.

## Chạy từ mã nguồn

```bat
setup.bat
run.bat
```

Hoặc:

```bat
python -m pip install -r requirements.txt
python app.py
```

## Kiểm thử

```bat
python -m pytest -q
```

## Cấu trúc dự án

```text
app.py                           Giao diện PyQt6
core.py                          SQLite, nhập/xuất và kiểm tra dữ liệu
update_manager.py                Cập nhật ứng dụng
setup.iss                        Kịch bản tạo bộ cài Inno Setup
build.bat                        Build EXE và Setup trên Windows
release.bat                      Commit, push và gắn tag release
VERSION.txt                      Phiên bản phát hành
.github/workflows/release.yml    Build và phát hành tự động
requirements.txt                 Thư viện
tests/                           Kiểm thử tự động
```

## Lưu ý bảo mật

Trước mỗi lần commit vẫn nên chạy `git status` để kiểm tra. Tuy nhiên dự án đã có ba lớp ngăn rò rỉ dữ liệu:

1. `.gitignore` chặn các định dạng dữ liệu.
2. `build.bat` không sao chép dữ liệu vào bản build.
3. GitHub Actions từ chối tạo Release nếu phát hiện tệp dữ liệu trong sản phẩm.
