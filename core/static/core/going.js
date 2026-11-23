// Going status (#84): saves the dropdown on the event page and in the map's
// event window. One delegated handler, because the window's HTML is inserted
// after page load. The server decides who may answer; this only posts.
(function () {
  document.addEventListener("change", function (event) {
    var select = event.target;
    if (!select.classList || !select.classList.contains("going-select")) return;
    var box = select.closest(".event-going");
    if (!box) return;
    var status = box.querySelector(".going-status");
    var previous = select.dataset.saved || "";
    var body = new URLSearchParams();
    body.set("status", select.value);
    select.disabled = true;
    status.textContent = "Saving…";

    fetch(box.dataset.goingUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": box.dataset.csrf,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    }).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok) throw new Error(payload.error || "failed");
        return payload;
      });
    }).then(function (payload) {
      select.dataset.saved = payload.status;
      status.textContent = payload.status ? "Saved" : "Answer cleared";
    }).catch(function (error) {
      select.value = previous;  // show what is really saved
      status.textContent = error.message && error.message !== "failed" && error.message !== "Failed to fetch"
        ? error.message : "Couldn't save. Try again.";
    }).then(function () {
      select.disabled = false;
    });
  });
})();
