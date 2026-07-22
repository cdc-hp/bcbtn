/**
 * "Cửa sổ online" (Google Apps Script) của máy chủ chính hệ thống Giám sát dịch bệnh.
 *
 * Máy chủ chính (lan_server.py) chỉ nghe trong LAN nội bộ CDC, nên Trạm Y tế xã ở xa không vào
 * thẳng được — họ dùng URL Web App này làm link nộp cố định. Với mỗi lần nộp, script thử
 * CHUYỂN TIẾP TRỰC TIẾP (server-to-server, qua UrlFetchApp) tới `MAIN_SERVER_URL` cấu hình
 * trong Script Properties, nếu máy chủ chính đó có địa chỉ Internet thật (domain/IP công khai,
 * đã mở cổng — xem google_apps_script/README.md). Chỉ khi KHÔNG chuyển tiếp được (lỗi mạng —
 * máy chủ chính offline/mất kết nối/chưa cấu hình `MAIN_SERVER_URL`) thì mới lưu file vào
 * Google Drive và ghi một dòng "chờ đồng bộ" vào Google Sheet gắn với script, để CDC đồng bộ
 * bù sau. `secondary_sync.py` (module Python) gọi `POST {action:"list_pending", key:...}` để
 * lấy các dòng đang chờ, tải nội dung base64 rồi đẩy vào hàng đợi nhập liệu cục bộ
 * (`import_queue`, source="server_phu"), sau đó gọi `POST {action:"mark_synced"}` để đánh dấu
 * đã đồng bộ — tránh kéo trùng lần sau. Mọi hành động đều qua POST (không dùng query string)
 * để khóa SHARED_KEY không lộ qua log truy cập/lịch sử trình duyệt.
 *
 * Sheet HangDoiPhu ghi nhận MỌI lượt nộp (kể cả chuyển tiếp trực tiếp thành công, status
 * "da_chuyen_tiep", không kèm file Drive) chứ không chỉ các lượt đệm tạm — để tab "Tình hình
 * nộp" (doGet) phản ánh đầy đủ, không bỏ sót lượt đã chuyển thẳng vào máy chủ chính.
 *
 * Triển khai: xem google_apps_script/README.md.
 */

var SHEET_NAME = "HangDoiPhu";
var HEADER = ["commune", "week", "file_name", "drive_file_id", "submitted_by", "received_at", "status", "synced_at"];
var ROOT_FOLDER_NAME = "MayChuPhu_GSBTN";
var COL_STATUS = 7;
var COL_SYNCED_AT = 8;

// Folder Drive dùng làm hàng chờ mặc định (không chia sẻ công khai — chỉ tài khoản sở hữu
// script và người CDC được cấp quyền mới xem được). Có thể ghi đè bằng Script Property
// ROOT_FOLDER_ID nếu sau này đổi sang folder khác mà không cần sửa mã nguồn.
var DEFAULT_ROOT_FOLDER_ID = "1Flis9O2NoobRPuhZewb_y762FEIEa_VP";

var STATUS_LABELS = {
  da_chuyen_tiep: "Đã chuyển tiếp trực tiếp vào máy chủ chính",
  cho_dong_bo: "Đang chờ đồng bộ (lưu tạm trên máy chủ phụ)",
  da_dong_bo: "Đã đồng bộ vào máy chủ chính",
};

/**
 * Danh mục chính thức 114 đơn vị hành chính cấp xã của thành phố Hải Phòng (67 xã, 45 phường,
 * 2 đặc khu), theo Nghị quyết số 1669/NQ-UBTVQH15 ngày 16/6/2025 của Ủy ban Thường vụ Quốc hội,
 * hiệu lực từ 1/7/2025. Dùng làm danh sách chọn cố định (dropdown) thay cho ô nhập tên xã tự
 * do trước đây — tránh sai chính tả/không thống nhất tên đơn vị giữa các lần nộp (hạn chế đã
 * ghi nhận ở WEB_DEDUP_DESIGN.md mục 8, "communes... Chưa cài đặt").
 */
var COMMUNES = [
  "Phường Thủy Nguyên", "Phường Thiên Hương", "Phường Hòa Bình", "Phường Nam Triệu",
  "Phường Bạch Đằng", "Phường Lưu Kiếm", "Phường Lê Ích Mộc", "Phường Hồng Bàng",
  "Phường Hồng An", "Phường Ngô Quyền", "Phường Gia Viên", "Phường Lê Chân",
  "Phường An Biên", "Phường Hải An", "Phường Đông Hải", "Phường Kiến An",
  "Phường Phù Liễn", "Phường Nam Đồ Sơn", "Phường Đồ Sơn", "Phường Hưng Đạo",
  "Phường Dương Kinh", "Phường An Dương", "Phường An Hải", "Phường An Phong",
  "Phường Hải Dương", "Phường Lê Thanh Nghị", "Phường Việt Hòa", "Phường Thành Đông",
  "Phường Nam Đồng", "Phường Tân Hưng", "Phường Thạch Khôi", "Phường Tứ Minh",
  "Phường Ái Quốc", "Phường Chu Văn An", "Phường Chí Linh", "Phường Trần Hưng Đạo",
  "Phường Nguyễn Trãi", "Phường Trần Nhân Tông", "Phường Lê Đại Hành", "Phường Kinh Môn",
  "Phường Nguyễn Đại Năng", "Phường Trần Liễu", "Phường Bắc An Phụ", "Phường Phạm Sư Mạnh",
  "Phường Nhị Chiểu",
  "Xã An Hưng", "Xã An Khánh", "Xã An Quang", "Xã An Trường", "Xã An Lão",
  "Xã Kiến Thụy", "Xã Kiến Minh", "Xã Kiến Hải", "Xã Kiến Hưng", "Xã Nghi Dương",
  "Xã Quyết Thắng", "Xã Tiên Lãng", "Xã Tân Minh", "Xã Tiên Minh", "Xã Chấn Hưng",
  "Xã Hùng Thắng", "Xã Vĩnh Bảo", "Xã Nguyễn Bỉnh Khiêm", "Xã Vĩnh Am", "Xã Vĩnh Hải",
  "Xã Vĩnh Hòa", "Xã Vĩnh Thịnh", "Xã Vĩnh Thuận", "Xã Việt Khê", "Xã Nam An Phụ",
  "Xã Nam Sách", "Xã Thái Tân", "Xã Trần Phú", "Xã Hợp Tiến", "Xã An Phú",
  "Xã Thanh Hà", "Xã Hà Tây", "Xã Hà Bắc", "Xã Hà Nam", "Xã Hà Đông",
  "Xã Mao Điền", "Xã Cẩm Giàng", "Xã Cẩm Giang", "Xã Tuệ Tĩnh", "Xã Kẻ Sặt",
  "Xã Bình Giang", "Xã Đường An", "Xã Thượng Hồng", "Xã Gia Lộc", "Xã Yết Kiêu",
  "Xã Gia Phúc", "Xã Trường Tân", "Xã Tứ Kỳ", "Xã Tân Kỳ", "Xã Đại Sơn",
  "Xã Chí Minh", "Xã Lạc Phượng", "Xã Nguyên Giáp", "Xã Ninh Giang", "Xã Vĩnh Lại",
  "Xã Khúc Thừa Dụ", "Xã Tân An", "Xã Hồng Châu", "Xã Thanh Miện", "Xã Bắc Thanh Miện",
  "Xã Hải Hưng", "Xã Nguyễn Lương Bằng", "Xã Nam Thanh Miện", "Xã Phú Thái", "Xã Lai Khê",
  "Xã An Thành", "Xã Kim Thành",
  "Đặc khu Cát Hải", "Đặc khu Bạch Long Vĩ",
];

function doGet(e) {
  return HtmlService.createHtmlOutput(buildPageHtml(COMMUNES))
    .setTitle("Nộp danh sách ca bệnh — máy chủ phụ")
    .addMetaTag("viewport", "width=device-width, initial-scale=1")
    // Mặc định Apps Script chặn nhúng iframe từ domain khác (X-Frame-Options: SAMEORIGIN) —
    // cần mở rõ để trang GitHub Pages (docs/index.html) nhúng được trang này trong <iframe>.
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function doPost(e) {
  try {
    var payload = JSON.parse((e.postData && e.postData.contents) || "{}");
    var result;
    if (payload.action === "submit") {
      result = handleSubmit(payload);
    } else if (payload.action === "mark_synced") {
      result = handleMarkSynced(payload);
    } else if (payload.action === "list_pending") {
      result = listPending(payload.key);
    } else if (payload.action === "list_status") {
      result = listStatus(payload.key, payload.commune);
    } else {
      throw new Error("Hành động không hợp lệ.");
    }
    return jsonResponse(true, result);
  } catch (err) {
    return jsonResponse(false, errorMessage(err));
  }
}

function jsonResponse(ok, resultOrError) {
  var body = ok ? { ok: true, result: resultOrError } : { ok: false, error: String(resultOrError) };
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}

function errorMessage(err) {
  return (err && err.message) ? err.message : String(err);
}

function constantTimeEquals(a, b) {
  a = String(a || "");
  b = String(b || "");
  // So sánh đủ độ dài của chuỗi dài hơn để thời gian chạy không lộ rõ độ dài khớp/không khớp.
  var length = Math.max(a.length, b.length);
  var diff = a.length ^ b.length;
  for (var i = 0; i < length; i++) {
    var codeA = i < a.length ? a.charCodeAt(i) : 0;
    var codeB = i < b.length ? b.charCodeAt(i) : 0;
    diff |= codeA ^ codeB;
  }
  return diff === 0;
}

function checkKey(key) {
  var expected = PropertiesService.getScriptProperties().getProperty("SHARED_KEY");
  if (!expected) {
    throw new Error("Chưa cấu hình SHARED_KEY trong Script Properties (Project Settings).");
  }
  if (!constantTimeEquals(key, expected)) {
    throw new Error("Sai khóa xác thực máy chủ phụ.");
  }
}

/**
 * Script này là standalone (không gắn sẵn vào 1 Google Sheet cụ thể), nên không dùng
 * SpreadsheetApp.getActiveSpreadsheet() (luôn null ngoài ngữ cảnh container-bound). Thay vào
 * đó, tự tạo 1 Spreadsheet ở lần chạy đầu tiên và ghi nhớ ID trong Script Properties để các lần
 * sau dùng lại đúng file đó.
 */
function getOrCreateSpreadsheet() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty("SPREADSHEET_ID");
  if (id) {
    try {
      return SpreadsheetApp.openById(id);
    } catch (err) {
      // ID cũ không còn hợp lệ (bị xoá/mất quyền) -> tạo lại bên dưới.
    }
  }
  var ss = SpreadsheetApp.create("GSBTN - Hang doi phu");
  props.setProperty("SPREADSHEET_ID", ss.getId());
  return ss;
}

function getSheet() {
  var ss = getOrCreateSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(HEADER);
  }
  return sheet;
}

function getOrCreateFolder(parent, name) {
  var it = parent.getFoldersByName(name);
  return it.hasNext() ? it.next() : parent.createFolder(name);
}

function getUploadFolder(commune, week) {
  var root = getOrCreateFolder(DriveApp.getRootFolder(), ROOT_FOLDER_NAME);
  var communeFolder = getOrCreateFolder(root, commune);
  return getOrCreateFolder(communeFolder, week);
}

var MAX_FILE_BYTES = 20 * 1024 * 1024; // Máy chủ phụ chỉ là bộ đệm tạm — giới hạn chặt hơn 100MB phía máy chủ chính.
var XLSX_SIGNATURE = [0x50, 0x4b, 0x03, 0x04]; // "PK\x03\x04" — chữ ký đầu file .xlsx/.xlsm (định dạng ZIP).

function hasXlsxSignature(bytes) {
  if (bytes.length < XLSX_SIGNATURE.length) return false;
  for (var i = 0; i < XLSX_SIGNATURE.length; i++) {
    var value = bytes[i];
    if (value < 0) value += 256; // byte[] trong Apps Script trả số có dấu cho giá trị > 127.
    if (value !== XLSX_SIGNATURE[i]) return false;
  }
  return true;
}

function logStatusRow(commune, week, fileName, driveFileId, submittedBy, status) {
  var sheet = getSheet();
  var now = new Date();
  sheet.appendRow([commune, week, fileName, driveFileId, submittedBy, now, status, status === "da_chuyen_tiep" ? now : ""]);
}

function handleSubmit(payload) {
  checkKey(payload.key);
  var commune = String(payload.commune || "").trim();
  var week = String(payload.week || "").trim();
  var fileName = String(payload.file_name || "du_lieu.xlsx");
  var submittedBy = String(payload.submitted_by || "");
  var contentBase64 = payload.content_base64;
  if (!commune) throw new Error("Thiếu tên xã.");
  if (!week) throw new Error("Thiếu tuần báo cáo.");
  if (!contentBase64) throw new Error("Thiếu nội dung file.");
  var bytes = Utilities.base64Decode(contentBase64);
  if (bytes.length > MAX_FILE_BYTES) {
    throw new Error("File vượt quá giới hạn " + Math.floor(MAX_FILE_BYTES / (1024 * 1024)) + " MB.");
  }
  if (!hasXlsxSignature(bytes)) {
    throw new Error("Nội dung không đúng định dạng file Excel (.xlsx/.xlsm).");
  }

  var forwarded = tryForwardToMainServer(commune, week, fileName, contentBase64, submittedBy);
  if (forwarded) {
    logStatusRow(commune, week, fileName, "", submittedBy, "da_chuyen_tiep");
    return forwarded;
  }

  // Không chuyển tiếp trực tiếp được (chưa cấu hình MAIN_SERVER_URL hoặc lỗi mạng) -> đệm tạm.
  var blob = Utilities.newBlob(bytes, MimeType.MICROSOFT_EXCEL, fileName);
  var folder = getUploadFolder(commune, week);
  var file = folder.createFile(blob);
  var sheet = getSheet();
  var now = new Date();
  sheet.appendRow([commune, week, fileName, file.getId(), submittedBy, now, "cho_dong_bo", ""]);
  return { row: sheet.getLastRow(), file_id: file.getId(), forwarded: false };
}

/**
 * Thử gửi thẳng tới máy chủ chính (POST {MAIN_SERVER_URL}/queue/submit). Trả về kết quả (đã
 * gắn forwarded=true) nếu máy chủ chính PHẢN HỒI (kể cả phản hồi lỗi thật — sai mật khẩu, dữ
 * liệu không hợp lệ — thì báo lỗi đó thẳng, không đệm ngầm để tránh lặp lại lỗi khi đồng bộ
 * sau). Trả về null (để hàm gọi rơi xuống nhánh đệm Sheet/Drive) khi chưa cấu hình
 * MAIN_SERVER_URL hoặc gặp lỗi mạng (không tới được máy chủ chính).
 */
function tryForwardToMainServer(commune, week, fileName, contentBase64, submittedBy) {
  var props = PropertiesService.getScriptProperties();
  var mainUrl = props.getProperty("MAIN_SERVER_URL");
  if (!mainUrl) return null;
  var password = props.getProperty("MAIN_SERVER_PASSWORD") || "";
  var headers = { "Content-Type": "application/json" };
  if (password) headers["X-GSBTN-Password"] = password;
  var options = {
    method: "post",
    contentType: "application/json",
    headers: headers,
    payload: JSON.stringify({
      commune: commune, week: week, file_name: fileName, content_base64: contentBase64,
      submitted_by: submittedBy,
    }),
    muteHttpExceptions: true,
  };
  var response;
  try {
    response = UrlFetchApp.fetch(mainUrl.replace(/\/+$/, "") + "/queue/submit", options);
  } catch (err) {
    return null; // Lỗi mạng (không tới được máy chủ chính) -> đệm tạm thay vì báo lỗi cho xã.
  }
  var code = response.getResponseCode();
  var body;
  try {
    body = JSON.parse(response.getContentText());
  } catch (err) {
    throw new Error("Máy chủ chính phản hồi không hợp lệ (HTTP " + code + ").");
  }
  if (code < 200 || code >= 300 || !body.ok) {
    // Máy chủ chính CÓ phản hồi nhưng từ chối -> báo lỗi thật, không đệm ngầm.
    throw new Error((body && body.error) || ("Máy chủ chính từ chối yêu cầu (HTTP " + code + ")."));
  }
  var result = body.result || {};
  result.forwarded = true;
  return result;
}

function handleMarkSynced(payload) {
  checkKey(payload.key);
  var rows = payload.rows || [];
  var sheet = getSheet();
  var now = new Date();
  rows.forEach(function (rowIndex) {
    sheet.getRange(rowIndex, COL_STATUS).setValue("da_dong_bo");
    sheet.getRange(rowIndex, COL_SYNCED_AT).setValue(now);
  });
  return { marked: rows };
}

function listPending(key) {
  checkKey(key);
  var sheet = getSheet();
  var values = sheet.getDataRange().getValues();
  var result = [];
  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    if (row[6] === "cho_dong_bo") {
      var fileId = row[3];
      var bytes = DriveApp.getFileById(fileId).getBlob().getBytes();
      result.push({
        row: r + 1,
        commune: row[0],
        week: row[1],
        file_name: row[2],
        submitted_by: row[4],
        content_base64: Utilities.base64Encode(bytes),
      });
    }
  }
  return result;
}

/**
 * Tình hình nộp của MỘT đơn vị (xã), lọc theo commune truyền lên — dùng cho tab "Tình hình
 * nộp" trên doGet. Yêu cầu cùng SHARED_KEY với việc nộp (xã nào cũng có key này, xem
 * "Giới hạn đã biết" trong google_apps_script/README.md — chưa có tài khoản riêng từng xã ở
 * tầng GAS nên chưa tách được quyền xem theo xã).
 */
function listStatus(key, commune) {
  checkKey(key);
  commune = String(commune || "").trim().toLowerCase();
  if (!commune) throw new Error("Chưa chọn đơn vị.");
  var sheet = getSheet();
  var values = sheet.getDataRange().getValues();
  var result = [];
  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    if (String(row[0] || "").trim().toLowerCase() === commune) {
      var receivedAt = row[5];
      result.push({
        week: row[1],
        file_name: row[2],
        submitted_by: row[4],
        received_at: receivedAt instanceof Date ? receivedAt.toISOString() : String(receivedAt),
        status: row[6],
        status_label: STATUS_LABELS[row[6]] || row[6],
      });
    }
  }
  result.sort(function (a, b) { return new Date(b.received_at) - new Date(a.received_at); });
  return result.slice(0, 200);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

function buildPageHtml(communes) {
  var options = communes.map(function (c) {
    return '<option value="' + escapeHtml(c) + '">' + escapeHtml(c) + "</option>";
  }).join("");

  return (
    '<!doctype html><html lang="vi"><head><meta charset="utf-8">' +
    '<style>' +
    "body{font-family:system-ui,sans-serif;max-width:640px;margin:24px auto;padding:0 16px;color:#1f2937}" +
    "h1{font-size:1.3rem}" +
    ".tabs{display:flex;gap:8px;border-bottom:1px solid #e2e8f0;margin-bottom:16px}" +
    ".tab-btn{padding:10px 14px;border:none;background:none;cursor:pointer;font-size:1rem;color:#64748b;border-bottom:2px solid transparent}" +
    ".tab-btn.active{color:#2563eb;border-bottom-color:#2563eb;font-weight:600}" +
    ".tab-panel{display:none}.tab-panel.active{display:block}" +
    "label{display:block;margin-top:12px;font-weight:600}" +
    "input,select{width:100%;padding:8px;margin-top:4px;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:6px;font-size:1rem}" +
    "button{margin-top:18px;padding:10px 16px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:1rem}" +
    "#msg,#statusMsg{margin-top:16px;padding:10px;border-radius:6px;display:none}" +
    "#msg.ok,#statusMsg.ok{background:#dcfce7;color:#166534;display:block}" +
    "#msg.err,#statusMsg.err{background:#fee2e2;color:#991b1b;display:block}" +
    "table{width:100%;border-collapse:collapse;margin-top:16px;font-size:0.9rem}" +
    "th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #e2e8f0}" +
    "th{background:#f8fafc}" +
    "</style></head><body>" +
    "<h1>Nộp danh sách ca bệnh hằng tuần</h1>" +
    '<div class="tabs">' +
    '<button type="button" class="tab-btn active" data-tab="submit">Nộp báo cáo</button>' +
    '<button type="button" class="tab-btn" data-tab="status">Tình hình nộp</button>' +
    "</div>" +

    '<div id="panel-submit" class="tab-panel active">' +
    "<p>Đây là link cố định để nộp mỗi tuần. Hệ thống tự chuyển thẳng tới máy chủ chính; nếu máy chủ chính tạm thời không phản hồi được, dữ liệu sẽ lưu tạm và CDC đồng bộ bù sau.</p>" +
    '<form id="f">' +
    "<label>Xã / phường / đặc khu</label><select name=\"commune\" required><option value=\"\">-- Chọn đơn vị --</option>" + options + "</select>" +
    '<label>Tuần báo cáo</label><input name="week" required placeholder="2026-W29">' +
    "<label>Người nộp</label><input name=\"submitted_by\">" +
    '<label>Khóa máy chủ phụ (do CDC cung cấp)</label><input name="key" type="password" required>' +
    '<label>File Excel theo mẫu (.xlsx)</label><input name="file" type="file" accept=".xlsx,.xlsm" required>' +
    '<button type="submit">Nộp báo cáo</button></form><div id="msg"></div>' +
    "</div>" +

    '<div id="panel-status" class="tab-panel">' +
    "<p>Xem các lần nộp gần đây của đơn vị mình (tối đa 200 lượt gần nhất).</p>" +
    '<form id="sf">' +
    "<label>Đơn vị</label><select name=\"communeSelect\" required><option value=\"\">-- Chọn đơn vị --</option>" + options + "</select>" +
    '<label>Khóa máy chủ phụ (do CDC cung cấp)</label><input name="key" type="password" required>' +
    '<button type="submit">Xem tình hình nộp</button></form><div id="statusMsg"></div>' +
    '<div id="statusTableWrap"></div>' +
    "</div>" +

    "<script>" +
    'document.querySelectorAll(".tab-btn").forEach(function (btn) {' +
    '  btn.addEventListener("click", function () {' +
    '    document.querySelectorAll(".tab-btn").forEach(function (b) { b.classList.remove("active"); });' +
    '    document.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("active"); });' +
    '    btn.classList.add("active");' +
    '    document.getElementById("panel-" + btn.dataset.tab).classList.add("active");' +
    "  });" +
    "});" +

    'document.getElementById("f").addEventListener("submit", function (ev) {' +
    "  ev.preventDefault();" +
    '  var form = ev.target, msg = document.getElementById("msg"), file = form.file.files[0];' +
    "  if (!file) return;" +
    "  var reader = new FileReader();" +
    "  reader.onload = function () {" +
    '    var base64 = reader.result.split(",")[1];' +
    "    fetch(window.location.href, {" +
    '      method: "POST",' +
    '      body: JSON.stringify({ action: "submit", commune: form.commune.value, week: form.week.value,' +
    "        submitted_by: form.submitted_by.value, key: form.key.value, file_name: file.name, content_base64: base64 })," +
    "    }).then(function (r) { return r.json(); }).then(function (data) {" +
    '      if (data.ok && data.result.forwarded) { msg.className = "ok"; msg.textContent = "Đã nộp trực tiếp vào máy chủ chính, mã hàng đợi #" + data.result.queue_id + "."; form.reset(); }' +
    '      else if (data.ok) { msg.className = "ok"; msg.textContent = "Máy chủ chính tạm thời không phản hồi — đã lưu tạm, dòng #" + data.result.row + ". CDC sẽ đồng bộ bù sau."; form.reset(); }' +
    '      else { msg.className = "err"; msg.textContent = "Lỗi: " + data.error; }' +
    '    }).catch(function (e) { msg.className = "err"; msg.textContent = "Lỗi kết nối: " + e; });' +
    "  };" +
    "  reader.readAsDataURL(file);" +
    "});" +

    'document.getElementById("sf").addEventListener("submit", function (ev) {' +
    "  ev.preventDefault();" +
    "  var form = ev.target;" +
    '  var msg = document.getElementById("statusMsg");' +
    '  var wrap = document.getElementById("statusTableWrap");' +
    '  var commune = (form.communeSelect.value || "").trim();' +
    "  wrap.innerHTML = '';" +
    "  if (!commune) {" +
    '    msg.className = "err"; msg.textContent = "Chọn hoặc nhập tên đơn vị trước.";' +
    "    return;" +
    "  }" +
    "  fetch(window.location.href, {" +
    '    method: "POST",' +
    '    body: JSON.stringify({ action: "list_status", commune: commune, key: form.key.value }),' +
    "  }).then(function (r) { return r.json(); }).then(function (data) {" +
    "    if (!data.ok) {" +
    '      msg.className = "err"; msg.textContent = "Lỗi: " + data.error;' +
    "      return;" +
    "    }" +
    "    var rows = data.result;" +
    "    if (!rows.length) {" +
    '      msg.className = "ok"; msg.textContent = "Đơn vị \\"" + commune + "\\" chưa có lượt nộp nào được ghi nhận.";' +
    "      return;" +
    "    }" +
    '    msg.className = "ok"; msg.textContent = rows.length + " lượt nộp gần nhất của \\"" + commune + "\\":";' +
    '    var html = "<table><thead><tr><th>Tuần</th><th>Thời điểm nộp</th><th>Người nộp</th><th>Trạng thái</th><th>File</th></tr></thead><tbody>";' +
    "    rows.forEach(function (row) {" +
    '      var t = new Date(row.received_at);' +
    '      var tStr = isNaN(t.getTime()) ? row.received_at : t.toLocaleString("vi-VN");' +
    '      html += "<tr><td>" + row.week + "</td><td>" + tStr + "</td><td>" + (row.submitted_by || "") + "</td><td>" + row.status_label + "</td><td>" + row.file_name + "</td></tr>";' +
    "    });" +
    '    html += "</tbody></table>";' +
    "    wrap.innerHTML = html;" +
    "  }).catch(function (e) { msg.className = \"err\"; msg.textContent = \"Lỗi kết nối: \" + e; });" +
    "});" +
    "</script></body></html>"
  );
}
