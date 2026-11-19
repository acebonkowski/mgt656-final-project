// Provider-neutral map loader (#8).
// Reads the config the server put in the page, then hands it to the provider's
// window.renderMap (defined in map_provider.js, loaded via _map_provider.html).
// If the local provider is unavailable, the fallback is shown.
(function () {
  "use strict";

  var openButton = document.getElementById("open-event-form");
  var dialog = document.getElementById("event-form-dialog");
  var closeButton = document.getElementById("close-event-form");

  // Always open as a modal: a non-modal dialog sits under the full-screen map,
  // and showModal() throws if the dialog is already open (#57).
  function openEventForm() {
    if (dialog.open) return;
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  }

  if (openButton && dialog) {
    openButton.addEventListener("click", openEventForm);
  }
  // The server marks the dialog when a submit was rejected, so the user sees
  // the form again with its errors.
  if (dialog && dialog.hasAttribute("data-open-on-load")) {
    openEventForm();
  }
  if (closeButton && dialog) {
    closeButton.addEventListener("click", function () {
      if (typeof dialog.close === "function") {
        dialog.close();
      } else {
        dialog.removeAttribute("open");
      }
    });
  }

  var locationInput = document.getElementById("id_location");
  var latitudeInput = document.getElementById("id_latitude");
  var longitudeInput = document.getElementById("id_longitude");
  var locationConfirmed = document.getElementById("id_location_confirmed");
  if (locationInput && dialog) {
    var locationGroup = locationInput.parentElement;
    var suggestions = document.createElement("div");
    suggestions.id = "address-suggestions";
    suggestions.className = "address-suggestions";
    suggestions.setAttribute("role", "listbox");
    suggestions.hidden = true;
    locationGroup.appendChild(suggestions);
    var timer = null;

    locationInput.addEventListener("input", function () {
      if (locationConfirmed) locationConfirmed.value = "";
      if (latitudeInput) latitudeInput.value = "";
      if (longitudeInput) longitudeInput.value = "";
      var query = locationInput.value.trim();
      window.clearTimeout(timer);
      if (query.length < 3) {
        suggestions.hidden = true;
        suggestions.replaceChildren();
        return;
      }
      timer = window.setTimeout(function () {
        fetch(dialog.dataset.geocodeUrl + "?q=" + encodeURIComponent(query), {
          credentials: "same-origin",
          headers: {"Accept": "application/json"},
        }).then(function (response) {
          if (!response.ok) throw new Error("Address search failed.");
          return response.json();
        }).then(function (payload) {
          suggestions.replaceChildren();
          (payload.suggestions || []).forEach(function (item) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "address-suggestion";
            button.setAttribute("role", "option");
            button.textContent = item.address;
            button.addEventListener("click", function () {
              locationInput.value = item.address;
              if (locationConfirmed) locationConfirmed.value = item.address;
              if (latitudeInput) latitudeInput.value = String(item.latitude);
              if (longitudeInput) longitudeInput.value = String(item.longitude);
              suggestions.hidden = true;
              suggestions.replaceChildren();
            });
            suggestions.appendChild(button);
          });
          suggestions.hidden = (payload.suggestions || []).length === 0;
        }).catch(function () {
          suggestions.hidden = true;
        });
      }, 300);
    });

    var duplicateDialog = document.getElementById("duplicate-event-dialog");
    var duplicateAlertClose = document.getElementById("close-duplicate-alert");
    var viewDuplicate = document.getElementById("view-duplicate-event");
    var detailPopup = document.getElementById("event-detail-popup");
    var detailContent = document.getElementById("event-detail-content");
    var detailFirstStep = document.getElementById("event-detail-first-step");
    var detailSecondStep = document.getElementById("event-detail-second-step");
    var submitButton = document.getElementById("create-event-submit");
    var dateInput = document.getElementById("id_date");
    var startInput = document.getElementById("id_start_time");
    var endInput = document.getElementById("id_end_time");
    var duplicateTimer = null;
    var duplicateMatch = null;

    function closeDialog(target) {
      if (!target) return;
      if (typeof target.close === "function") target.close();
      else target.removeAttribute("open");
    }

    function openDialog(target) {
      if (!target) return;
      if (typeof target.showModal === "function") target.showModal();
      else target.setAttribute("open", "");
    }

    function checkDuplicate() {
      window.clearTimeout(duplicateTimer);
      duplicateTimer = window.setTimeout(function () {
        var params = new URLSearchParams({
          location: locationInput.value,
          date: dateInput ? dateInput.value : "",
          start_time: startInput ? startInput.value : "",
          end_time: endInput ? endInput.value : "",
        });
        if (!params.get("location") || !params.get("date") ||
            !params.get("start_time") || !params.get("end_time")) {
          duplicateMatch = null;
          if (submitButton) submitButton.disabled = false;
          if (duplicateDialog && duplicateDialog.open) closeDialog(duplicateDialog);
          return;
        }
        fetch(dialog.dataset.duplicateUrl + "?" + params.toString(), {
          credentials: "same-origin",
          headers: {"Accept": "application/json"},
        }).then(function (response) {
          if (!response.ok) throw new Error("Duplicate check failed.");
          return response.json();
        }).then(function (payload) {
          duplicateMatch = payload.match;
          if (duplicateMatch) {
            if (submitButton) submitButton.disabled = true;
            openDialog(duplicateDialog);
          } else {
            if (submitButton) submitButton.disabled = false;
            if (duplicateDialog && duplicateDialog.open) closeDialog(duplicateDialog);
          }
        }).catch(function () {
          duplicateMatch = null;
        });
      }, 250);
    }

    [locationInput, dateInput, startInput, endInput].forEach(function (input) {
      if (input) input.addEventListener("change", checkDuplicate);
      if (input) input.addEventListener("input", checkDuplicate);
    });
    if (duplicateAlertClose) {
      duplicateAlertClose.addEventListener("click", function () {
        closeDialog(duplicateDialog);
      });
    }
    if (viewDuplicate) {
      viewDuplicate.addEventListener("click", function () {
        if (!duplicateMatch) return;
        fetch(duplicateMatch.detail_url, {
          credentials: "same-origin",
          headers: {"Accept": "text/html"},
        }).then(function (response) {
          if (!response.ok) throw new Error("Could not load event.");
          return response.text();
        }).then(function (html) {
          detailContent.innerHTML = html;
          detailFirstStep.hidden = false;
          detailSecondStep.hidden = true;
          closeDialog(duplicateDialog);
          openDialog(detailPopup);
        });
      });
    }
    var closeDetail = document.getElementById("close-event-detail");
    var thatsMyEvent = document.getElementById("thats-my-event");
    var requestCollab = document.getElementById("request-collab");
    var returnToMap = document.getElementById("return-to-map");
    if (closeDetail) closeDetail.addEventListener("click", function () {
      closeDialog(detailPopup);
    });
    if (thatsMyEvent) thatsMyEvent.addEventListener("click", function () {
      detailFirstStep.hidden = true;
      detailSecondStep.hidden = false;
    });
    if (requestCollab) requestCollab.addEventListener("click", function () {});
    if (returnToMap) returnToMap.addEventListener("click", function () {
      closeDialog(detailPopup);
      closeDialog(duplicateDialog);
      window.location.reload();
    });
  }

  var imageMenu = document.querySelector(".image-menu");
  if (imageMenu) {
    var addButton = document.getElementById("event-image-add");
    var replaceButton = document.getElementById("event-image-replace");
    var deleteButton = document.getElementById("event-image-delete");
    var sources = document.getElementById("event-image-sources");
    var aiButton = document.getElementById("event-image-ai");
    var loading = document.getElementById("event-image-loading");
    var error = document.getElementById("event-image-error");
    var preview = document.getElementById("event-image-preview");
    var previewImage = document.getElementById("event-image-preview-img");
    var formImage = document.getElementById("id_image");
    var aiImage = document.getElementById("id_ai_image");
    var removeImage = document.getElementById("id_remove_image");
    if (formImage && formImage.parentElement) {
      formImage.parentElement.hidden = true;
    }

    function showSources() {
      sources.hidden = !sources.hidden;
    }

    function showSelectedImage(src) {
      previewImage.src = src;
      preview.hidden = false;
      addButton.hidden = true;
      replaceButton.hidden = false;
      deleteButton.hidden = false;
      sources.hidden = true;
    }

    function clearImage() {
      if (formImage) {
        formImage.value = "";
      }
      if (aiImage) {
        aiImage.value = "";
      }
      if (removeImage) removeImage.value = "1";
      previewImage.removeAttribute("src");
      preview.hidden = true;
      addButton.hidden = false;
      replaceButton.hidden = true;
      deleteButton.hidden = true;
      sources.hidden = true;
      error.hidden = true;
    }

    if (addButton) addButton.addEventListener("click", showSources);
    if (replaceButton) replaceButton.addEventListener("click", showSources);
    if (deleteButton) deleteButton.addEventListener("click", clearImage);

    ["event-image-gallery", "event-image-files", "event-image-camera"].forEach(function (id) {
      var input = document.getElementById(id);
      if (!input) return;
      input.addEventListener("change", function () {
        var file = input.files && input.files[0];
        if (!file) return;
        if (typeof DataTransfer !== "undefined" && formImage) {
          var transfer = new DataTransfer();
          transfer.items.add(file);
          formImage.files = transfer.files;
        }
        if (aiImage) aiImage.value = "";
        if (removeImage) removeImage.value = "";
        var reader = new FileReader();
        reader.onload = function () {
          showSelectedImage(reader.result);
        };
        reader.readAsDataURL(file);
      });
    });

    if (aiButton) {
      aiButton.addEventListener("click", function () {
        var csrf = document.querySelector(".event-form input[name=csrfmiddlewaretoken]");
        var name = document.getElementById("id_name");
        var description = document.getElementById("id_description");
        var body = new URLSearchParams();
        body.set("name", name ? name.value : "");
        body.set("description", description ? description.value : "");
        error.hidden = true;
        loading.hidden = false;
        aiButton.disabled = true;
        fetch(imageMenu.dataset.generateUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "X-CSRFToken": csrf ? csrf.value : "",
          },
          body: body.toString(),
          credentials: "same-origin",
        }).then(function (response) {
          return response.json().then(function (payload) {
            if (!response.ok) throw new Error(payload.error || "Image generation failed.");
            return payload;
          });
        }).then(function (payload) {
          if (formImage) formImage.value = "";
          if (aiImage) aiImage.value = payload.image;
          if (removeImage) removeImage.value = "";
          showSelectedImage(payload.image);
        }).catch(function (caught) {
          error.textContent = caught.message || "Image generation failed.";
          error.hidden = false;
        }).then(function () {
          loading.hidden = true;
          aiButton.disabled = false;
        });
      });
    }
  }

  var mapElement = document.getElementById("map");
  var fallback = document.getElementById("map-fallback");
  var configElement = document.getElementById("map-config");

  function showFallback(reason) {
    if (fallback) {
      fallback.hidden = false;
    }
    if (reason && window.console) {
      console.warn("Map unavailable: " + reason);
    }
  }

  var config = null;
  try {
    config = configElement ? JSON.parse(configElement.textContent) : null;
  } catch (error) {
    showFallback("could not read the map config");
    return;
  }

  if (!mapElement || !config || !config.tileUrl) {
    showFallback("local map tiles are unavailable");
    return;
  }

  if (typeof window.renderMap !== "function") {
    showFallback("no map provider loaded");
    return;
  }

  // Lets providers report failures that happen after the initial page load.
  window.showMapFallback = showFallback;

  try {
    window.renderMap(mapElement, config);
  } catch (error) {
    showFallback(error && error.message ? error.message : "map provider failed");
  }
})();
