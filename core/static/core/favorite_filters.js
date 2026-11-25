(function () {
  var form = document.getElementById("favorite-filters");
  if (!form) return;
  var address = form.elements.near_label;
  var lat = form.elements.near_lat;
  var lng = form.elements.near_lng;
  var radius = form.elements.radius_mi;
  var status = document.getElementById("favorite-location-status");
  var options = document.getElementById("favorite-address-options");
  var generation = 0;
  function clearLocation() {
    generation++;
    lat.value = lng.value = "";
    options.replaceChildren();
    status.textContent = "No location filter applied.";
  }
  function selectLocation(latitude, longitude, label) {
    lat.value = String(latitude);
    lng.value = String(longitude);
    address.value = label;
    if (!radius.value) radius.value = "1";
    options.replaceChildren();
    status.textContent = "Location selected. Search favorites to apply.";
  }
  address.addEventListener("input", clearLocation);
  document.getElementById("favorite-clear-location").addEventListener("click", function () {
    clearLocation(); address.value = "";
  });
  document.getElementById("favorite-find-address").addEventListener("click", async function () {
    clearLocation();
    var current = generation;
    var query = address.value.trim();
    if (query.length < 3) { status.textContent = "Enter at least 3 characters to find an address."; return; }
    status.textContent = "Finding addresses…";
    try {
      if (!form.dataset.geocodeUrl) throw new Error("unavailable");
      var response = await fetch(form.dataset.geocodeUrl + "?q=" + encodeURIComponent(query), {
        credentials: "same-origin", headers: { "Accept": "application/json" },
      });
      if (!response.ok) throw new Error("unavailable");
      var payload = await response.json();
      if (current !== generation) return;
      (payload.suggestions || []).forEach(function (item) {
        var button = document.createElement("button");
        button.type = "button";
        button.textContent = item.address;
        button.addEventListener("click", function () {
          generation++;
          selectLocation(item.latitude, item.longitude, item.address);
        });
        options.appendChild(button);
      });
      status.textContent = options.children.length ? "Choose an address below."
        : "No addresses found. Other filters still work without a location.";
    } catch (error) {
      if (current === generation) status.textContent = "Address search is unavailable. Other filters still work without a location.";
    }
  });
  document.getElementById("favorite-my-location").addEventListener("click", function () {
    clearLocation();
    var current = generation;
    if (!navigator.geolocation) { status.textContent = "Location is unavailable. Other filters still work."; return; }
    status.textContent = "Finding your location…";
    navigator.geolocation.getCurrentPosition(function (position) {
      if (current !== generation) return;
      selectLocation(position.coords.latitude, position.coords.longitude, "My location");
    }, function () {
      if (current === generation) status.textContent = "Location could not be shared. Other filters still work without a location.";
    }, { timeout: 10000, maximumAge: 60000 });
  });
})();
