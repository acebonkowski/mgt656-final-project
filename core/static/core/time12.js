// 12-hour time controls (#67): hour, minute and AM/PM, sent to the server as
// 24-hour "HH:MM". Markup: templates/core/widgets/time12.html.
// Loads as a plain script (window.Time12) and as a Node module for the tests.
(function (root) {
  "use strict";

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  // ("8", "00", "PM") -> "20:00". "" when hour and minute are both empty,
  // null when the input isn't a valid 12-hour time. An empty minute means :00.
  function to24(hour, minute, period) {
    hour = String(hour == null ? "" : hour).trim();
    minute = String(minute == null ? "" : minute).trim();
    if (!hour && !minute) return "";
    if (!/^\d{1,2}$/.test(hour) || (minute && !/^\d{1,2}$/.test(minute))) return null;
    if (period !== "AM" && period !== "PM") return null;
    var h = Number(hour);
    var m = minute ? Number(minute) : 0;
    if (h < 1 || h > 12 || m > 59) return null;
    return pad(h % 12 + (period === "PM" ? 12 : 0)) + ":" + pad(m);
  }

  // "20:05" (or "20:05:00") -> {hour: "8", minute: "05", period: "PM"}; null otherwise.
  function from24(value) {
    var match = /^(\d{1,2}):(\d{2})(:\d{2})?$/.exec(String(value == null ? "" : value).trim());
    if (!match) return null;
    var h = Number(match[1]);
    var m = Number(match[2]);
    if (h > 23 || m > 59) return null;
    return { hour: String(h % 12 || 12), minute: pad(m), period: h < 12 ? "AM" : "PM" };
  }

  // "20:05" -> "8:05 PM", for chips and summaries.
  function label(value) {
    var t = from24(value);
    return t ? t.hour + ":" + t.minute + " " + t.period : String(value || "");
  }

  // DOM helpers for one .time12 group.
  function parts(group) {
    return {
      hour: group.querySelector(".time12-hour"),
      minute: group.querySelector(".time12-minute"),
      radios: Array.prototype.slice.call(group.querySelectorAll('input[type="radio"]')),
    };
  }

  function read(group) {
    var p = parts(group);
    var checked = p.radios.filter(function (r) { return r.checked; })[0];
    return to24(p.hour.value, p.minute.value, checked ? checked.value : "");
  }

  function write(group, value) {
    var p = parts(group);
    var t = from24(value);
    p.hour.value = t ? t.hour : "";
    p.minute.value = t ? t.minute : "";
    var period = t ? t.period : "PM";
    p.radios.forEach(function (r) { r.checked = r.value === period; });
  }

  function inputs(group) {
    var p = parts(group);
    return [p.hour, p.minute].concat(p.radios);
  }

  var api = { to24: to24, from24: from24, label: label, read: read, write: write, inputs: inputs };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.Time12 = api;
  }
})(this);
