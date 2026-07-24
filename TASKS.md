# Việc còn lại / Backlog

Kiến trúc & schema hiện tại xem [`CLAUDE.md`](CLAUDE.md). File này chỉ theo dõi **việc đã xong
gần đây** (để không làm lại) và **việc còn mở**.

## Đang làm: chuyển sang Web App tập trung (FastAPI)

Nhiệm vụ lớn: bỏ mô hình desktop PyQt6 + máy trạm quản trị riêng, chuyển toàn bộ quản trị sang
Web App chạy trên đúng 1 máy chủ, quản trị viên chỉ cần trình duyệt (Chrome/Edge) qua
`https://cdc-hp.io.vn/cdc/login`. Chi tiết đầy đủ 18 mục yêu cầu nằm trong lịch sử trò chuyện
lúc giao việc này — tóm tắt tiến độ theo 11 giai đoạn:

- [x] **Giai đoạn 1** — Rà soát code, xác nhận baseline test (72 test cũ đều pass).
- [x] **Giai đoạn 2** — FastAPI + xác thực: `webapp/` (`main.py`, `config.py`, `auth.py`,
      `dependencies.py`, `routers/login.py`, `routers/dashboard.py` placeholder). Đăng nhập
      phiên (cookie HttpOnly, tái dùng `core.issue_admin_token`/`verify_admin_token` — không
      thêm thư viện session), CSRF double-submit-cookie, khoá tài khoản, buộc đổi mật khẩu lần
      đầu, thiết lập `super_admin` đầu tiên (`/cdc/setup`), `/health`. `cdc_accounts` mở rộng
      `role`/`must_change_password`/`failed_login_count`/`locked_until`; `audit_log` thêm cột
      `ip`. Bootstrap 5 + HTMX vendor cục bộ trong `webapp/static/vendor/` (không phụ thuộc
      CDN). 16 test mới (`tests/test_cdc_account_roles_lockout.py`,
      `tests/test_webapp_auth.py`), 79/79 test pass. Đã chạy thử server thật (uvicorn) qua curl
      xác nhận toàn luồng thiết lập → đăng nhập → dashboard → đăng xuất hoạt động đúng, không
      chỉ dựa vào test.
- [x] **Giai đoạn 3** — `POST /queue/submit` (`webapp/routers/submission_api.py`) tương thích
      nguyên trạng `Code.gs: tryForwardToMainServer` (không đổi phía Code.gs) — xác thực bằng
      `gas_api_key` riêng (deployment_config.py, TÁCH khỏi mật khẩu LAN dùng chung), rate-limit
      10 lần/5 phút theo (IP, xã) (`webapp/services/rate_limit.py`), chống gửi trùng theo hash
      nội dung (`core.queue_submit` — cột `content_hash` mới, bỏ qua các mục đã lỗi khi so
      trùng). `/cdc/hang-doi` (`webapp/routers/queue.py` + `templates/queue.html`): lọc theo
      xã/tuần/trạng thái/nguồn (`core.list_import_queue` thêm tham số `week`/`source`), xem,
      tải file gốc, nhập một/nhiều, **nhập lại** mục lỗi (`core.import_queue_item` giờ nhận cả
      trạng thái `loi`, trước đây chỉ `cho_nhap`), xoá theo quyền (`core.delete_queue_item` mới
      — chặn xoá khi `dang_nhap`/đã `da_nhap`). Phân quyền: xem = mọi vai trò đã đăng nhập, nhập
      = super_admin/admin/data_operator, xoá = super_admin/admin. 23 test mới
      (`tests/test_queue_web_extensions.py`, `tests/test_webapp_queue.py`), 102/102 test pass.
      Đã chạy thử server thật xác nhận `/queue/submit` và `/cdc/hang-doi` hoạt động đúng.
- [x] **Giai đoạn 4** — `/cdc/dashboard` thật (thay placeholder): tổng ca bệnh/ổ dịch, file chờ
      nhập/lỗi, xã đã nộp tuần hiện tại (`core.current_iso_week()` mới), lần sao lưu gần nhất,
      phiên bản. **Chưa có** "xã chưa nộp" (cần danh mục xã chuẩn hoá, đã ghi backlog) và "nhóm
      nghi trùng" (để Giai đoạn 5, tránh dashboard chậm vì quét trùng toàn bộ mỗi lần tải).
      `/cdc/ca-benh` + `/cdc/o-dich` (`webapp/routers/records.py`, dùng chung 1 router cho cả 2
      loại — cấu trúc giống hệt nhau): tìm kiếm, lọc nhiều điều kiện, phân trang phía máy chủ
      (tái dùng nguyên `core.query_records`/`list_filter_values`/`get_record` có sẵn, không viết
      lại), xem chi tiết, xem nguồn file, xem lỗi chất lượng (`core.list_quality_issues` thêm
      tham số `entity_id`). "Xuất theo bộ lọc" chưa làm — gộp vào Giai đoạn 5 (cùng nhóm xuất dữ
      liệu). 18 test mới (`tests/test_webapp_records.py`), 110/110 test pass. Đã chạy thử server
      thật xác nhận các trang yêu cầu đăng nhập đúng.
- [x] **Giai đoạn 5** — `/cdc/loc-trung` (`webapp/routers/dedup.py`): quét trùng ca bệnh/ổ dịch
      (tái dùng nguyên `core.find_duplicate_groups`), duyệt & hợp nhất từng nhóm
      (`/cdc/loc-trung/xem` nhận id bản ghi trực tiếp qua querystring thay vì `group_id` — tránh
      quét lại/lệch kết quả nếu dữ liệu vừa đổi; `core.get_records_by_ids` mới), hợp nhất
      (`core.merge_duplicate_records`, đưa bản còn lại vào Thùng rác), thùng rác/lịch sử + khôi
      phục (`core.list_duplicate_actions`/`restore_duplicate_action`), cấu hình tiêu chí ca bệnh
      + trọng số ổ dịch (`duplicate_config.save_case_criteria`/`save_rules`). Phân quyền: xem =
      mọi vai trò, hợp nhất = super_admin/admin/data_operator, khôi phục/cấu hình tiêu chí =
      super_admin/admin. `/cdc/xuat-du-lieu` (`webapp/routers/xuat_du_lieu.py`): xuất theo bộ lọc
      (Excel/CSV, tái dùng `core.export_filtered_records`) — có nút "Xuất theo bộ lọc" ngay trên
      `/cdc/ca-benh`/`/cdc/o-dich`; xuất ca bệnh chia theo xã (`core.export_cases_by_commune`).
      Xuất bị chặn với vai trò `viewer` (chỉ xem, không xuất hàng loạt — quyết định vì dữ liệu có
      CCCD/SĐT, xem TASKS.md backlog "Mã hoá national_id/phone"). Dashboard: thêm thẻ "Nhóm nghi
      trùng chưa xử lý" (`core.count_duplicate_groups` mới, giới hạn `max_records=3000` để không
      làm chậm trang tổng quan). File xuất dùng file tạm + tự xoá sau khi gửi xong
      (`webapp/services/export_files.py`, `BackgroundTask`), không ghi vào thư mục dữ liệu chính.
      26 test mới (`tests/test_dedup_export_core.py`, `tests/test_webapp_dedup.py`,
      `tests/test_webapp_export.py`), 136/136 test pass. Đã chạy thử server thật: seed dữ liệu
      trùng thật, quét → duyệt → hợp nhất → thùng rác → khôi phục, xuất theo bộ lọc và xuất theo
      xã đều tải file `.xlsx` thành công qua curl (không chỉ dựa vào test).
- [x] **Giai đoạn 6** — `/cdc/tai-khoan` (`webapp/routers/accounts.py`, chỉ `super_admin`): tạo
      tài khoản, đổi vai trò, khoá/mở khoá, đặt lại mật khẩu (tái dùng nguyên
      `core.create_cdc_account`/`set_cdc_account_role`/`set_cdc_account_active`/
      `reset_cdc_account_password`) — thêm 1 lớp bảo vệ router tự làm (không có trong `core.py`,
      chủ định để tầng gọi tự lo — xem docstring `set_cdc_account_role`): chặn super_admin tự
      khoá/tự hạ quyền chính mình. `/cdc/nhat-ky` (`webapp/routers/audit_log.py`, super_admin +
      admin): xem/lọc theo action/actor/commune/ip/khoảng ngày, tái dùng nguyên
      `core.list_audit_log` (đã có sẵn tham số lọc từ Giai đoạn 2). `/cdc/sao-luu`
      (`webapp/routers/backups.py`, tái dùng nguyên `backup_manager`): xem tình trạng sao lưu tự
      động, sao lưu ngay, tải file sao lưu, cấu hình chính sách giữ bản (interval/keep_*) — xem =
      super_admin/admin, PHỤC HỒI (ghi đè CSDL đang chạy) + sửa chính sách = chỉ super_admin
      (rủi ro cao hơn hẳn thao tác khác, tách quyền riêng thay vì dùng chung CAN_MANAGE của
      `/cdc/tai-khoan`). Tên file sao lưu trong URL được xác thực nằm đúng trong thư mục sao lưu
      (chặn path traversal) trước khi tải/phục hồi. 24 test mới (`tests/test_webapp_accounts.py`,
      `tests/test_webapp_audit_log.py`, `tests/test_webapp_backups.py`), 160/160 test pass. Đã
      chạy thử server thật: tạo tài khoản → xem trong nhật ký → sao lưu → phục hồi (xác nhận tài
      khoản tạo sau thời điểm sao lưu biến mất đúng như core-level test đã kiểm) → phiên đăng
      nhập vẫn còn hiệu lực sau khi phục hồi CSDL đang chạy.
- [x] **Giai đoạn 7** — `webapp/scheduler.py` mới: đồng bộ máy chủ phụ chạy nền qua
      `APScheduler` (`BackgroundScheduler`, khởi động/tắt qua `lifespan` của `webapp/main.py`),
      thay `MainWindow.run_auto_secondary_sync` kiểu `QTimer` — chạy trong tiến trình Uvicorn,
      không phụ thuộc có ai mở trình duyệt. Đọc lại `secondary_sync_interval_minutes` (5-180
      phút, đã có sẵn trong `deployment_config.py`) mỗi lần khởi động job; đổi chu kỳ cần khởi
      động lại tiến trình (APScheduler không tự reschedule job đang chạy). Chống chạy chồng lấp
      bằng `threading.Lock` không chặn (`_run_lock`) dùng chung cho cả tác vụ định kỳ lẫn nút
      "Đồng bộ ngay" — idempotent, bỏ qua im lặng nếu đang có lần chạy khác thay vì xếp hàng.
      Trạng thái (đang chạy/lần gần nhất/lỗi/lần kế tiếp) đọc qua `_state_lock` riêng để việc
      xem trạng thái không bị treo trong lúc đang đồng bộ. Dashboard: thẻ trạng thái đồng bộ +
      nút "Đồng bộ ngay" (`POST /cdc/dashboard/dong-bo-may-chu-phu`, vai trò
      super_admin/admin/data_operator — khai `def` thường KHÔNG `async` vì gọi mạng có thể mất
      tới 30s/dòng, nếu để `async def` gọi thẳng sẽ chặn cả vòng lặp sự kiện của toàn Web App).
      `/health` hết hardcode `"chua_trien_khai"`, trả trạng thái thật
      (`chua_chay`/`dang_chay`/`dang_dong_bo`). 13 test mới (`tests/test_scheduler.py`,
      `tests/test_webapp_dashboard_sync.py`), 173/173 test pass. Đã chạy thử server thật với 1
      máy chủ phụ giả lập (`http.server` thuần, mô phỏng đúng API `list_pending`/`mark_synced`
      của `MayChuPhu.gs`): bấm "Đồng bộ ngay" → kéo đúng 1 mục đang chờ vào `/cdc/hang-doi`,
      máy chủ phụ giả lập xác nhận đã xoá mục khỏi hàng chờ (`mark_synced` gọi đúng), nhật ký ghi
      `secondary_sync_pull`, `/health` báo `"scheduler": "dang_chay"` khi chạy qua Uvicorn thật
      (khác `TestClient` không kích hoạt `lifespan` nên trong test luôn là `chua_chay`).
- [x] **Giai đoạn 8** — `service_windows.py` mới: dịch vụ Windows (`CDCGiamSatDichBenh`, dùng
      `pywin32`/`win32serviceutil.ServiceFramework`) chạy `webapp.main:app` qua Uvicorn —
      `run_server()` là phần lõi dùng chung cho cả `SvcDoRun` (chạy như dịch vụ thật) lẫn lệnh
      `python service_windows.py run` (chạy tay để phát triển/kiểm thử, không cần đăng ký với
      Windows) để 2 đường chạy không lệch hành vi. Lệnh dòng lệnh chuẩn pywin32:
      `install`/`start`/`stop`/`remove`/`debug`. `/cdc/cau-hinh` (`webapp/routers/settings.py`,
      chỉ super_admin): cổng/địa chỉ lắng nghe, tên miền công khai, khoá API GAS, URL/khoá +
      chu kỳ máy chủ phụ, thư mục sao lưu — khoá bí mật (GAS API key, khoá máy chủ phụ) KHÔNG
      bao giờ hiện lại giá trị thật lên trang (ô mật khẩu trống, để trống khi lưu = giữ nguyên
      giá trị cũ, chỉ ghi đè khi nhập giá trị mới). Nút "Khởi động lại dịch vụ" gọi
      `service_windows.restart_service()`, báo lỗi rõ ràng khi chưa cài đặt dịch vụ/thiếu quyền
      Administrator thay vì giả vờ thành công. Tài khoản super_admin đầu tiên đã có sẵn từ
      `/cdc/setup` (Giai đoạn 2) — trang này không lặp lại bước đó, chỉ thêm phần cấu hình triển
      khai. 13 test mới (`tests/test_service_windows.py`, `tests/test_webapp_settings.py`),
      186/186 test pass. Đã chạy thử server thật xác nhận: `python service_windows.py run` khởi
      động đúng Uvicorn theo `server_host`/`server_port` đọc từ cấu hình (dùng đúng code path
      `SvcDoRun` sẽ dùng), trang `/cdc/cau-hinh` lưu/hiển thị đúng (khoá bí mật không lộ ra
      HTML), nút "Khởi động lại dịch vụ" gọi thật vào Windows Service Control Manager và nhận
      lỗi thật (`OpenSCManager: Access is denied` — do sandbox chạy không có quyền Administrator
      và dịch vụ chưa được cài) thay vì lỗi giả lập.
      **CHƯA kiểm thử**: cài đặt/gỡ dịch vụ Windows thật (`python service_windows.py
      install`/`start`/`stop`/`remove`) — cần quyền Administrator mà sandbox hiện tại không có,
      và đây là thao tác ảnh hưởng trạng thái hệ thống dùng chung nên cố tình không tự ý thực
      hiện. Cần người có quyền Administrator trên máy Windows thật chạy thử trước khi coi Giai
      đoạn 8 là "đã xác minh đầy đủ" — việc này sẽ được kiểm thử gián tiếp qua bộ cài ở Giai đoạn 9.
      **Bổ sung khi làm Giai đoạn 9**: `service_windows.py` giờ mặc định thư mục dữ liệu là
      `C:\ProgramData\CDC Hai Phong\GiamSatDichBenh` khi chạy như dịch vụ thật (đúng yêu cầu ban
      đầu, trước đó lỡ vẫn dùng `%LOCALAPPDATA%` kế thừa từ app desktop) — chỉ áp dụng cho nhánh
      `install`/`start`/`stop`/`remove`/`debug`; lệnh `run` (phát triển/kiểm thử) vẫn giữ hành vi
      cũ (tôn trọng `GIAM_SAT_DICH_BENH_DATA_DIR` đã đặt hoặc mặc định LOCALAPPDATA), 4 test mới
      xác nhận đúng (`_resolve_cli_mode`, import không có tác dụng phụ, `run` không tự ép
      ProgramData — đã chạy thử subprocess thật xác nhận).
- [x] **Giai đoạn 9** — `setup-webapp-server.iss` mới: bộ cài DUY NHẤT cho Web App tập trung,
      `CDC-GiamSatDichBenh-Server-Setup-v{version}.exe`, `PrivilegesRequired=admin` (khác 3 bộ
      cài desktop cũ đều `lowest`) vì phải đăng ký dịch vụ Windows. Wizard chỉ hỏi ĐÚNG 1 câu
      (cổng lắng nghe) — không hỏi tài khoản/GAS/đồng bộ/thư mục sao lưu như installer cũ, vì
      những cái đó nay cấu hình qua trình duyệt (`/cdc/setup`, `/cdc/cau-hinh`, Giai đoạn 2 và
      8) đúng triết lý "quản trị chỉ cần trình duyệt". Cài đặt: dừng+gỡ dịch vụ cũ TRƯỚC khi copy
      file (`PrepareToInstall`, tránh lỗi file đang bị khoá lúc nâng cấp), ghi
      `C:\ProgramData\CDC Hai Phong\GiamSatDichBenh\deployment.json` CHỈ khi máy chưa từng cài
      (giữ nguyên cấu hình/khoá bí mật cũ khi nâng cấp — cùng triết lý với `setup-server.iss`),
      mở tường lửa cho cổng đã chọn, đăng ký+khởi động dịch vụ, cuối cùng mở trình duyệt tới
      `/cdc/login`. Gỡ cài đặt: dừng+gỡ dịch vụ trước khi xoá file, KHÔNG tự xoá thư mục dữ liệu
      (an toàn dữ liệu — admin tự xoá tay nếu thật sự muốn). `build.bat` thêm bước PyInstaller
      riêng cho `service_windows.py` (`--console`, không phải `--windowed`; loại trừ
      `PyQt5`/`PyQt6` — máy build có cả 2 khiến PyInstaller từ chối build vì xung đột Qt binding,
      dù webapp/ không dùng Qt) + gọi ISCC cho `.iss` mới.
      Đã build + chạy thử THẬT: PyInstaller build thành công (loại bỏ `PyQt5`/`PyQt6` sau khi
      gặp đúng lỗi xung đột này), chạy trực tiếp file `.exe` đã đóng gói (`CDCGiamSatDichBenh.exe
      run`) xác nhận phục vụ đúng qua HTTP — static asset, template Jinja, toàn luồng thiết lập →
      đăng nhập → dashboard đều hoạt động; phát hiện và sửa 1 lỗi thật khi build (thiếu
      `VERSION.txt` cạnh `.exe` khiến `/health` báo `"version": "0.0.0"` — đã thêm bước copy vào
      `build.bat`, xác nhận lại báo đúng `0.10.1`).
      **CHƯA kiểm thử được**: không compile được bằng Inno Setup (`ISCC.exe`) trong sandbox này —
      đã thử cài Inno Setup 6.7.3 cả bằng bộ cài đầy đủ (`/CURRENTUSER`) lẫn chế độ giải nén
      portable (`/PORTABLE=1`), cả 2 cách đều treo ở bước tự giải nén rất sớm (không tạo được cả
      file log), có vẻ là giới hạn của môi trường sandbox (không có phiên desktop tương tác đầy
      đủ cho ứng dụng GUI) chứ không phải lỗi kịch bản `.iss`. Đã tự soát kỹ cú pháp Pascal
      Script (đặc biệt sửa 1 lỗi thứ tự thực thi thật: `[Icons]` được engine xử lý TRƯỚC bước
      `ssPostInstall`, ban đầu `ResolvedPort` tính ở `ssPostInstall` nên shortcut sẽ thiếu cổng —
      đã sửa tính `ResolvedPort` sớm hơn ở `NextButtonClick`). Cần máy Windows thật (có Inno
      Setup cài sẵn hoặc cài được qua `choco install innosetup` như CI đang dùng) chạy
      `build.bat` toàn bộ, cài thử `CDC-GiamSatDichBenh-Server-Setup-v{version}.exe` với quyền
      Administrator, và xác nhận dịch vụ khởi động đúng + `/cdc/login` mở được — việc này sẽ được
      CI (Giai đoạn 10, chạy trên `windows-latest` có đủ điều kiện) thực hiện thay, nhưng vẫn nên
      có người xác nhận cài thật trên máy CDC trước khi phát hành chính thức.
- [x] **Giai đoạn 10** — `.github/workflows/release.yml`: thêm
      `CDC-GiamSatDichBenh-Server-Setup-v{version}.exe` vào danh sách file kiểm tra checksum, tạo
      GitHub Release, và upload artifact (song song 3 bộ cài desktop cũ, không thay thế —
      `build.bat` đã tự build cả 4 trong 1 lần chạy từ Giai đoạn 9, workflow chỉ cần biết tên
      file mới). Quan trọng hơn: thêm bước **"Verify Web App installs and runs as a Windows
      Service"** — bù đắp đúng phần KHÔNG kiểm thử được ở Giai đoạn 8/9 do sandbox phát triển
      thiếu quyền Administrator. `windows-latest` chạy với quyền Administrator sẵn có nên bước
      này làm được điều sandbox không làm được: chạy silent-install bộ cài thật vừa build
      (`/VERYSILENT /SUPPRESSMSGBOXES`), xác nhận dịch vụ `CDCGiamSatDichBenh` vào trạng thái
      `Running`, gọi thật `GET /health` xác nhận trả `"status":"ok"`, rồi chạy file gỡ cài đặt
      thật do Inno Setup sinh ra (`unins000.exe`, đúng `[UninstallRun]` — không tự gọi
      `stop`/`remove` tay) và xác nhận dịch vụ đã biến mất khỏi SCM. Build thất bại rõ ràng
      (`throw`) nếu bất kỳ bước nào sai, không chỉ log cảnh báo rồi bỏ qua.
      **CHƯA kiểm thử**: chưa chạy được workflow này trên GitHub Actions thật trong phiên làm
      việc này (không có quyền kích hoạt CI từ đây) — cần lần chạy CI thật tiếp theo (push/PR)
      để xác nhận bước cài đặt/gỡ cài mới hoạt động đúng trên `windows-latest`; nếu lỗi, đây sẽ
      là nơi đầu tiên cần xem log.
- [x] **Giai đoạn 11 (một phần)** — Cập nhật tài liệu: `README.md` thêm mục "Web App tập trung"
      (cài đặt, link hướng dẫn) ngay đầu file, cập nhật danh sách file phát hành trong mục "Phát
      hành"; `CLAUDE.md` viết lại toàn bộ mục "Web App tập trung" (trước đó chỉ có ghi chú của
      Giai đoạn 2) — bảng route chính kèm phân quyền, tóm tắt Giai đoạn 5/7/8/9-10, cập nhật
      "File chính" và "Build & test"; `docs/huong-dan/6-may-chu-web-tap-trung.html` mới (theo
      đúng khuôn mẫu 5 tài liệu HTML/PDF sẵn có) — cài đặt, thiết lập lần đầu, vai trò tài khoản,
      các màn hình chính, ghi chú kỹ thuật (chưa xuất PDF, cần người có công cụ in-ra-PDF làm
      nốt bước đó như các tài liệu trước). 188/188 test pass (không có test mới ở phần này, chỉ
      tài liệu).
      **CHƯA làm — cố ý hoãn**:
      - Bump `VERSION.txt` — việc này khiến `release.yml` tự tạo GitHub Release công khai kèm
        tag ngay khi push (workflow trigger `push: branches: [main]`, so tag đã tồn tại chưa).
        Chưa xác minh được cài đặt dịch vụ Windows thật trên máy có quyền Administrator (xem
        Giai đoạn 8/9), nên chưa tự ý kích hoạt phát hành công khai — để CDC/người phụ trách
        release tự bump khi đã sẵn sàng phát hành, sau khi xác nhận cài thật thành công.
      - Xoá `app.py`/`lan_server.py`/`setup.iss`/`setup-server.iss`/`setup-admin.iss` — theo
        đúng điều kiện đã ghi từ đầu nhiệm vụ này ("chưa xoá cho tới khi Web App thay thế đủ
        chức năng VÀ được xác nhận dùng thật"), điều kiện đó chưa thoả (chưa có xác nhận cài đặt
        dịch vụ Windows thật trên máy CDC). Giữ nguyên toàn bộ, chạy song song.
      - Vẽ lại sơ đồ ASCII "Kiến trúc tổng thể" ở đầu `CLAUDE.md` — vẫn đúng cho luồng desktop cũ
        (`lan_server.py`), chưa vẽ thêm nhánh Web App mới; mục "Web App tập trung" đã mô tả đủ
        bằng văn bản nên không chặn việc dùng tài liệu, nhưng nên làm khi có dịp.

### Bổ sung sau khi phát hành v0.11.0 — 2 lỗi thật CI thật phát hiện (sandbox không phát hiện được)

Bấm nút "chốt release" (bump `VERSION.txt` lên `0.11.0`, push) đã kích hoạt CI thật trên
`windows-latest` — đúng như kỳ vọng, phát hiện được 2 lỗi mà sandbox phát triển (thiếu Inno
Setup, thiếu quyền Administrator) không thể phát hiện:

1. **`setup-webapp-server.iss` không biên dịch được**: `Error on line 127: Unknown preprocessor
   directive.` — dòng Pascal Script bắt đầu bằng `#13#10#13#10` (ký tự xuống dòng) bị ISPP
   (preprocessor Inno Setup, quét toàn văn bản TRƯỚC khi Pascal Script biên dịch) hiểu nhầm
   thành 1 chỉ thị preprocessor vì dòng bắt đầu bằng `#`. Sửa: chuyển `#13#10#13#10` lên cùng
   dòng với câu lệnh gán phía trước, không để nó là token đầu dòng.
2. **Dịch vụ Windows cài xong nhưng ở trạng thái `Stopped` thay vì `Running`** — lỗi nghiêm
   trọng hơn nhiều, đúng loại lỗi mà bước "Verify Web App installs and runs as a Windows
   Service" (Giai đoạn 10) được thêm vào để bắt. Nguyên nhân gốc: toàn bộ `webapp/main.py` và
   10 file `webapp/routers/*.py` gọi `Jinja2Templates(directory="webapp/templates")`/
   `StaticFiles(directory="webapp/static")` bằng **đường dẫn tương đối** — khi Windows SCM khởi
   động dịch vụ, thư mục làm việc mặc định là `System32`, không phải thư mục cài đặt, nên đường
   dẫn tương đối không trỏ tới đâu cả; `StaticFiles` kiểm tra thư mục tồn tại ngay lúc import
   nên toàn bộ `webapp.main` crash ngay khi khởi động. **Vì sao sandbox không bắt được**: mọi
   lần chạy thử thủ công trong các giai đoạn trước đều vô tình chạy với thư mục làm việc = thư
   mục gốc mã nguồn (nơi `webapp/templates` thật sự tồn tại), nên đường dẫn tương đối "tình cờ"
   đúng — chưa từng thử chạy từ thư mục làm việc khác để lộ lỗi. Sửa: `webapp/__init__.py`
   thêm `TEMPLATES_DIR`/`STATIC_DIR` tính tuyệt đối từ `Path(__file__).resolve().parent` (đúng
   cả khi chạy từ mã nguồn lẫn khi đóng gói PyInstaller — cùng kỹ thuật `core.py: _base_dir()`
   đã dùng), thay toàn bộ 12 chỗ dùng chuỗi tương đối. Đã viết lại kiểm thử
   (`tests/test_webapp_paths.py`) xác nhận đường dẫn tuyệt đối + import được từ thư mục làm
   việc bất kỳ (mô phỏng đúng tình huống SCM), và tự tay chạy lại server thật từ một thư mục
   KHÁC thư mục gốc mã nguồn để xác nhận sửa đúng trước khi push lại (191/191 test pass).

**Bài học**: khi kiểm thử "chạy thử server thật" cho mã sẽ chạy như dịch vụ nền, phải test từ
thư mục làm việc KHÔNG phải thư mục gốc mã nguồn — nếu không, lỗi đường dẫn tương đối sẽ ẩn đi
một cách im lặng.

## Đã xong (tính đến v0.6.0)

1. Lọc trùng theo tiêu chí chọn (bỏ chấm điểm), hiển thị `case_code` gốc để tra ngược.
2. Xuất Excel chia theo xã (mỗi xã 1 sheet + sheet `Tong_hop`), quy tắc chọn xã khi trùng khác
   xã (xã của bản ghi `admission_date` mới nhất).
3. Web nộp dữ liệu + hàng đợi 2 tầng (`/xa`, `/cdc/hang-doi`), tài khoản riêng theo xã
   (`commune_accounts`) + audit log, rate-limit theo (IP, xã).
4. GAS máy chủ phụ: chuyển tiếp trực tiếp khi có `MAIN_SERVER_URL`, đệm Sheet/Drive khi lỗi
   mạng, đồng bộ bù idempotent.
5. Trang GitHub Pages iframe GAS (`docs/index.html`) làm link cố định cho xã + tab "tình hình
   nộp" lọc theo xã trong `Code.gs`.
6. Danh mục chính thức 114 xã/phường/đặc khu Hải Phòng (sau sáp nhập), thay ô nhập tự do.
7. Tính năng **"Chuyển máy chủ"**: đồng bộ toàn bộ dữ liệu sang máy chủ mới qua
   `/admin/receive-full-backup`, tự chuyển máy chủ cũ sang chế độ "đã đóng"/redirect
   (`_retired_response`) thay vì tắt đột ngột.
8. **Tài khoản quản trị viên riêng từng người** (`cdc_accounts`, `/cdc/login`) thay mật khẩu
   máy chủ dùng chung cho thao tác quản trị.
9. Tách 2 bản release riêng: `setup-server.iss` (chỉ Máy chủ) và `setup-admin.iss` (chỉ máy
   trạm quản trị). `setup.iss` gốc (3 chế độ) vẫn giữ cho máy đơn lẻ/máy trạm thường.
10. 4 file hướng dẫn PDF (`docs/huong-dan/`): xã/phường, máy chủ, máy trạm quản trị, Google
    Apps Script.
11. Di chuyển toàn bộ phát triển từ `Monsterph6/GSBTN` sang `cdc-hp/bcbtn` (repo chính thức).
12. Gộp tài liệu: `CLAUDE.md` (cốt lõi) + `TASKS.md` (file này) thay cho `SCHEMA.md`,
    `WEB_DEDUP_DESIGN.md`, `google_apps_script/README.md` (đã xoá, nội dung gộp vào
    `CLAUDE.md`).
13. **Cấu hình cột hiển thị danh sách ca bệnh** (`case_view_config.py`): chọn/đổi tên cột, thêm
    cột tính toán (tuổi, số ngày giữa 2 mốc, nối cột) — xem CLAUDE.md mục "Cấu hình cột hiển thị
    danh sách ca bệnh". `query_records`/`CASE_TABLE_COLUMNS` mở rộng để SELECT đủ 48 trường +
    `birth_year` thay vì 12 cột cố định như trước.

## Backlog — chưa cài đặt

Thứ tự không nhất thiết phản ánh độ ưu tiên; đánh giá lại theo nhu cầu triển khai thật.

- [ ] **HTTPS cho `lan_server.py`** — hiện dùng `http.server` thuần, mật khẩu/token truyền qua
      HTTP nếu chưa có TLS. Bắt buộc phải có trước khi mở máy chủ chính ra Internet lâu dài
      (không chỉ dựa vào reverse proxy tạm thời).
- [ ] **Mã hoá `national_id`/`phone` lúc lưu trữ** (Nghị định 13/2023/NĐ-CP) — cần thiết kế
      riêng vì ảnh hưởng trực tiếp thuật toán so khớp trùng hiện dựa trên so sánh giá trị
      thuần (mã hoá sẽ cần so khớp trên giá trị đã băm/mã hoá xác định — deterministic).
- [ ] **Khoá tài khoản sau nhiều lần đăng nhập sai** — hiện chỉ ghi `login_failed` vào
      `audit_log`, chưa tự khoá tài khoản (`commune_accounts` và `cdc_accounts`).
- [ ] **Bảng `communes` chuẩn hoá** — đã có danh mục 114 xã/phường/đặc khu nhưng chưa tách
      thành bảng riêng có mã chuẩn; `commune` trên mỗi bản ghi/tài khoản vẫn là chuỗi tự do.
- [ ] **Theo dõi tiến độ nộp báo cáo tuần** — dashboard CDC hiển thị ma trận Xã × Tuần (đã
      nộp/chưa nộp/trễ hạn), có thể nhắc email/SMS tự động vào ngày cố định mỗi tuần.
- [ ] **Đối soát ngược sau khi xã lọc trùng trên phần mềm Bộ Y tế** — xã nộp lại kết quả/mã ca
      đã xác nhận, hệ thống so khớp với `commune_export_batches` (bảng này chưa tồn tại) để
      biết ca nào xử lý xong, ca nào xã chưa phản hồi.
- [ ] **Giám sát vận hành** — cảnh báo khi máy chủ chính rớt mạng quá X phút, khi hàng đợi máy
      chủ phụ tồn đọng quá lâu chưa đồng bộ.
- [ ] **Lịch tự động cho đồng bộ máy chủ phụ** — hiện phải bấm tay "Đồng bộ máy chủ phụ"; GAS
      chưa tự lập lịch việc này.

## Câu hỏi còn mở (cần CDC xác nhận trước khi code hoá tiếp)

- Cách hiểu "ca vào viện gần nhất" khi chọn xã đại diện cho nhóm trùng khác xã: đang code theo
  nghĩa *ngày nhập viện mới nhất/gần hiện tại nhất* (nearest-to-now) — nếu ý đúng là "khoảng
  cách ngày nhập viện giữa 2 ca gần nhau nhất" thì quy tắc chọn xã cần sửa lại khác đi.
  (`core.py`, phần xuất Excel chia xã — xem mục "Xuất Excel chia theo xã" trong `CLAUDE.md`.)
- Tần suất/độ trễ chấp nhận được cho đồng bộ máy chủ phụ → máy chủ chính khi có lịch tự động
  (đề xuất tham khảo trước đây: 5 phút — chưa triển khai, xem mục "Lịch tự động" ở trên).
