/**
 * "Cửa sổ online" (Google Apps Script) của máy chủ chính hệ thống Giám sát dịch bệnh.
 *
 * Máy chủ chính (lan_server.py) chỉ nghe trong LAN nội bộ CDC, nên Trạm Y tế xã ở xa không vào
 * thẳng được — họ dùng URL Web App này làm link nộp cố định. Với mỗi lần nộp, script thử
 * CHUYỂN TIẾP TRỰC TIẾP (server-to-server, qua UrlFetchApp) tới `MAIN_SERVER_URL` cấu hình
 * trong Script Properties, nếu máy chủ chính đó có địa chỉ Internet thật (domain/IP công khai,
 * đã mở cổng — xem CLAUDE.md). Chỉ khi KHÔNG chuyển tiếp được (lỗi mạng —
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
 * Triển khai: xem CLAUDE.md (mục Google Apps Script) hoặc docs/huong-dan/4-google-apps-script.pdf.
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

// File mẫu Excel (48 trường, khớp CASE_FIELDS trong core.py) — lưu tĩnh trên GitHub Pages
// cùng repo với trang iframe (docs/Mau_Danh_sach_ca_benh.xlsx), tải công khai không cần xác thực.
var TEMPLATE_URL = "https://cdc-hp.github.io/bcbtn/Mau_Danh_sach_ca_benh.xlsx";

// Logo CDC Hải Phòng — cùng lưu tĩnh trên GitHub Pages (docs/logo.png) thay vì nhúng base64
// vào Code.gs, để đổi logo sau này chỉ cần thay file, không cần deploy lại Apps Script.
var LOGO_URL = "https://cdc-hp.github.io/bcbtn/logo.png";

var STATUS_LABELS = {
  da_chuyen_tiep: "Đã chuyển tiếp trực tiếp vào máy chủ chính",
  cho_dong_bo: "Đang chờ đồng bộ (lưu tạm trên máy chủ phụ)",
  da_dong_bo: "Đã đồng bộ vào máy chủ chính",
};

/**
 * Danh mục chính thức 114 đơn vị hành chính cấp xã của thành phố Hải Phòng (67 xã, 45 phường,
 * 2 đặc khu), theo Nghị quyết số 1669/NQ-UBTVQH15 ngày 16/6/2025 của Ủy ban Thường vụ Quốc hội,
 * hiệu lực từ 1/7/2025. Dùng làm danh sách chọn cố định (dropdown có tìm kiếm) thay cho ô nhập
 * tên xã tự do trước đây — tránh sai chính tả/không thống nhất tên đơn vị giữa các lần nộp (hạn
 * chế đã ghi nhận ở TASKS.md, mục "communes chuẩn hoá").
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
  // buildPageHtml() đã tự có <meta viewport> riêng trong <head> — không cần addMetaTag nữa.
  return HtmlService.createHtmlOutput(buildPageHtml(COMMUNES))
    .setTitle("Nộp danh sách ca bệnh — máy chủ phụ")
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

/**
 * Chuỗi tuần ISO-8601 (vd "2026-W29") của 1 ngày — dùng cả khi hiển thị mặc định trên form lẫn
 * khi máy chủ tự kiểm tra tuần nộp không được vượt quá tuần hiện tại (không tin hoàn toàn vào
 * việc trình duyệt xã đã chặn đúng — kiểm tra lại phía server).
 */
function isoWeekString(date) {
  var d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  var dayNum = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - dayNum + 3);
  var firstThursday = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  var firstDayNum = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstDayNum + 3);
  var weekNum = 1 + Math.round((d - firstThursday) / (7 * 24 * 3600 * 1000));
  return d.getUTCFullYear() + "-W" + (weekNum < 10 ? "0" : "") + weekNum;
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
  if (COMMUNES.indexOf(commune) === -1) {
    throw new Error("Đơn vị không hợp lệ — vui lòng chọn đúng tên từ danh sách gợi ý.");
  }
  if (!/^\d{4}-W\d{2}$/.test(week)) {
    throw new Error("Định dạng tuần báo cáo không hợp lệ.");
  }
  if (week > isoWeekString(new Date())) {
    throw new Error("Không được chọn tuần báo cáo trong tương lai.");
  }
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

/**
 * Đánh dấu các dòng đã được máy chủ chính kéo về thành công. Đồng thời XOÁ (đưa vào Thùng rác
 * Drive, không xoá vĩnh viễn — tự dọn hẳn sau ~30 ngày theo chính sách Drive) file Excel gốc
 * tương ứng, vì dữ liệu đã nằm an toàn trong CSDL chính — tránh Drive phình to theo thời gian.
 * Lỗi xoá file (đã bị xoá tay từ trước, mất quyền...) không chặn việc đánh dấu đồng bộ.
 */
function handleMarkSynced(payload) {
  checkKey(payload.key);
  var rows = payload.rows || [];
  var sheet = getSheet();
  var now = new Date();
  rows.forEach(function (rowIndex) {
    var fileId = sheet.getRange(rowIndex, 4).getValue();
    if (fileId) {
      try {
        DriveApp.getFileById(fileId).setTrashed(true);
      } catch (err) {
        // Bỏ qua — file có thể đã bị xoá tay từ trước hoặc mất quyền truy cập.
      }
    }
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
 * Mốc tuần (ISO, dạng "YYYY-Www") mà CDC bắt đầu yêu cầu nộp báo cáo hằng tuần — dùng để tính
 * "tuần chưa báo cáo" trên tab Tình hình nộp (không tính các tuần trước khi hệ thống bắt đầu
 * vận hành). Cấu hình 1 lần trong Script Properties (Project Settings), không có sẵn giá trị
 * mặc định — nếu chưa cấu hình, client chỉ hiện thông báo hướng dẫn thay vì đoán bừa mốc tuần.
 */
function getTrackingStartWeek() {
  return PropertiesService.getScriptProperties().getProperty("TRACKING_START_WEEK") || "";
}

/**
 * Tiện ích quản trị: đặt 1 Script Property qua dòng lệnh thay vì phải mở script.google.com —
 * ví dụ `clasp run setScriptProperty --params '["TRACKING_START_WEEK","2026-W30"]'`. Chỉ gọi
 * được bởi người có quyền chỉnh sửa project (Apps Script Execution API đòi quyền editor/owner),
 * không lộ ra ngoài qua doGet/doPost nên các xã không thể gọi hàm này.
 */
function setScriptProperty(name, value) {
  PropertiesService.getScriptProperties().setProperty(name, value);
  return PropertiesService.getScriptProperties().getProperty(name);
}

/**
 * Tình hình nộp của MỘT đơn vị (xã), lọc theo commune truyền lên — dùng cho tab "Tình hình
 * nộp" trên doGet. Yêu cầu cùng SHARED_KEY với việc nộp (xã nào cũng có key này, xem
 * xem CLAUDE.md, mục Google Apps Script — chưa có tài khoản riêng từng xã ở
 * tầng GAS nên chưa tách được quyền xem theo xã).
 *
 * Trả về cả `tracking_start_week` để client tự tính danh sách tuần chưa báo cáo (mục "Tuần
 * chưa báo cáo" bên phải bảng lượt nộp) — client đã sẵn có các hàm tính tuần ISO nên không cần
 * lặp lại logic đó ở phía Apps Script.
 */
function listStatus(key, commune) {
  checkKey(key);
  commune = String(commune || "").trim().toLowerCase();
  if (!commune) throw new Error("Chưa chọn đơn vị.");
  var sheet = getSheet();
  var values = sheet.getDataRange().getValues();
  var rows = [];
  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    if (String(row[0] || "").trim().toLowerCase() === commune) {
      var receivedAt = row[5];
      rows.push({
        week: row[1],
        file_name: row[2],
        submitted_by: row[4],
        received_at: receivedAt instanceof Date ? receivedAt.toISOString() : String(receivedAt),
        status: row[6],
        status_label: STATUS_LABELS[row[6]] || row[6],
      });
    }
  }
  rows.sort(function (a, b) { return new Date(b.received_at) - new Date(a.received_at); });
  return { rows: rows.slice(0, 200), tracking_start_week: getTrackingStartWeek() };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

function buildPageHtml(communes) {
  var communesJson = JSON.stringify(communes);
  // Datalist dùng chung cho mọi ô chọn đơn vị (input list=... để gõ tìm trong 114 đơn vị
  // thay vì cuộn 1 select dài — item 1 yêu cầu cập nhật).
  var options = communes.map(function (c) {
    return '<option value="' + escapeHtml(c) + '">';
  }).join("");

  return `<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nộp danh sách ca bệnh — CDC Hải Phòng</title>
<style>
  :root {
    --blue-900:#1e3a8a; --blue-600:#2563eb; --blue-600h:#1d4ed8; --blue-50:#eff6ff;
    --green-700:#166534; --green-50:#dcfce7;
    --red-700:#991b1b; --red-50:#fee2e2; --red-600:#dc2626;
    --amber-700:#92400e; --amber-50:#fef3c7;
    --slate-900:#1f2937; --slate-500:#64748b; --slate-300:#cbd5e1; --slate-200:#e2e8f0; --slate-50:#f8fafc;
  }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    margin: 0; background: var(--slate-200); color: var(--slate-900); -webkit-font-smoothing: antialiased;
  }
  .page { max-width: 640px; margin: 0 auto; padding-bottom: 32px; }
  .app-header {
    background: var(--blue-50); padding: 18px 20px 24px; border-radius: 0 0 22px 22px;
    box-shadow: 0 3px 10px rgba(30,58,138,.10);
  }
  .app-header-inner { display: flex; align-items: center; gap: 12px; }
  .logo-badge { flex: none; width: 44px; height: 44px; border-radius: 12px; object-fit: contain;
    box-shadow: 0 1px 4px rgba(30,58,138,.20); background: #fff; }
  .app-header h1 { font-size: 1.15rem; margin: 0; font-weight: 700; color: var(--blue-900); }
  .app-header p { margin: 2px 0 0; font-size: .85rem; color: var(--slate-500); }

  .content { margin: 16px 16px 0; }

  .card { background: #fff; border-radius: 14px; padding: 20px; border: 1px solid var(--slate-200);
    box-shadow: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04); }
  .lede { font-size: .88rem; color: var(--slate-500); margin: 0 0 16px; line-height: 1.5; }
  .missing-notice { color: var(--red-600); font-weight: 600; font-size: .88rem; line-height: 1.6; margin: 0 0 16px; }

  label { display: block; margin-top: 14px; font-weight: 600; font-size: .88rem; }
  label:first-of-type { margin-top: 0; }
  label .req { color: var(--red-600); }
  input[type=text], input[type=password], input[type=week], input:not([type]) {
    width: 100%; padding: 11px 12px; margin-top: 6px; border: 1px solid var(--slate-300);
    border-radius: 9px; font-size: 1rem; background: #fff; color: var(--slate-900);
  }
  input:focus { outline: none; border-color: var(--blue-600); box-shadow: 0 0 0 3px var(--blue-50); }
  .hint { font-size: .8rem; color: var(--slate-500); margin-top: 5px; }
  .hint a { color: var(--blue-600); }

  .dropzone { margin-top: 8px; border: 2px dashed var(--slate-300); border-radius: 12px; padding: 22px 16px;
    text-align: center; cursor: pointer; background: var(--slate-50); transition: border-color .15s, background .15s; }
  .dropzone.drag { border-color: var(--blue-600); background: var(--blue-50); }
  .dropzone:focus { outline: 2px solid var(--blue-600); outline-offset: 2px; }
  .dropzone-icon { font-size: 1.6rem; }
  .dropzone-text { font-size: .9rem; margin-top: 6px; }
  .dropzone-text b { color: var(--blue-600); font-weight: 600; }
  .dropzone-hint { font-size: .78rem; color: var(--slate-500); margin-top: 4px; }

  .file-chip { margin-top: 8px; display: flex; align-items: center; gap: 8px; background: var(--blue-50);
    border: 1px solid #bfdbfe; border-radius: 10px; padding: 10px 12px; font-size: .86rem; }
  .file-chip .file-info { flex: 1; min-width: 0; }
  .file-chip .fname { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .file-chip .fsize { color: var(--slate-500); font-size: .78rem; }
  .file-chip button { flex: none; border: none; background: none; color: var(--slate-500); cursor: pointer;
    font-size: 1rem; padding: 2px 6px; border-radius: 6px; }
  .file-chip button:hover { background: rgba(0,0,0,.06); color: var(--red-600); }

  button[type=submit] { margin-top: 20px; width: 100%; padding: 13px 16px; background: var(--blue-600); color: #fff;
    border: none; border-radius: 10px; cursor: pointer; font-size: 1rem; font-weight: 600; transition: background .15s; }
  button[type=submit]:hover { background: var(--blue-600h); }
  button[type=submit]:disabled { background: var(--slate-300); cursor: not-allowed; }
  .btn-secondary { padding: 9px 12px; background: #fff; color: var(--blue-600); border: 1px solid var(--blue-600);
    border-radius: 8px; cursor: pointer; font-size: .85rem; font-weight: 600; }
  .btn-secondary:hover { background: var(--blue-50); }
  .link-btn { font-size: .82rem; color: var(--blue-600); cursor: pointer; text-decoration: underline;
    background: none; border: none; padding: 0; margin-top: 14px; display: inline-block; }

  .spinner { display: inline-block; width: 15px; height: 15px; border: 2px solid rgba(255,255,255,.4);
    border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; vertical-align: -3px; margin-right: 7px; }
  @keyframes spin { to { transform: rotate(360deg); } }

  #msg { margin-top: 16px; padding: 12px 14px; border-radius: 10px; display: none; font-size: .88rem; line-height: 1.5; }
  #msg.ok { background: var(--green-50); color: var(--green-700); display: block; }
  #msg.err { background: var(--red-50); color: var(--red-700); display: block; }

  .footer-note { text-align: center; font-size: .76rem; color: var(--slate-500); margin-top: 20px; }
</style>
</head>
<body>
<div class="page">
  <div class="app-header">
    <div class="app-header-inner">
      <img class="logo-badge" src="${LOGO_URL}" alt="CDC Hải Phòng">
      <div>
        <h1>Nộp danh sách ca bệnh</h1>
        <p>CDC Hải Phòng — báo cáo hằng tuần</p>
      </div>
    </div>
  </div>

  <div class="content">
    <datalist id="communeList">${options}</datalist>

    <div class="card">
      <p class="lede">Đây là link cố định để nộp mỗi tuần. Hệ thống tự chuyển thẳng tới máy chủ chính; nếu máy chủ chính tạm thời không phản hồi được, dữ liệu sẽ lưu tạm và CDC đồng bộ bù sau.</p>
      <div id="missingWeeksNotice" class="missing-notice" style="display:none"></div>
      <form id="f">
        <label>Xã / phường / đặc khu <span class="req">*</span></label>
        <input name="commune" list="communeList" autocomplete="off" placeholder="Gõ để tìm..." required>

        <label>Tuần báo cáo <span class="req">*</span></label>
        <input name="week" type="week" id="weekInput" required>
        <div class="hint" id="weekRangeInfo"></div>

        <label>Người nộp</label>
        <input name="submitted_by" placeholder="Họ tên (không bắt buộc)">

        <label>Khóa máy chủ phụ (do CDC cung cấp) <span class="req">*</span></label>
        <input name="key" type="password" required>

        <label>File Excel theo mẫu (.xlsx) <span class="req">*</span></label>
        <div class="hint"><a href="${TEMPLATE_URL}" target="_blank" rel="noopener">⬇ Tải file mẫu Excel (48 trường)</a></div>

        <div class="dropzone" id="dropzone" tabindex="0" role="button" aria-label="Chọn file Excel">
          <div class="dropzone-icon">📄</div>
          <div class="dropzone-text">Kéo thả file vào đây, hoặc <b>chọn file</b></div>
          <div class="dropzone-hint">Chỉ nhận .xlsx / .xlsm theo mẫu</div>
        </div>
        <input name="file" id="fileInput" type="file" accept=".xlsx,.xlsm" required hidden>
        <div class="file-chip" id="fileChip" style="display:none">
          <span>📄</span>
          <div class="file-info"><div class="fname" id="fileName"></div><div class="fsize" id="fileSize"></div></div>
          <button type="button" id="removeFile" title="Bỏ chọn file">✕</button>
        </div>

        <button type="submit" id="submitBtn">Nộp báo cáo</button>
        <button type="button" class="link-btn" id="clearCacheLink">Xoá thông tin đã lưu (đổi đơn vị/người nộp)</button>
      </form>
      <div id="msg"></div>
    </div>

    <div class="footer-note">CDC Hải Phòng · Ứng dụng Giám sát dịch bệnh</div>
  </div>
</div>

<script>
var COMMUNES = ${communesJson};
var COMMUNE_SET = {};
COMMUNES.forEach(function (c) { COMMUNE_SET[c] = true; });
var CACHE_KEY = "gsbtn_submit_cache_v1";

function loadCache() {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) || "{}"); } catch (e) { return {}; }
}
function saveCache(patch) {
  var cur = loadCache();
  for (var k in patch) cur[k] = patch[k];
  try { localStorage.setItem(CACHE_KEY, JSON.stringify(cur)); } catch (e) {}
}
function clearCache() {
  try { localStorage.removeItem(CACHE_KEY); } catch (e) {}
}

// Thuật toán tuần ISO-8601 chuẩn (thứ Năm của tuần quyết định số tuần/năm).
function isoWeekString(date) {
  var d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  var dayNum = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - dayNum + 3);
  var firstThursday = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  var firstDayNum = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstDayNum + 3);
  var weekNum = 1 + Math.round((d - firstThursday) / (7 * 24 * 3600 * 1000));
  return d.getUTCFullYear() + "-W" + (weekNum < 10 ? "0" : "") + weekNum;
}
function isoWeekRange(weekStr) {
  var m = /^(\\d{4})-W(\\d{2})$/.exec(weekStr);
  if (!m) return null;
  var year = parseInt(m[1], 10), week = parseInt(m[2], 10);
  var simple = new Date(Date.UTC(year, 0, 1 + (week - 1) * 7));
  var dow = simple.getUTCDay();
  var monday = new Date(simple);
  if (dow <= 4) monday.setUTCDate(simple.getUTCDate() - dow + 1);
  else monday.setUTCDate(simple.getUTCDate() + 8 - dow);
  var sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  return { start: monday, end: sunday };
}
function formatVNDate(d) {
  var dd = String(d.getUTCDate()).padStart(2, "0");
  var mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  return dd + "/" + mm + "/" + d.getUTCFullYear();
}
function updateWeekRangeInfo() {
  var input = document.getElementById("weekInput");
  var info = document.getElementById("weekRangeInfo");
  var range = isoWeekRange(input.value);
  if (!range) { info.textContent = ""; return; }
  info.textContent = "Từ " + formatVNDate(range.start) + " đến " + formatVNDate(range.end);
}

(function initWeekInput() {
  var input = document.getElementById("weekInput");
  var currentWeek = isoWeekString(new Date());
  input.max = currentWeek;
  if (!input.value) input.value = currentWeek;
  updateWeekRangeInfo();
  input.addEventListener("change", function () {
    if (input.value > currentWeek) {
      input.value = currentWeek;
      alert("Không được chọn tuần báo cáo trong tương lai — đã đặt lại về tuần hiện tại.");
    }
    updateWeekRangeInfo();
  });
})();

// Nạp cache vào form nộp báo cáo (item 4): đơn vị, khoá, người nộp không cần nhập lại.
(function initSubmitCache() {
  var cache = loadCache();
  var form = document.getElementById("f");
  if (cache.commune) form.commune.value = cache.commune;
  if (cache.key) form.key.value = cache.key;
  if (cache.submitted_by) form.submitted_by.value = cache.submitted_by;
  ["commune", "key", "submitted_by"].forEach(function (field) {
    form[field].addEventListener("change", function () {
      var patch = {}; patch[field] = form[field].value;
      saveCache(patch);
      if (field === "commune" || field === "key") refreshMissingWeeksNotice();
    });
  });
  document.getElementById("clearCacheLink").addEventListener("click", function () {
    clearCache();
    form.commune.value = ""; form.key.value = ""; form.submitted_by.value = "";
    refreshMissingWeeksNotice();
  });
  refreshMissingWeeksNotice();
})();

// --- Dropzone / chọn file ---
function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}
function isExcelFile(name) {
  var n = name.toLowerCase();
  return n.endsWith(".xlsx") || n.endsWith(".xlsm");
}
function showFileChip(file) {
  document.getElementById("dropzone").style.display = "none";
  var chip = document.getElementById("fileChip");
  chip.style.display = "flex";
  document.getElementById("fileName").textContent = file.name;
  document.getElementById("fileSize").textContent = formatFileSize(file.size);
}
function clearFileChip() {
  document.getElementById("fileInput").value = "";
  document.getElementById("fileChip").style.display = "none";
  document.getElementById("dropzone").style.display = "block";
}
(function initDropzone() {
  var dropzone = document.getElementById("dropzone");
  var fileInput = document.getElementById("fileInput");
  var msg = document.getElementById("msg");
  dropzone.addEventListener("click", function () { fileInput.click(); });
  dropzone.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); fileInput.click(); }
  });
  fileInput.addEventListener("change", function () {
    if (fileInput.files[0]) showFileChip(fileInput.files[0]);
  });
  document.getElementById("removeFile").addEventListener("click", function (ev) {
    ev.stopPropagation();
    clearFileChip();
  });
  ["dragenter", "dragover"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      dropzone.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      dropzone.classList.remove("drag");
    });
  });
  dropzone.addEventListener("drop", function (ev) {
    var files = ev.dataTransfer.files;
    if (!files || !files[0]) return;
    if (!isExcelFile(files[0].name)) {
      msg.className = "err"; msg.textContent = "Chỉ nhận file .xlsx hoặc .xlsm — vui lòng chọn đúng file mẫu.";
      return;
    }
    msg.className = ""; msg.style.display = "none";
    fileInput.files = files;
    showFileChip(files[0]);
  });
})();

document.getElementById("f").addEventListener("submit", function (ev) {
  ev.preventDefault();
  var form = ev.target, msg = document.getElementById("msg"), file = form.file.files[0];
  if (!file) {
    msg.className = "err"; msg.textContent = "Vui lòng chọn file Excel trước khi nộp.";
    return;
  }
  if (!COMMUNE_SET[form.commune.value]) {
    msg.className = "err"; msg.textContent = "Vui lòng chọn đúng tên đơn vị từ danh sách gợi ý (gõ để tìm).";
    return;
  }
  var currentWeek = isoWeekString(new Date());
  if (form.week.value > currentWeek) {
    msg.className = "err"; msg.textContent = "Không được chọn tuần báo cáo trong tương lai.";
    return;
  }
  var submitBtn = document.getElementById("submitBtn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="spinner"></span>Đang gửi...';
  msg.className = ""; msg.style.display = "none";
  var reader = new FileReader();
  reader.onload = function () {
    var base64 = reader.result.split(",")[1];
    fetch(window.location.href, {
      method: "POST",
      body: JSON.stringify({ action: "submit", commune: form.commune.value, week: form.week.value,
        submitted_by: form.submitted_by.value, key: form.key.value, file_name: file.name, content_base64: base64 }),
    }).then(function (r) { return r.json(); }).then(function (data) {
      submitBtn.disabled = false; submitBtn.textContent = "Nộp báo cáo";
      if (data.ok) {
        saveCache({ commune: form.commune.value, key: form.key.value, submitted_by: form.submitted_by.value });
        refreshMissingWeeksNotice();
      }
      if (data.ok && data.result.forwarded) { msg.className = "ok"; msg.textContent = "✓ Đã nộp trực tiếp vào máy chủ chính, mã hàng đợi #" + data.result.queue_id + "."; clearFileChip(); }
      else if (data.ok) { msg.className = "ok"; msg.textContent = "✓ Máy chủ chính tạm thời không phản hồi — đã lưu tạm, dòng #" + data.result.row + ". CDC sẽ đồng bộ bù sau."; clearFileChip(); }
      else { msg.className = "err"; msg.textContent = "Lỗi: " + data.error; }
    }).catch(function (e) {
      submitBtn.disabled = false; submitBtn.textContent = "Nộp báo cáo";
      msg.className = "err"; msg.textContent = "Lỗi kết nối: " + e;
    });
  };
  reader.readAsDataURL(file);
});

// Liệt kê mọi tuần ISO từ startWeek đến endWeek (bao gồm cả 2 đầu). Trả về [] nếu startWeek
// sai định dạng hoặc đã ở sau endWeek (cấu hình TRACKING_START_WEEK sai — không đoán bừa).
function weeksBetween(startWeek, endWeek) {
  var startRange = isoWeekRange(startWeek);
  if (!startRange || startWeek > endWeek) return [];
  var weeks = [];
  var cursor = new Date(startRange.start);
  var guard = 0;
  while (guard < 600) { // chặn vòng lặp chạy tràn nếu mốc cấu hình quá xa (~11 năm)
    var w = isoWeekString(cursor);
    weeks.push(w);
    if (w === endWeek) break;
    cursor.setUTCDate(cursor.getUTCDate() + 7);
    guard++;
  }
  return weeks;
}

// Tuần chưa báo cáo = mọi tuần từ TRACKING_START_WEEK (Script Property, CDC tự cấu hình) tới
// tuần hiện tại mà đơn vị chưa có lượt nộp nào (bất kể trạng thái đã đồng bộ hay chưa). Hiện
// dưới dạng 1 dòng chữ đỏ ngay trên form nộp — không phải trang/tab riêng — im lặng ẩn đi nếu
// CDC chưa cấu hình TRACKING_START_WEEK hoặc chưa xác định được đơn vị (không có gì để xã xử lý).
function renderMissingWeeks(trackingStartWeek, submittedWeeksSet) {
  var notice = document.getElementById("missingWeeksNotice");
  if (!trackingStartWeek) { notice.style.display = "none"; return; }
  var currentWeek = isoWeekString(new Date());
  var allWeeks = weeksBetween(trackingStartWeek, currentWeek);
  if (!allWeeks.length) { notice.style.display = "none"; return; }
  var missing = allWeeks.filter(function (w) { return !submittedWeeksSet[w]; });
  if (!missing.length) { notice.style.display = "none"; return; }
  notice.textContent = "⚠ Chưa nộp báo cáo các tuần: " + missing.join(", ") + ".";
  notice.style.display = "block";
}

// Tự động chạy khi tải trang (nếu đã có đơn vị/khóa trong cache) và mỗi khi đổi đơn vị/khóa
// trên chính form nộp — không cần màn hình/tab riêng để xem tình hình nộp.
function refreshMissingWeeksNotice() {
  var form = document.getElementById("f");
  var commune = form.commune.value, key = form.key.value;
  var notice = document.getElementById("missingWeeksNotice");
  if (!COMMUNE_SET[commune] || !key) { notice.style.display = "none"; return; }
  fetch(window.location.href, {
    method: "POST",
    body: JSON.stringify({ action: "list_status", commune: commune, key: key }),
  }).then(function (r) { return r.json(); }).then(function (data) {
    if (!data.ok) { notice.style.display = "none"; return; }
    var submittedWeeksSet = {};
    data.result.rows.forEach(function (row) { submittedWeeksSet[row.week] = true; });
    renderMissingWeeks(data.result.tracking_start_week, submittedWeeksSet);
  }).catch(function () { notice.style.display = "none"; });
}
</script>
</body>
</html>`;
}
