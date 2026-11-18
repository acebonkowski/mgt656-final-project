// Event search panel (#35).
// Reads the filter controls, calls GET /events/search/, redraws the event
// markers through window.eventMap (map_provider.js) and shows active filters as
// chips. The query string mirrors the filters, so refresh and shared links
// show the same search.
(function () {
  "use strict";

  var panel = document.getElementById("search-panel");
  if (!panel) return;

  var searchUrl = panel.dataset.searchUrl;
  var geocodeUrl = panel.dataset.geocodeUrl;

  function byId(id) { return document.getElementById(id); }

  var form = byId("search-form");
  var qInput = byId("search-q");
  var filtersToggle = byId("search-filters-toggle");
  var filters = byId("search-filters");
  var categoryDetails = byId("search-category");
  var categoryBoxes = Array.prototype.slice.call(
    panel.querySelectorAll('input[name="category"]'));
  var whenRadios = Array.prototype.slice.call(panel.querySelectorAll('input[name="when"]'));
  var datesBox = byId("search-dates");
  var rangeBox = byId("search-date-range");
  var dateFrom = byId("search-date-from");
  var dateFromLabel = byId("search-date-from-label");
  var dateTo = byId("search-date-to");
  var dateToWrap = byId("search-date-to-wrap");
  var timeFrom = byId("search-time-from");
  var timeTo = byId("search-time-to");
  var address = byId("search-address");
  var suggestions = byId("search-address-suggestions");
  var myLocation = byId("search-my-location");
  var radius = byId("search-radius");
  var locationMessage = byId("search-location-message");
  var clearButton = byId("search-clear");
  var results = byId("search-results");
  var summary = byId("search-summary");
  var summaryText = byId("search-summary-text");
  var collapseButton = byId("search-collapse");
  var phone = window.matchMedia("(max-width: 767px)");
  var chips = byId("search-chips");
  var errorBox = byId("search-error");
  var statusBox = byId("search-status");
  var areaButton = byId("search-this-area");

  var defaultRadius = radius.value;
  var near = { lat: "", lng: "", label: "" };
  var area = "";          // applied "Search this area" circle: "lat,lng,radius"
  var previewArea = null;  // circle shown after a drag, not searched yet
  var requestId = 0;

  // --- Reading and writing the controls --------------------------------------

  function checkedWhen() {
    var checked = whenRadios.filter(function (radio) { return radio.checked; })[0];
    return checked ? checked.value : "";
  }

  function readFilters() {
    var when = checkedWhen();
    var pickDates = when === "dates";
    return {
      q: qInput.value.trim(),
      category: categoryBoxes.filter(function (box) { return box.checked; })
        .map(function (box) { return box.value; }),
      when: pickDates ? "" : when,
      date_from: pickDates ? dateFrom.value : "",
      date_to: pickDates && rangeBox.checked ? dateTo.value : "",
      time_from: timeFrom.value,
      time_to: timeTo.value,
      near_lat: near.lat,
      near_lng: near.lng,
      near_label: near.lat ? near.label : "",
      radius_mi: near.lat ? radius.value : "",
      area: area,
    };
  }

  function setWhen(value) {
    whenRadios.forEach(function (radio) { radio.checked = radio.value === value; });
    datesBox.hidden = value !== "dates";
  }

  function setRange(isRange) {
    rangeBox.checked = isRange;
    dateToWrap.hidden = !isRange;
    dateFromLabel.textContent = isRange ? "From" : "On";
    if (!isRange) dateTo.value = "";
  }

  function writeFilters(f) {
    qInput.value = f.q || "";
    categoryBoxes.forEach(function (box) {
      box.checked = (f.category || []).indexOf(box.value) !== -1;
    });
    if (f.date_from || f.date_to) {
      setWhen("dates");
      dateFrom.value = f.date_from || f.date_to;
      setRange(Boolean(f.date_to && f.date_to !== f.date_from));
      dateTo.value = rangeBox.checked ? f.date_to : "";
    } else {
      setWhen(f.when || "");
      dateFrom.value = "";
      setRange(false);
    }
    timeFrom.value = f.time_from || "";
    timeTo.value = f.time_to || "";
    near = { lat: f.near_lat || "", lng: f.near_lng || "", label: f.near_label || "" };
    address.value = near.lat ? (near.label || "Selected location") : "";
    radius.value = f.radius_mi || defaultRadius;
    area = f.area || "";
  }

  function toParams(f) {
    var params = new URLSearchParams();
    Object.keys(f).forEach(function (key) {
      var value = f[key];
      if (Array.isArray(value)) {
        value.forEach(function (item) { params.append(key, item); });
      } else if (value) {
        params.set(key, value);
      }
    });
    return params;
  }

  function fromParams(params) {
    return {
      q: params.get("q") || "",
      category: params.getAll("category"),
      when: params.get("when") || "",
      date_from: params.get("date_from") || "",
      date_to: params.get("date_to") || "",
      time_from: params.get("time_from") || "",
      time_to: params.get("time_to") || "",
      near_lat: params.get("near_lat") || "",
      near_lng: params.get("near_lng") || "",
      near_label: params.get("near_label") || "",
      radius_mi: params.get("radius_mi") || "",
      area: params.get("area") || "",
    };
  }

  // --- Chips -------------------------------------------------------------------

  function shortDate(value) {
    var parts = value.split("-");
    var date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  function labelFor(input) {
    return input ? input.dataset.label : "";
  }

  function chipList(f) {
    var list = [];
    if (f.q) {
      list.push({ label: "“" + f.q + "”", focus: qInput,
        remove: function () { qInput.value = ""; } });
    }
    f.category.forEach(function (value) {
      var box = categoryBoxes.filter(function (b) { return b.value === value; })[0];
      list.push({ label: labelFor(box), focus: categoryDetails, remove: function () {
        if (box) box.checked = false;
      } });
    });
    if (f.when) {
      var radio = whenRadios.filter(function (r) { return r.value === f.when; })[0];
      list.push({ label: labelFor(radio), focus: radio, remove: function () { setWhen(""); } });
    } else if (f.date_from) {
      var label = shortDate(f.date_from) + (f.date_to && f.date_to !== f.date_from
        ? " – " + shortDate(f.date_to) : "");
      list.push({ label: label, focus: dateFrom, remove: function () {
        setWhen(""); dateFrom.value = ""; setRange(false);
      } });
    }
    if (f.time_from || f.time_to) {
      var timeLabel = f.time_from && f.time_to ? "Starts " + f.time_from + "–" + f.time_to
        : (f.time_from ? "Starts after " + f.time_from : "Starts before " + f.time_to);
      list.push({ label: timeLabel, focus: timeFrom, remove: function () {
        timeFrom.value = ""; timeTo.value = "";
      } });
    }
    if (f.near_lat) {
      list.push({ label: "Within " + f.radius_mi + " mi of " + (f.near_label || "location"),
        focus: address, remove: function () {
          near = { lat: "", lng: "", label: "" }; address.value = "";
        } });
    }
    if (f.area) {
      list.push({ label: "Map area (" + f.area.split(",")[2] + " mi)", focus: null,
        remove: function () { area = ""; } });
    }
    return list;
  }

  function renderChips(f) {
    chips.replaceChildren();
    chipList(f).forEach(function (chip) {
      var item = document.createElement("li");
      item.className = "search-chip";
      var edit = document.createElement("button");
      edit.type = "button";
      edit.className = "search-chip-label";
      edit.textContent = chip.label;
      edit.addEventListener("click", function () {
        if (!chip.focus) return;
        openFilters(true);
        if (chip.focus === categoryDetails) categoryDetails.open = true;
        chip.focus.focus();
      });
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "search-chip-remove";
      remove.setAttribute("aria-label", "Remove filter: " + chip.label);
      remove.textContent = "×";
      remove.addEventListener("click", function () {
        chip.remove();
        runSearch();
      });
      item.appendChild(edit);
      item.appendChild(remove);
      chips.appendChild(item);
    });
  }

  // --- Searching ---------------------------------------------------------------

  function showError(message) {
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
  }

  function hasFilters(f) {
    return chipList(f).length > 0;
  }

  function updateUrl(params) {
    var query = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (query ? "?" + query : ""));
  }

  var NEW_YORK_TIME = {
    timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  };

  // A simple list of results; #34 turns these into cards with the event popup.
  function renderResults(events) {
    results.replaceChildren();
    events.forEach(function (event) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.className = "search-result";
      link.href = event.detail_url;
      link.addEventListener("click", function (clickEvent) {
        // Show the event on the map; a modified click still opens the page.
        if (!window.eventMap || clickEvent.metaKey || clickEvent.ctrlKey ||
            clickEvent.shiftKey || clickEvent.button !== 0) return;
        clickEvent.preventDefault();
        setCollapsed(true);
        window.eventMap.focusEvent(event.id);
      });
      var name = document.createElement("strong");
      name.textContent = event.name;
      var when = document.createElement("span");
      when.textContent = new Date(event.start_at).toLocaleString("en-US", NEW_YORK_TIME);
      var details = document.createElement("span");
      details.textContent = event.price + " \u00b7 " + event.category_label;
      link.appendChild(name);
      link.appendChild(when);
      link.appendChild(details);
      item.appendChild(link);
      results.appendChild(item);
    });
  }

  // The map shows the preview circle after a drag, otherwise the searched one.
  function showArea() {
    if (!window.eventMap) return;
    if (previewArea) {
      window.eventMap.setArea({ lat: previewArea.lat, lng: previewArea.lng,
        radius: previewArea.radius, preview: true });
    } else if (area) {
      var parts = area.split(",").map(Number);
      window.eventMap.setArea({ lat: parts[0], lng: parts[1], radius: parts[2], preview: false });
    } else {
      window.eventMap.setArea(null);
    }
  }

  // Collapsed, the panel is one line summarising the search, so the map shows.
  function setCollapsed(collapsed) {
    if (collapsed === !form.hidden) {
      form.hidden = collapsed;
      summary.hidden = !collapsed;
      collapseButton.setAttribute("aria-expanded", String(!collapsed));
      summary.setAttribute("aria-expanded", String(!collapsed));
    }
  }

  function updateSummary() {
    var parts = chipList(readFilters()).map(function (chip) { return chip.label; });
    if (statusBox.textContent) parts.push(statusBox.textContent);
    summaryText.textContent = parts.length ? parts.join(" \u00b7 ") : "Search events";
  }

  function runSearch() {
    showError("");
    if (address.value.trim() && !near.lat) {
      showError("Choose an address from the suggestions, or use your location.");
      return;
    }
    var f = readFilters();
    var params = toParams(f);
    renderChips(f);
    updateUrl(params);
    showArea();
    clearButton.hidden = !hasFilters(f);
    var thisRequest = ++requestId;
    statusBox.textContent = "Searching…";

    fetch(searchUrl + "?" + params.toString(), {
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
    }).then(function (response) {
      return response.json().then(function (payload) {
        return { ok: response.ok, payload: payload };
      });
    }).then(function (result) {
      if (thisRequest !== requestId) return;  // a newer search has started
      if (!result.ok) {
        var errors = result.payload.errors || {};
        var messages = Object.keys(errors).map(function (key) { return errors[key].join(" "); });
        statusBox.textContent = "";
        renderResults([]);
        updateSummary();
        showError(messages.join(" ") || "Those filters aren't valid.");
        return;
      }
      var events = result.payload.events || [];
      if (window.eventMap) window.eventMap.setEvents(events);
      renderResults(events);
      if (events.length === 0) {
        statusBox.textContent = "No events found";
      } else {
        statusBox.textContent = events.length === 1 ? "1 event" : events.length + " events";
      }
      updateSummary();
    }).catch(function () {
      if (thisRequest !== requestId) return;
      statusBox.textContent = "";
      showError("Search failed. Check your connection and try again.");
    });
  }

  function clearAll() {
    writeFilters(fromParams(new URLSearchParams()));
    previewArea = null;
    areaButton.hidden = true;
    locationMessage.hidden = true;
    runSearch();
  }

  // --- Controls ----------------------------------------------------------------

  function openFilters(open) {
    filters.hidden = !open;
    filtersToggle.setAttribute("aria-expanded", String(open));
  }

  filtersToggle.addEventListener("click", function () {
    openFilters(filters.hidden);
  });

  // Filters apply as soon as they change, so the chips and results always
  // match the controls. Text searches on Enter or the Search button.
  var applyTimer = null;
  function applySoon() {
    window.clearTimeout(applyTimer);
    applyTimer = window.setTimeout(runSearch, 250);
  }

  whenRadios.forEach(function (radio) {
    radio.addEventListener("change", function () { setWhen(checkedWhen()); applySoon(); });
  });
  rangeBox.addEventListener("change", function () { setRange(rangeBox.checked); applySoon(); });
  categoryBoxes.concat([dateFrom, dateTo, timeFrom, timeTo]).forEach(function (input) {
    input.addEventListener("change", applySoon);
  });
  radius.addEventListener("change", function () { if (near.lat) applySoon(); });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    window.clearTimeout(applyTimer);
    runSearch();
  });
  clearButton.addEventListener("click", clearAll);
  collapseButton.addEventListener("click", function () {
    setCollapsed(true);
    summary.focus();
  });
  summary.addEventListener("click", function () {
    setCollapsed(false);
    qInput.focus();
  });

  function showLocationMessage(message) {
    locationMessage.textContent = message;
    locationMessage.hidden = !message;
  }

  var addressTimer = null;
  address.addEventListener("input", function () {
    near = { lat: "", lng: "", label: "" };
    showLocationMessage("");
    window.clearTimeout(addressTimer);
    var query = address.value.trim();
    if (query.length < 3) {
      suggestions.hidden = true;
      suggestions.replaceChildren();
      return;
    }
    addressTimer = window.setTimeout(function () {
      fetch(geocodeUrl + "?q=" + encodeURIComponent(query), {
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
      }).then(function (response) {
        if (!response.ok) throw new Error("unavailable");
        return response.json();
      }).then(function (payload) {
        suggestions.replaceChildren();
        (payload.suggestions || []).forEach(function (item) {
          var option = document.createElement("button");
          option.type = "button";
          option.className = "address-suggestion";
          option.setAttribute("role", "option");
          option.textContent = item.address;
          option.addEventListener("click", function () {
            near = { lat: String(item.latitude), lng: String(item.longitude), label: item.address };
            address.value = item.address;
            suggestions.hidden = true;
            suggestions.replaceChildren();
            applySoon();
          });
          suggestions.appendChild(option);
        });
        suggestions.hidden = suggestions.children.length === 0;
      }).catch(function () {
        suggestions.hidden = true;
        showLocationMessage("Address search is unavailable right now. Other filters still work.");
      });
    }, 300);
  });

  myLocation.addEventListener("click", function () {
    if (!navigator.geolocation) {
      showLocationMessage("Your browser can't share your location. Type an address instead.");
      return;
    }
    showLocationMessage("Finding your location…");
    navigator.geolocation.getCurrentPosition(function (position) {
      near = {
        lat: position.coords.latitude.toFixed(6),
        lng: position.coords.longitude.toFixed(6),
        label: "My location",
      };
      address.value = "My location";
      suggestions.hidden = true;
      showLocationMessage("");
      applySoon();
    }, function () {
      showLocationMessage("Location access was denied. Type an address instead; other filters still work.");
    }, { timeout: 10000, maximumAge: 60000 });
  });

  // After a drag or zoom, preview the circle that "Search this area" would use.
  if (window.eventMap) {
    // Phones: dragging the map tucks the panel away so the map is visible.
    window.eventMap.onUserMoveStart(function () {
      if (phone.matches) setCollapsed(true);
    });
    window.eventMap.onUserMove(function () {
      previewArea = window.eventMap.viewCircle();
      areaButton.textContent = "Search this area (" + previewArea.radius + " mi)";
      areaButton.hidden = false;
      showArea();
    });
  }
  areaButton.addEventListener("click", function () {
    if (!previewArea) return;
    area = [previewArea.lat.toFixed(6), previewArea.lng.toFixed(6), previewArea.radius].join(",");
    previewArea = null;
    areaButton.hidden = true;
    runSearch();
  });

  // A link with filters in it (refresh, back, shared URL) runs that search.
  var initial = new URLSearchParams(window.location.search);
  if (initial.toString()) {
    writeFilters(fromParams(initial));
    runSearch();
  }
})();
