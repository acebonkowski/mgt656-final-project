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

  // Overnight and multi-day events (#70). An end time earlier than the start
  // time shows End date, set to the next day; the user can change it. An end
  // time later than the start hides it again, and the event ends on the start
  // date. The server checks end > start in New York time (core/forms.py).
  var dateInput = document.getElementById("id_date");
  var startGroup = document.getElementById("id_start_time");
  var endGroup = document.getElementById("id_end_time");
  var endDate = document.getElementById("id_end_date");
  var endDateRow = document.getElementById("end-date-row");
  if (dateInput && startGroup && endGroup && endDate && endDateRow && window.Time12) {
    // True while End date holds the value we filled in, so a new start date
    // moves it along; false once the user picks one (or the server sent one).
    var autoEndDate = !endDate.value;

    var nextDay = function (iso) {
      var p = iso.split("-").map(Number);
      return new Date(Date.UTC(p[0], p[1] - 1, p[2] + 1)).toISOString().slice(0, 10);
    };

    var endsBeforeStart = function () {
      var start = window.Time12.read(startGroup);
      var end = window.Time12.read(endGroup);
      return Boolean(start && end && end < start);  // "HH:MM" sorts as text
    };

    var syncEndDate = function (onLoad) {
      // On load, also keep a saved multi-day end date (edit page).
      var show = endsBeforeStart() || (onLoad === true && Boolean(endDate.value) &&
                                       endDate.value !== dateInput.value);
      endDateRow.hidden = !show;
      if (!show) {
        endDate.value = "";
        autoEndDate = true;
      } else if (autoEndDate && dateInput.value) {
        endDate.value = nextDay(dateInput.value);
      }
    };

    [startGroup, endGroup, dateInput].forEach(function (element) {
      element.addEventListener("change", syncEndDate);
      element.addEventListener("input", syncEndDate);
    });
    endDate.addEventListener("input", function () { autoEndDate = false; });
    if (!endDateRow.querySelector(".errorlist")) syncEndDate(true);
  }
})();
