// Relay for feedback_kit. Deploy it under the Google account that should RECEIVE the reports
// (support.somore100@gmail.com) so no password ever ships inside an app:
//   1. script.google.com -> New project -> paste this file.
//   2. Deploy -> New deployment -> type "Web app"; Execute as: Me; Who has access: Anyone.
//   3. Copy the web-app URL into feedback.json  ->  {"endpoint": "https://script.google.com/macros/s/.../exec"}
// MailApp is limited by Google (about 100 mails/day for a free account), which also caps abuse.
var TO = "support.somore100@gmail.com";           // always delivered here, whatever the request says

// Opening the URL in a browser is a GET: just confirm the relay is alive (the apps use POST).
function doGet() { return out({ok: true, service: "feedback relay"}); }

function doPost(e) {
  try {
    var d = JSON.parse(e.postData.contents);
    var subject = String(d.subject || "").replace(/[\r\n]+/g, " ").slice(0, 200);
    var body = String(d.body || "").slice(0, 8000);
    if (!subject || !body) return out({ok: false, error: "empty"});
    MailApp.sendEmail({to: TO, subject: subject, body: body, name: "Feedback relay"});
    return out({ok: true});
  } catch (err) {
    return out({ok: false, error: String(err)});
  }
}

function out(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
