(function () {
  var menu = document.getElementById("profile-menu");
  if (!menu) return;
  var toggle = document.getElementById("profile-menu-toggle");
  var panel = document.getElementById("profile-menu-panel");
  function close(restoreFocus) {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open Profile Menu");
    if (restoreFocus) toggle.focus();
  }
  toggle.addEventListener("click", function () {
    var opening = panel.hidden;
    panel.hidden = !opening;
    toggle.setAttribute("aria-expanded", String(opening));
    toggle.setAttribute("aria-label", opening ? "Close Profile Menu" : "Open Profile Menu");
  });
  menu.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !panel.hidden) {
      event.preventDefault(); close(true);
    }
    if (event.target === toggle && event.key === "ArrowDown") {
      event.preventDefault(); panel.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
      toggle.setAttribute("aria-label", "Close Profile Menu");
      panel.querySelector("a[href], button").focus();
    }
  });
  document.addEventListener("click", function (event) {
    if (!menu.contains(event.target)) close(false);
  });
  menu.addEventListener("focusout", function (event) {
    if (!menu.contains(event.relatedTarget)) close(false);
  });
  var photo = document.getElementById("profile-menu-photo");
  if (photo) {
    function fallback() { photo.hidden = true; }
    photo.addEventListener("error", fallback);
    if (photo.complete && !photo.naturalWidth) fallback();
  }
})();
