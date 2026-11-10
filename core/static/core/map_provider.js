// Map provider (#8): MapLibre GL JS rendering a MapTiler dark style.
// Loaded via templates/core/_map_provider.html. map.js calls window.renderMap
// with the server's config: {"apiKey": "...", "center": [lat, lng], "zoom": 13}.
(function () {
  "use strict";

  // MapTiler's minimal dark basemap. Background and water are then tinted to
  // the page's blue-black so the map and the page read as one surface.
  var STYLE_ID = "dataviz-dark";
  var BLUE_BLACK = "#0b1220";  // matches --map-bg in map.css
  var DEEP_WATER = "#0e1d36";
  var WATER_LAYER = /water|ocean|lake|river/i;

  function styleUrl(apiKey) {
    return "https://api.maptiler.com/maps/" + STYLE_ID +
      "/style.json?key=" + encodeURIComponent(apiKey);
  }

  function tintBlueBlack(map) {
    var layers = (map.getStyle() && map.getStyle().layers) || [];
    layers.forEach(function (layer) {
      try {
        if (layer.type === "background") {
          map.setPaintProperty(layer.id, "background-color", BLUE_BLACK);
        } else if (layer.type === "fill" && WATER_LAYER.test(layer.id)) {
          map.setPaintProperty(layer.id, "fill-color", DEEP_WATER);
        }
      } catch (error) {
        // Cosmetic only: keep MapTiler's own colour for this layer.
      }
    });
  }

  window.renderMap = function (element, config) {
    if (typeof window.maplibregl === "undefined") {
      throw new Error("MapLibre GL JS did not load");
    }

    var lat = config.center[0];
    var lng = config.center[1];
    var loaded = false;
    var failed = false;

    // Throws if the browser has no WebGL; map.js then shows the fallback.
    var map = new window.maplibregl.Map({
      container: element,
      style: styleUrl(config.apiKey),
      center: [lng, lat],  // MapLibre takes [longitude, latitude]
      zoom: config.zoom,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      attributionControl: { compact: true },
    });
    map.touchZoomRotate.disableRotation();

    function fail(reason) {
      if (failed) {
        return;
      }
      failed = true;
      element.hidden = true;
      if (typeof window.showMapFallback === "function") {
        window.showMapFallback(reason);
      }
    }

    // A 0px-tall container renders nothing and raises no error, so check it
    // explicitly (the MapLibre stylesheet has loaded by now: it comes before
    // this script, and scripts wait for earlier stylesheets).
    if (element.clientHeight === 0 || element.clientWidth === 0) {
      fail("the map container has no size (check map.css)");
      map.remove();
      return null;
    }

    map.on("style.load", function () {
      tintBlueBlack(map);
    });
    map.on("load", function () {
      loaded = true;
    });
    map.on("error", function (event) {
      var status = event && event.error && event.error.status;
      if (status === 401 || status === 403) {
        // Wrong key, or the key isn't allowed on this domain.
        fail("MapTiler rejected the key (HTTP " + status + ")");
      } else if (!loaded && !(event && event.sourceId)) {
        // The style itself failed to load (not just one tile).
        fail("the map style could not be loaded");
      }
    });

    return map;
  };
})();
