/**
 * Máy chủ phụ (Google Apps Script) cho hệ thống Giám sát dịch bệnh.
 *
 * Dùng khi máy chủ chính (lan_server.py) offline: Trạm Y tế xã mở URL Web App này để nộp
 * file Excel tạm thời; script lưu file vào Google Drive và ghi một dòng "chờ đồng bộ" vào
 * Google Sheet gắn với script. Khi máy chủ chính online lại, module Python
 * `secondary_sync.py` gọi `GET ?action=list_pending` để lấy các dòng đang chờ, tải nội dung
 * base64 rồi đẩy vào hàng đợi nhập liệu cục bộ (`import_queue`, source="server_phu"), sau đó
 * gọi `POST {action:"mark_synced"}` để đánh dấu đã đồng bộ — tránh kéo trùng lần sau.
 *
 * Triển khai: xem google_apps_script/README.md.
 */

var SHEET_NAME = "HangDoiPhu";
var HEADER = ["commune", "week", "file_name", "drive_file_id", "submitted_by", "received_at", "status", "synced_at"];
var ROOT_FOLDER_NAME = "MayChuPhu_GSBTN";
var COL_STATUS = 7;
var COL_SYNCED_AT = 8;

function doGet(e) {
  var params = (e && e.parameter) || {};
  if (params.action === "list_pending") {
    try {
      return jsonResponse(true, listPending(params.key));
    } catch (err) {
      return jsonResponse(false, errorMessage(err));
    }
  }
  return HtmlService.createHtmlOutput(UPLOAD_FORM_HTML)
    .setTitle("Nộp danh sách ca bệnh — máy chủ phụ")
    .addMetaTag("viewport", "width=device-width, initial-scale=1");
}

function doPost(e) {
  try {
    var payload = JSON.parse((e.postData && e.postData.contents) || "{}");
    var result;
    if (payload.action === "submit") {
      result = handleSubmit(payload);
    } else if (payload.action === "mark_synced") {
      result = handleMarkSynced(payload);
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

function checkKey(key) {
  var expected = PropertiesService.getScriptProperties().getProperty("SHARED_KEY");
  if (!expected) {
    throw new Error("Chưa cấu hình SHARED_KEY trong Script Properties (Project Settings).");
  }
  if (key !== expected) {
    throw new Error("Sai khóa xác thực máy chủ phụ.");
  }
}

function getSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
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

function handleSubmit(payload) {
  checkKey(payload.key);
  var commune = String(payload.commune || "").trim();
  var week = String(payload.week || "").trim();
  var fileName = String(payload.file_name || "du_lieu.xlsx");
  var contentBase64 = payload.content_base64;
  if (!commune) throw new Error("Thiếu tên xã.");
  if (!week) throw new Error("Thiếu tuần báo cáo.");
  if (!contentBase64) throw new Error("Thiếu nội dung file.");
  var bytes = Utilities.base64Decode(contentBase64);
  var blob = Utilities.newBlob(bytes, MimeType.MICROSOFT_EXCEL, fileName);
  var folder = getUploadFolder(commune, week);
  var file = folder.createFile(blob);
  var sheet = getSheet();
  var now = new Date();
  sheet.appendRow([commune, week, fileName, file.getId(), String(payload.submitted_by || ""), now, "cho_dong_bo", ""]);
  return { row: sheet.getLastRow(), file_id: file.getId() };
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

var UPLOAD_FORM_HTML =
  '<!doctype html><html lang="vi"><head><meta charset="utf-8">' +
  '<style>body{font-family:system-ui,sans-serif;max-width:520px;margin:24px auto;padding:0 16px;color:#1f2937}' +
  'label{display:block;margin-top:12px;font-weight:600}' +
  'input{width:100%;padding:8px;margin-top:4px;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:6px}' +
  'button{margin-top:18px;padding:10px 16px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer}' +
  '#msg{margin-top:16px;padding:10px;border-radius:6px;display:none}' +
  '#msg.ok{background:#dcfce7;color:#166534;display:block}#msg.err{background:#fee2e2;color:#991b1b;display:block}</style></head>' +
  '<body><h1>Nộp danh sách ca bệnh (máy chủ phụ)</h1>' +
  '<p>Chỉ dùng khi không kết nối được máy chủ chính. CDC sẽ đồng bộ dữ liệu này vào hệ thống chính khi máy chủ online lại.</p>' +
  '<form id="f">' +
  '<label>Xã / phường</label><input name="commune" required>' +
  '<label>Tuần báo cáo</label><input name="week" required placeholder="2026-W29">' +
  '<label>Người nộp</label><input name="submitted_by">' +
  '<label>Khóa máy chủ phụ (do CDC cung cấp)</label><input name="key" type="password" required>' +
  '<label>File Excel (.xlsx)</label><input name="file" type="file" accept=".xlsx,.xlsm" required>' +
  '<button type="submit">Nộp tạm vào máy chủ phụ</button></form><div id="msg"></div>' +
  '<script>' +
  'document.getElementById("f").addEventListener("submit", function (ev) {' +
  '  ev.preventDefault();' +
  '  var form = ev.target, msg = document.getElementById("msg"), file = form.file.files[0];' +
  '  if (!file) return;' +
  '  var reader = new FileReader();' +
  '  reader.onload = function () {' +
  '    var base64 = reader.result.split(",")[1];' +
  '    fetch(window.location.href, {' +
  '      method: "POST",' +
  '      body: JSON.stringify({ action: "submit", commune: form.commune.value, week: form.week.value,' +
  '        submitted_by: form.submitted_by.value, key: form.key.value, file_name: file.name, content_base64: base64 }),' +
  '    }).then(function (r) { return r.json(); }).then(function (data) {' +
  '      if (data.ok) { msg.className = "ok"; msg.textContent = "Đã nộp tạm, dòng #" + data.result.row + ". CDC sẽ đồng bộ khi máy chủ chính online."; form.reset(); }' +
  '      else { msg.className = "err"; msg.textContent = "Lỗi: " + data.error; }' +
  '    }).catch(function (e) { msg.className = "err"; msg.textContent = "Lỗi kết nối: " + e; });' +
  '  };' +
  '  reader.readAsDataURL(file);' +
  '});' +
  "</script></body></html>";
