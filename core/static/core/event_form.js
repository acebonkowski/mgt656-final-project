// Create and edit event form (#69): live character counters, and a
// description box that grows with its text instead of scrolling.
// Markup: templates/core/_event_form_fields.html.
(function () {
  "use strict";

  document.querySelectorAll(".char-count[data-count-for]").forEach(function (counter) {
    var input = document.getElementById(counter.dataset.countFor);
    if (!input) return;
    var max = counter.dataset.max;
    function update() {
      counter.textContent = input.value.length + "/" + max;
    }
    input.addEventListener("input", update);
    update();
  });

  var description = document.getElementById("id_description");
  if (description) {
    var grow = function () {
      description.style.height = "auto";
      // +2 for the top and bottom border, so no inner scrollbar appears.
      description.style.height = description.scrollHeight + 2 + "px";
    };
    description.addEventListener("input", grow);
    // The create form sits in a closed dialog, where scrollHeight is 0 until
    // it opens; grow again whenever it becomes visible.
    var dialog = description.closest("dialog");
    if (dialog && typeof MutationObserver !== "undefined") {
      new MutationObserver(grow).observe(dialog, { attributes: true, attributeFilter: ["open"] });
    }
    grow();
  }
})();
