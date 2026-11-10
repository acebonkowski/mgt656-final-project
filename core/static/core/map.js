// Provider-neutral map loader (#8).
// Reads the config the server put in the page, then hands it to the provider's
// window.renderMap (defined in map_provider.js, loaded via _map_provider.html).
// If there is no key, no provider, or the provider fails, the fallback is shown.
(function () {
  "use strict";

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

  if (!mapElement || !config || !config.apiKey) {
    showFallback("no map key configured");
    return;
  }

  if (typeof window.renderMap !== "function") {
    showFallback("no map provider loaded");
    return;
  }

  // Lets providers report failures that happen after the first render,
  // e.g. a rejected key.
  window.showMapFallback = showFallback;

  try {
    window.renderMap(mapElement, config);
  } catch (error) {
    showFallback(error && error.message ? error.message : "map provider failed");
  }
})();
