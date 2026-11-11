// Code sent screen (#6): the confirm button is enabled only when a code is
// typed, and the resend option appears when the countdown reaches zero.
// The server enforces both rules too; this script only drives the screen.
(function () {
  "use strict";

  var input = document.getElementById("code");
  var confirm = document.getElementById("confirm");
  if (input && confirm) {
    var update = function () {
      confirm.disabled = input.value.trim() === "";
    };
    input.addEventListener("input", update);
    update();
  }

  var countdown = document.getElementById("resend-countdown");
  var seconds = document.getElementById("resend-seconds");
  var resend = document.getElementById("resend-form");
  if (!countdown || !seconds || !resend) {
    return;
  }
  var remaining = parseInt(countdown.getAttribute("data-seconds"), 10) || 0;
  var deadline = Date.now() + remaining * 1000;

  function tick() {
    var left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    seconds.textContent = String(left);
    if (left === 0) {
      countdown.hidden = true;
      resend.hidden = false;
      return;
    }
    window.setTimeout(tick, 250);
  }
  if (remaining > 0) {
    tick();
  }
})();
