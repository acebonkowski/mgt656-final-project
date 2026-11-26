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
  var iconBar = panel.querySelector(".search-bar");
  var filters = byId("search-filters");
  var filtersBack = byId("search-filters-back");   // manual search header (#67)
  var filtersAi = byId("search-filters-ai");
  var categorySelect = byId("search-category");
  var whenSelect = byId("search-when");
  var pickDates = byId("search-pick-dates");
  var datesBox = byId("search-dates");
  var rangeBox = byId("search-date-range");
  var dateFrom = byId("search-date-from");
  var dateFromLabel = byId("search-date-from-label");
  var dateTo = byId("search-date-to");
  var dateToWrap = byId("search-date-to-wrap");
  var timeFrom = byId("search-time-from");  // 12-hour groups (time12.js)
  var timeTo = byId("search-time-to");
  var address = byId("search-address");
  var suggestions = byId("search-address-suggestions");
  var myLocation = byId("search-my-location");
  var radius = byId("search-radius");
  var includeNotGoing = byId("search-include-not-going");  // #84
  var locationMessage = byId("search-location-message");
  var clearButton = byId("search-clear");
  var results = byId("search-results");
  var summary = byId("search-summary");
  var summaryText = byId("search-summary-text");
  var collapseButton = byId("search-collapse");
  var aiView = byId("search-ai");
  var aiToggle = byId("search-ai-toggle");
  var aiBack = byId("search-ai-back");
  var mode = "filters";     // or "ai" (#34); kept in the URL as ?mode=ai
  var aiUrl = panel.dataset.aiUrl;
  var aiResetUrl = panel.dataset.aiResetUrl;
  var aiLog = byId("search-ai-log");
  var aiResults = byId("search-ai-results");
  var aiForm = byId("search-ai-form");
  var aiInput = byId("search-ai-input");
  var aiCount = byId("search-ai-count");
  var aiSend = byId("search-ai-send");
  var aiManual = byId("search-ai-manual");  // "Search manually" (#66)
  var aiImage = byId("search-ai-image");
  var aiAttachment = byId("search-ai-attachment");
  var aiAttachmentPreview = byId("search-ai-attachment-preview");
  var aiAttachmentName = byId("search-ai-attachment-name");
  var aiAttachmentError = byId("search-ai-notice");  // attachment and voice notices
  var IMAGE_TYPES = ["image/png", "image/jpeg", "image/heic", "image/heif"];
  var MAX_IMAGE_BYTES = 5 * 1024 * 1024;
  var attachedImage = null;  // the File the user picked, sent with the next message
  var collapsed = false;
  var phone = window.matchMedia("(max-width: 767px)");
  var popupUrl = panel.dataset.popupUrl;  // "/events/0/popup/"
  var defaultImage = panel.dataset.defaultImage;
  var dialog = byId("search-event-dialog");
  var dialogContent = byId("search-event-content");
  var dialogPosition = byId("search-event-position");
  var prevButton = byId("search-event-prev");
  var nextButton = byId("search-event-next");
  var currentEvents = [];  // the events in the panel and on the map, in order
  var openIndex = -1;
  var openedFrom = null;
  var chips = byId("search-chips");
  var errorBox = byId("search-error");
  var statusBox = byId("search-status");
  var areaButton = byId("search-this-area");

  var defaultRadius = radius.value;
  var near = { lat: "", lng: "", label: "" };
  var area = "";          // applied "Search This Area" circle: "lat,lng,radius"
  var previewArea = null;  // circle shown after a drag, not searched yet
  var requestId = 0;

  // --- Reading and writing the controls --------------------------------------

  // Category is one dropdown (#67). The AI can pick several categories; then
  // the dropdown shows one extra option holding all of them, so "Edit in
  // filters" keeps the AI's search intact.
  var MULTI = "multiple";

  function categoryOption(value) {
    return Array.prototype.filter.call(categorySelect.options, function (o) {
      return o.value === value;
    })[0];
  }

  function readCategories() {
    var option = categorySelect.options[categorySelect.selectedIndex];
    if (!option || !option.value) return [];
    return option.value === MULTI ? option.dataset.values.split(",") : [option.value];
  }

  function setCategories(values) {
    var multi = categoryOption(MULTI);
    if (multi) multi.remove();
    values = (values || []).filter(function (v) { return v && v !== MULTI && categoryOption(v); });
    if (values.length > 1) {
      multi = document.createElement("option");
      multi.value = MULTI;
      multi.dataset.values = values.join(",");
      multi.textContent = values.length + " categories";
      categorySelect.appendChild(multi);
    }
    categorySelect.value = values.length > 1 ? MULTI : (values[0] || "");
  }

  function readTime(group) {
    return window.Time12.read(group) || "";  // invalid times are reported by runSearch
  }

  function readFilters() {
    var when = whenSelect.value;
    var picked = when === "dates";
    return {
      q: qInput.value.trim(),
      category: readCategories(),
      when: picked ? "" : when,
      date_from: picked ? dateFrom.value : "",
      date_to: picked && rangeBox.checked ? dateTo.value : "",
      time_from: readTime(timeFrom),  // 24-hour "HH:MM" for the server
      time_to: readTime(timeTo),
      near_lat: near.lat,
      near_lng: near.lng,
      near_label: near.lat ? near.label : "",
      radius_mi: near.lat ? radius.value : "",
      area: area,
      include_not_going: includeNotGoing.checked ? "1" : "",
    };
  }

  // The quick-date dropdown and "Pick dates" are separate controls; picked
  // dates show as "Picked dates" in the dropdown.
  function setWhen(value) {
    whenSelect.value = value;
    datesBox.hidden = value !== "dates";
    pickDates.setAttribute("aria-expanded", String(value === "dates"));
  }

  function setRange(isRange) {
    rangeBox.checked = isRange;
    dateToWrap.hidden = !isRange;
    dateFromLabel.textContent = isRange ? "From" : "On";
    if (!isRange) dateTo.value = "";
  }

  function writeFilters(f) {
    qInput.value = f.q || "";
    setCategories(f.category);
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
    window.Time12.write(timeFrom, f.time_from);
    window.Time12.write(timeTo, f.time_to);
    near = { lat: f.near_lat || "", lng: f.near_lng || "", label: f.near_label || "" };
    address.value = near.lat ? (near.label || "Selected location") : "";
    radius.value = f.radius_mi || defaultRadius;
    area = f.area || "";
    includeNotGoing.checked = Boolean(f.include_not_going);
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
      include_not_going: params.get("include_not_going") || "",
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
      list.push({ label: labelFor(categoryOption(value)), focus: categorySelect, remove: function () {
        setCategories(readCategories().filter(function (v) { return v !== value; }));
      } });
    });
    if (f.when) {
      var option = Array.prototype.filter.call(whenSelect.options, function (o) {
        return o.value === f.when;
      })[0];
      list.push({ label: labelFor(option), focus: whenSelect, remove: function () { setWhen(""); } });
    } else if (f.date_from) {
      var label = shortDate(f.date_from) + (f.date_to && f.date_to !== f.date_from
        ? " – " + shortDate(f.date_to) : "");
      list.push({ label: label, focus: dateFrom, remove: function () {
        setWhen(""); dateFrom.value = ""; setRange(false);
      } });
    }
    if (f.time_from || f.time_to) {
      var from = window.Time12.label(f.time_from);
      var to = window.Time12.label(f.time_to);
      var timeLabel = f.time_from && f.time_to ? "Starts " + from + "–" + to
        : (f.time_from ? "Starts after " + from : "Starts before " + to);
      list.push({ label: timeLabel, focus: timeFrom.querySelector(".time12-hour"), remove: function () {
        window.Time12.write(timeFrom, ""); window.Time12.write(timeTo, "");
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
    if (f.include_not_going) {
      list.push({ label: "Including Not Going", focus: includeNotGoing,
        remove: function () { includeNotGoing.checked = false; } });
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
        chip.focus.focus();
      });
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "search-chip-remove";
      remove.setAttribute("aria-label", "Remove Filter: " + chip.label);
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
    var page = new URLSearchParams(params);
    if (mode === "ai") page.set("mode", "ai");
    var query = page.toString();
    window.history.replaceState(null, "", window.location.pathname + (query ? "?" + query : ""));
  }

  var NEW_YORK_TIME = {
    timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  };

  // Events without an image, or whose image fails to load, show the default
  // bulldog (#79) instead of their first letter.
  function useDefaultImage(img) {
    if (!defaultImage || img.getAttribute("src") === defaultImage) return;
    img.src = defaultImage;
  }

  function thumbnail(event) {
    var box = document.createElement("span");
    box.className = "search-result-thumb";
    box.setAttribute("aria-hidden", "true");
    var img = document.createElement("img");
    img.alt = "";
    img.loading = "lazy";
    img.addEventListener("error", function () { useDefaultImage(img); });
    img.src = event.image_url || defaultImage;
    box.appendChild(img);
    return box;
  }

  // Result cards (#34): thumbnail, name, date and time, price and category.
  function renderResults(events, target) {
    target = target || results;
    target.replaceChildren();
    events.forEach(function (event, index) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.className = "search-result";
      link.href = event.detail_url;
      link.addEventListener("click", function (clickEvent) {
        // Open the event over the map; a modified click still opens the page.
        if (clickEvent.metaKey || clickEvent.ctrlKey || clickEvent.shiftKey ||
            clickEvent.button !== 0) return;
        clickEvent.preventDefault();
        openEvent(index, link);
      });
      var text = document.createElement("span");
      text.className = "search-result-text";
      var name = document.createElement("strong");
      name.textContent = event.name;
      var when = document.createElement("span");
      when.textContent = new Date(event.start_at).toLocaleString("en-US", NEW_YORK_TIME);
      var details = document.createElement("span");
      details.textContent = event.price + " \u00b7 " + event.category_label;
      text.appendChild(name);
      text.appendChild(when);
      text.appendChild(details);
      link.appendChild(thumbnail(event));
      link.appendChild(text);
      item.appendChild(link);
      target.appendChild(item);
    });
  }

  // --- Event dialog (#34) --------------------------------------------------------

  function eventPopupUrl(event) {
    return event.popup_url || popupUrl.replace("/0/", "/" + event.id + "/");
  }

  function showEvent(index) {
    var event = currentEvents[index];
    if (!event) return;
    openIndex = index;
    dialogPosition.textContent = (index + 1) + " of " + currentEvents.length;
    prevButton.disabled = index === 0;
    nextButton.disabled = index === currentEvents.length - 1;
    dialogContent.textContent = "Loading\u2026";
    if (window.eventMap) window.eventMap.focusEvent(event.id);
    fetch(eventPopupUrl(event), { credentials: "same-origin", headers: { "Accept": "text/html" } })
      .then(function (response) {
        if (!response.ok) throw new Error("not found");
        return response.text();
      }).then(function (html) {
        if (openIndex !== index) return;  // the user already moved on
        dialogContent.innerHTML = html;  // rendered (and escaped) by our server
        dialogContent.querySelectorAll("img").forEach(function (img) {
          img.addEventListener("error", function () { useDefaultImage(img); });
        });
      }).catch(function () {
        if (openIndex !== index) return;
        dialogContent.textContent = "This event couldn't be loaded. It may have been removed.";
      });
  }

  function openEvent(index, trigger) {
    openedFrom = trigger || null;
    showEvent(index);
    if (!dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    }
  }

  function closeEvent() {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
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

  // Shows the view for the current mode or, when collapsed, only the one-line
  // summary so the map is visible.
  function showViews() {
    form.hidden = collapsed || mode === "ai";
    aiView.hidden = collapsed || mode !== "ai";
    summary.hidden = !collapsed;
    collapseButton.setAttribute("aria-expanded", String(!collapsed));
    summary.setAttribute("aria-expanded", String(!collapsed));
    summary.setAttribute("aria-controls", mode === "ai" ? "search-ai" : "search-form");
  }

  function setCollapsed(value) {
    if (value === collapsed) return;
    collapsed = value;
    showViews();
    // Desktop: the map widens into the space the side panel used (#34).
    document.body.classList.toggle("search-collapsed", collapsed);
    if (window.eventMap) window.eventMap.resize();
  }

  // AI mode replaces the filters view; the filters (and the pins) stay as they
  // are, so going back shows them unchanged.
  function setMode(value) {
    mode = value;
    showViews();
    updateUrl(toParams(readFilters()));
    updateSummary();
  }

  function updateSummary() {
    var parts = chipList(readFilters()).map(function (chip) { return chip.label; });
    if (statusBox.textContent) parts.push(statusBox.textContent);
    if (mode === "ai") parts.unshift("Ask AI");
    summaryText.textContent = parts.length ? parts.join(" \u00b7 ") : "Search Events";
  }

  function runSearch() {
    showError("");
    if (address.value.trim() && !near.lat) {
      showError("Choose an address from the suggestions, or use your location.");
      return;
    }
    if (window.Time12.read(timeFrom) === null || window.Time12.read(timeTo) === null) {
      showError("Enter start times like 8:30, from 1 to 12, with AM or PM.");
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
      // In AI mode the pins show the AI's results once there are any.
      if (mode === "filters" || !lastFilters()) {
        if (window.eventMap) window.eventMap.setEvents(events);
        currentEvents = events;
      }
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

  // Manual search replaces the icon bar (#67); results stay below both.
  function openFilters(open) {
    filters.hidden = !open;
    iconBar.hidden = open;
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

  whenSelect.addEventListener("change", function () { setWhen(whenSelect.value); applySoon(); });
  pickDates.addEventListener("click", function () {
    setWhen("dates");
    dateFrom.focus();
    // Open the calendar right away where the browser allows it.
    try { if (dateFrom.showPicker) dateFrom.showPicker(); } catch (e) { /* needs a user gesture */ }
  });
  rangeBox.addEventListener("change", function () { setRange(rangeBox.checked); applySoon(); });
  categorySelect.addEventListener("change", function () {
    if (categorySelect.value !== MULTI) setCategories(readCategories());
  });
  [categorySelect, dateFrom, dateTo].concat(window.Time12.inputs(timeFrom), window.Time12.inputs(timeTo))
    .forEach(function (input) {
      input.addEventListener("change", applySoon);
    });
  radius.addEventListener("change", function () { if (near.lat) applySoon(); });
  includeNotGoing.addEventListener("change", applySoon);

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
    // Back where the user was: the AI view, the filters, or the icon bar (#65).
    (mode === "ai" ? aiBack : (filters.hidden ? filtersToggle : qInput)).focus();
  });
  function openAi() {
    setMode("ai");
    showAiResults();
    setInputMode(aiInputMode);
  }
  aiToggle.addEventListener("click", openAi);
  filtersAi.addEventListener("click", openAi);  // "Search with AI" (#67)
  // Back to the icon bar: like the AI view's Back, this leaves search (#66).
  filtersBack.addEventListener("click", function () {
    openFilters(false);
    resetChat();
    filtersToggle.focus();
  });
  // Back to the icon bar (#66). Leaving search ends the conversation, which
  // replaced the "New chat" button.
  aiBack.addEventListener("click", function () {
    stopVoice();
    resetChat();
    setMode("filters");
    openFilters(false);
    runSearch();  // the pins go back to the manual filters
    aiToggle.focus();
  });
  // Switching to manual search keeps the conversation for "Search with AI".
  aiManual.addEventListener("click", function () {
    stopVoice();
    setMode("filters");
    openFilters(true);
    runSearch();
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

  // After a drag or zoom, preview the circle that "Search This Area" would use.
  if (window.eventMap) {
    // Phones: dragging the map tucks the panel away so the map is visible.
    window.eventMap.onUserMoveStart(function () {
      if (phone.matches) setCollapsed(true);
    });
    window.eventMap.onUserMove(function () {
      previewArea = window.eventMap.viewCircle();
      areaButton.textContent = "Search This Area (" + previewArea.radius + " mi)";
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

  // --- AI chat (#36) ------------------------------------------------------------
  // The server keeps the conversation the AI sees (session); the tab keeps the
  // same transcript (sessionStorage) so a refresh shows it again.

  var CHAT_KEY = "ai-search-chat";
  var chat = [];       // {role: "user"|"ai"|"error", text, notes, filters, count}
  var aiEvents = [];   // results of the latest AI answer
  var aiBusy = false;

  function csrfToken() {
    var input = aiForm.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  function saveChat() {
    try { window.sessionStorage.setItem(CHAT_KEY, JSON.stringify(chat)); } catch (e) { /* private mode */ }
  }

  function loadChat() {
    try { chat = JSON.parse(window.sessionStorage.getItem(CHAT_KEY)) || []; } catch (e) { chat = []; }
    if (!Array.isArray(chat)) chat = [];
  }

  function filtersToParams(filters) {
    return toParams(filters || {});
  }

  function editInFilters(filters) {
    writeFilters(fromParams(filtersToParams(filters)));
    previewArea = null;
    areaButton.hidden = true;
    setMode("filters");
    openFilters(true);
    runSearch();
    qInput.focus();
  }

  // Recurring searches (#37). The latest answer with filters offers to keep
  // looking every day. When My Queries sent the user here to edit a saved search
  // (data-edit-id), it offers to replace that search instead, after a confirmation.
  // The server re-validates the filters; the confirmation is enforced there too.
  var saveUrl = panel.dataset.saveUrl;
  var editId = panel.dataset.editId || "";
  var editLabel = panel.dataset.editLabel || "";

  function recurringBox(entry) {
    var state = entry.recurring || "ask";
    var done = state === "saved" || state === "replaced";
    var latest = chat.filter(function (e) { return e.role === "ai"; }).pop() === entry;
    if (state === "declined" || (!done && !latest)) return null;

    var box = document.createElement("div");
    box.className = "search-ai-recurring";
    var text = document.createElement("span");
    box.appendChild(text);
    function add(label, handler) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.addEventListener("click", handler);
      box.appendChild(button);
    }
    function set(next, note) {
      entry.recurring = next;
      entry.recurringNote = note || "";
      saveChat();
      renderChat();
    }
    function send(url, confirmed) {
      box.querySelectorAll("button").forEach(function (button) { button.disabled = true; });
      var previous = chat[chat.indexOf(entry) - 1];
      var body = new FormData();
      body.append("filters", JSON.stringify(entry.filters));
      body.append("label", previous && previous.text ? previous.text : "");
      if (confirmed) body.append("confirm", "1");
      fetch(url, {
        method: "POST", credentials: "same-origin",
        headers: { "Accept": "application/json", "X-CSRFToken": csrfToken() }, body: body,
      }).then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (payload) {
          set(response.ok ? (confirmed ? "replaced" : "saved") : "ask",
            response.ok ? "" : payload.error || "That couldn't be saved. Try again.");
        });
      }).catch(function () { set("ask", "Couldn't reach the server. Try again."); });
    }

    if (done) {
      text.textContent = state === "saved"
        ? "Saved. New matches will show up in My Events under Suggested."
        : "Saved search updated.";
    } else if (state === "confirm") {
      text.textContent = "Replace “" + editLabel + "” with this search?";
      add("Yes, Replace", function () { send(panel.dataset.updateUrl, true); });
      add("Cancel", function () { set("ask"); });
    } else if (editId) {
      text.textContent = entry.recurringNote || "";
      add("Replace Saved Search", function () { set("confirm"); });
    } else {
      text.textContent = entry.recurringNote || "Keep looking for this every day?";
      add("Yes", function () { send(saveUrl, false); });
      add("No Thanks", function () { set("declined"); });
    }
    return box;
  }

  function aiEntry(entry) {
    var item = document.createElement("li");
    item.className = "search-ai-message search-ai-message--" + entry.role;
    if (entry.imageName) {
      var attached = document.createElement("p");
      attached.className = "search-ai-attached";
      attached.textContent = "\ud83d\udcce " + entry.imageName;
      item.appendChild(attached);
    }
    if (entry.text) {
      var text = document.createElement("p");
      text.textContent = entry.text;
      item.appendChild(text);
    }
    if (entry.role === "error") item.setAttribute("role", "alert");
    if (entry.role !== "ai") return item;

    (entry.notes || []).forEach(function (note) {
      var p = document.createElement("p");
      p.className = "search-ai-note";
      p.textContent = note;
      item.appendChild(p);
    });
    var labels = chipList(fromParams(filtersToParams(entry.filters)))
      .map(function (chip) { return chip.label; });
    if (labels.length) {
      var list = document.createElement("ul");
      list.className = "search-chips";
      list.setAttribute("aria-label", "Filters the AI used");
      labels.forEach(function (label) {
        var chip = document.createElement("li");
        chip.className = "search-chip search-chip--static";
        chip.textContent = label;
        list.appendChild(chip);
      });
      item.appendChild(list);
    }
    var footer = document.createElement("div");
    footer.className = "search-ai-footer";
    var count = document.createElement("span");
    count.textContent = entry.count === 0 ? "No events found"
      : (entry.count === 1 ? "1 event" : entry.count + " events");
    footer.appendChild(count);
    var edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "Edit in Filters";
    edit.addEventListener("click", function () { editInFilters(entry.filters); });
    footer.appendChild(edit);
    item.appendChild(footer);
    var recurring = labels.length ? recurringBox(entry) : null;
    if (recurring) item.appendChild(recurring);
    return item;
  }

  function renderChat() {
    var intro = aiLog.querySelector(".search-ai-intro");
    aiLog.replaceChildren(intro);
    chat.forEach(function (entry) { aiLog.appendChild(aiEntry(entry)); });
  }

  function scrollChatToEnd() {
    var last = aiLog.lastElementChild;
    if (last && last.scrollIntoView) last.scrollIntoView({ block: "nearest" });
  }

  // Cards and pins show the latest AI results while in AI mode.
  // Before the first answer, the pins and the dialog keep the manual results.
  function showAiResults() {
    renderResults(aiEvents, aiResults);
    if (mode !== "ai" || !lastFilters()) return;
    currentEvents = aiEvents;
    if (window.eventMap) window.eventMap.setEvents(aiEvents);
  }

  function setAiBusy(busy) {
    aiBusy = busy;
    aiSend.disabled = busy;
    aiSend.textContent = busy ? "Searching\u2026" : "Send";
  }

  function lastFilters() {
    for (var i = (chat || []).length - 1; i >= 0; i--) {
      if (chat[i].role === "ai") return chat[i].filters;
    }
    return null;
  }

  // --- Attached image (a poster, for example) --------------------------------------

  function showAttachmentError(message) {
    aiAttachmentError.textContent = message || "";
    aiAttachmentError.hidden = !message;
  }

  function clearAttachment() {
    if (aiAttachmentPreview.src) URL.revokeObjectURL(aiAttachmentPreview.src);
    aiAttachmentPreview.removeAttribute("src");
    attachedImage = null;
    aiImage.value = "";
    aiAttachment.hidden = true;
  }

  aiImage.addEventListener("change", function () {
    var file = aiImage.files && aiImage.files[0];
    clearAttachment();
    showAttachmentError("");
    if (!file) return;
    // Same rules as the server, checked first so the user isn't kept waiting.
    var type = file.type || (/\.hei[cf]$/i.test(file.name) ? "image/heic" : "");
    if (IMAGE_TYPES.indexOf(type) === -1) {
      showAttachmentError("Choose a PNG, JPEG or HEIC image.");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      showAttachmentError("Choose an image no larger than 5 MB.");
      return;
    }
    attachedImage = file;
    aiAttachmentName.textContent = file.name;
    aiAttachmentPreview.src = URL.createObjectURL(file);  // HEIC may not preview; the name still shows
    aiAttachment.hidden = false;
  });
  byId("search-ai-attachment-remove").addEventListener("click", function () {
    clearAttachment();
    aiInput.focus();
  });

  function sendToAi(message) {
    var image = attachedImage;
    if (aiBusy || (!message && !image)) return;
    chat.push({ role: "user", text: message, imageName: image ? image.name : "" });
    renderChat();
    scrollChatToEnd();
    aiInput.value = "";
    aiCount.textContent = "0/300";
    clearAttachment();
    showAttachmentError("");
    setAiBusy(true);

    var body = new FormData();
    body.append("message", message);
    if (image) body.append("image", image);
    fetch(aiUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Accept": "application/json", "X-CSRFToken": csrfToken() },
      body: body,
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (payload) {
        return { ok: response.ok, payload: payload };
      });
    }).then(function (result) {
      if (!result.ok) {
        chat.push({ role: "error", text: result.payload.error ||
          "AI search isn't available right now. Manual search still works." });
        return;
      }
      var data = result.payload;
      chat.push({ role: "ai", text: data.reply, notes: data.notes || [],
        filters: data.filters || {}, count: data.count });
      aiEvents = data.events || [];
      showAiResults();
    }).catch(function () {
      chat.push({ role: "error", text: "Couldn't reach the server. Check your connection and try again." });
    }).then(function () {
      setAiBusy(false);
      saveChat();
      renderChat();
      scrollChatToEnd();
      var answer = chat[chat.length - 1];
      if (answer && answer.role !== "user") speak(answer.text);
    });
  }

  aiForm.addEventListener("submit", function (event) {
    event.preventDefault();
    sendToAi(aiInput.value.trim());
  });
  aiInput.addEventListener("input", function () {
    aiCount.textContent = aiInput.value.length + "/300";
  });
  aiInput.addEventListener("keydown", function (event) {
    // Enter sends; Shift+Enter starts a new line.
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendToAi(aiInput.value.trim());
    }
  });
  // Forgets the conversation here and on the server (the AI's context).
  function resetChat() {
    if (chat.length) {  // nothing to forget on the server otherwise
      fetch(aiResetUrl, {
        method: "POST", credentials: "same-origin",
        headers: { "X-CSRFToken": csrfToken() }, body: new FormData(),
      }).catch(function () { /* the server forgets it at the end of the session anyway */ });
    }
    chat = [];
    aiEvents = [];
    stopVoice();
    clearAttachment();
    showAttachmentError("");
    saveChat();
    renderChat();
    renderResults([], aiResults);
  }

  // --- Input modes and voice (#36) --------------------------------------------------
  // start: attach | large microphone | type.  text: message box, small microphone
  // at the top right, nothing spoken.  voice: live transcript, replies read aloud,
  // volume/mute at the bottom right, X at the top right back to text.
  // Speech recognition and speech output are the browser's own (Web Speech API).

  var aiControls = byId("search-ai-controls");
  var aiMic = byId("search-ai-mic");
  var aiMicSmall = byId("search-ai-mic-small");
  var aiVoiceExit = byId("search-ai-voice-exit");
  var aiKeyboard = byId("search-ai-keyboard");
  var aiVolume = byId("search-ai-volume");
  var aiVoiceStatus = byId("search-ai-voice-status");
  var aiTranscript = byId("search-ai-transcript");
  var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var VOICE_UNSUPPORTED = "Voice isn't supported in this browser. You can type instead.";
  // Light outline icons (emoji speakers were too dark to see on the panel).
  var VOLUME_ON_ICON = aiVolume.innerHTML;
  var VOLUME_OFF_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9l5 6M22 9l-5 6"/></svg>';
  var aiInputMode = "start";
  var recognizer = null;
  var muted = false;

  function setVoiceStatus(message) {
    aiVoiceStatus.textContent = message || "";
    aiVoiceStatus.hidden = !message;
  }

  function setInputMode(value) {
    aiInputMode = value;
    aiControls.hidden = value === "text";
    aiForm.hidden = value !== "text";
    aiMicSmall.hidden = value !== "text";
    aiVoiceExit.hidden = value !== "voice";
    aiKeyboard.hidden = value !== "start";
    aiVolume.hidden = value !== "voice";
    if (value !== "voice") {
      stopListening();
      stopSpeaking();
      setVoiceStatus("");
      aiTranscript.hidden = true;
    }
    if (value === "text" && mode === "ai") aiInput.focus();
  }

  function stopSpeaking() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  function speak(text) {
    if (aiInputMode !== "voice" || muted || !text || !window.speechSynthesis) return;
    stopSpeaking();
    var utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    window.speechSynthesis.speak(utterance);
  }

  function stopListening() {
    if (recognizer) {
      var current = recognizer;
      recognizer = null;  // so its end event doesn't send anything
      try { current.abort(); } catch (e) { /* already stopped */ }
    }
    aiMic.classList.remove("is-listening");
    aiMic.setAttribute("aria-pressed", "false");
  }

  function stopVoice() {
    stopListening();
    stopSpeaking();
  }

  function startListening() {
    if (!Recognition) {
      setInputMode("text");
      showAttachmentError(VOICE_UNSUPPORTED);
      return;
    }
    showAttachmentError("");
    setInputMode("voice");
    stopSpeaking();
    var heard = "";
    var current = new Recognition();
    current.lang = "en-US";
    current.interimResults = true;
    current.continuous = false;
    current.maxAlternatives = 1;
    current.onstart = function () {
      aiMic.classList.add("is-listening");
      aiMic.setAttribute("aria-pressed", "true");
      setVoiceStatus("Listening\u2026 speak now. Tap the microphone to stop.");
      aiTranscript.textContent = "";
      aiTranscript.hidden = false;
    };
    current.onresult = function (event) {
      var interim = "";
      heard = "";
      for (var i = 0; i < event.results.length; i++) {
        if (event.results[i].isFinal) heard += event.results[i][0].transcript;
        else interim += event.results[i][0].transcript;
      }
      aiTranscript.textContent = (heard + interim).trim();
    };
    current.onerror = function (event) {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        showAttachmentError("Microphone access is blocked. Allow it in your browser, or type instead.");
      } else if (event.error === "no-speech") {
        setVoiceStatus("I didn't hear anything. Tap the microphone to try again.");
      } else if (event.error !== "aborted") {
        setVoiceStatus("Voice input stopped. Tap the microphone to try again.");
      }
    };
    current.onend = function () {
      if (recognizer !== current) return;  // stopped on purpose
      recognizer = null;
      aiMic.classList.remove("is-listening");
      aiMic.setAttribute("aria-pressed", "false");
      var text = heard.trim().slice(0, 300);
      if (text) {
        setVoiceStatus("");
        aiTranscript.hidden = true;
        sendToAi(text);  // the transcript becomes a chat message
      } else if (!aiVoiceStatus.textContent || /Listening/.test(aiVoiceStatus.textContent)) {
        setVoiceStatus("Tap the microphone and say what you're looking for.");
      }
    };
    recognizer = current;
    try {
      current.start();
    } catch (e) {
      recognizer = null;
      setVoiceStatus("Voice input couldn't start. Tap the microphone to try again.");
    }
  }

  aiMic.addEventListener("click", function () {
    if (recognizer) {
      recognizer.stop();  // finish now; what was heard is sent
      return;
    }
    startListening();
  });
  aiMicSmall.addEventListener("click", startListening);
  aiKeyboard.addEventListener("click", function () { setInputMode("text"); });
  aiVoiceExit.addEventListener("click", function () {
    setInputMode("text");
  });
  aiVolume.addEventListener("click", function () {
    muted = !muted;
    if (muted) stopSpeaking();
    aiVolume.setAttribute("aria-pressed", String(muted));
    aiVolume.setAttribute("aria-label", muted ? "Turn Spoken Replies On" : "Mute Spoken Replies");
    aiVolume.title = aiVolume.getAttribute("aria-label");
    aiVolume.innerHTML = muted ? VOLUME_OFF_ICON : VOLUME_ON_ICON;  // constant SVG markup
  });

  // Restore the transcript and fetch fresh results for its latest filters.
  loadChat();
  renderChat();
  if (lastFilters()) {
    fetch(searchUrl + "?" + filtersToParams(lastFilters()).toString(), {
      credentials: "same-origin", headers: { "Accept": "application/json" },
    }).then(function (response) { return response.ok ? response.json() : { events: [] }; })
      .then(function (payload) {
        aiEvents = payload.events || [];
        showAiResults();
      }).catch(function () { /* the cards stay empty; the next message refreshes them */ });
  }

  prevButton.addEventListener("click", function () { showEvent(openIndex - 1); });
  nextButton.addEventListener("click", function () { showEvent(openIndex + 1); });
  byId("search-event-close").addEventListener("click", closeEvent);
  dialog.addEventListener("click", function (clickEvent) {
    if (clickEvent.target === dialog) closeEvent();  // click on the backdrop
  });
  dialog.addEventListener("close", function () {
    openIndex = -1;
    dialogContent.replaceChildren();
    // Back to where the user was in the panel (its scroll position is unchanged).
    if (openedFrom && document.contains(openedFrom)) openedFrom.focus();
  });

  // Map pins open the same dialog, stepping through the same list.
  if (window.eventMap) {
    window.eventMap.onEventClick(function (id) {
      var index = currentEvents.map(function (e) { return e.id; }).indexOf(id);
      if (index !== -1) openEvent(index, null);
    });
  }

  // Load the list on arrival: the URL's filters (refresh, back, shared link)
  // or, without any, all upcoming events.
  var initial = new URLSearchParams(window.location.search);
  if (initial.toString()) writeFilters(fromParams(initial));
  if (initial.get("mode") === "ai") setMode("ai");
  if (editId) {  // editing a saved search from My Queries (#37)
    var editNote = document.createElement("p");
    editNote.className = "search-ai-note search-ai-editing";
    editNote.textContent = "Editing your saved search “" + editLabel +
      "”. Tell me what to change, then replace it.";
    aiLog.before(editNote);
    setMode("ai");
  }
  runSearch();
})();
