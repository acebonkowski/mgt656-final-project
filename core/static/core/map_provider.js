// Map provider (#8): MapLibre GL JS rendering local OpenStreetMap vector tiles.
// map.js calls window.renderMap with the server's tile URL and map settings.
(function () {
  "use strict";

  function localStyle(config) {
    return {
      version: 8,
      sources: {
        osm: {
          type: "vector",
          tiles: [window.location.origin + config.tileUrl],
          bounds: config.bounds,
          minzoom: config.minZoom,
          maxzoom: config.maxZoom,
          attribution: "© OpenMapTiles © OpenStreetMap contributors",
        },
      },
      layers: [
        {
          id: "background",
          type: "background",
          paint: {"background-color": "#ebe8e1"},
        },
        {
          id: "landcover",
          type: "fill",
          source: "osm",
          "source-layer": "landcover",
          paint: {"fill-color": "#dfe5dc", "fill-opacity": 0.8},
        },
        {
          id: "landuse",
          type: "fill",
          source: "osm",
          "source-layer": "landuse",
          paint: {"fill-color": "#e6e2d9", "fill-opacity": 0.75},
        },
        {
          id: "parks",
          type: "fill",
          source: "osm",
          "source-layer": "park",
          paint: {"fill-color": "#c8d9c2"},
        },
        {
          id: "water",
          type: "fill",
          source: "osm",
          "source-layer": "water",
          paint: {"fill-color": "#a9cbdc"},
        },
        {
          id: "waterways",
          type: "line",
          source: "osm",
          "source-layer": "waterway",
          paint: {"line-color": "#a9cbdc", "line-width": 1.5},
        },
        {
          id: "buildings",
          type: "fill",
          source: "osm",
          "source-layer": "building",
          minzoom: 13,
          paint: {"fill-color": "#d2cec5", "fill-outline-color": "#c3beb4"},
        },
        {
          id: "roads",
          type: "line",
          source: "osm",
          "source-layer": "transportation",
          paint: {
            "line-color": "#fffdf8",
            "line-width": [
              "interpolate", ["linear"], ["zoom"],
              8, 0.5, 12, 1.5, 16, 5,
            ],
          },
        },
        {
          id: "boundaries",
          type: "line",
          source: "osm",
          "source-layer": "boundary",
          paint: {
            "line-color": "#a29c91",
            "line-width": 1,
            "line-dasharray": [2, 2],
          },
        },
      ],
    };
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
      style: localStyle(config),
      center: [lng, lat],  // MapLibre takes [longitude, latitude]
      zoom: config.zoom,
      minZoom: config.minZoom,
      maxZoom: config.maxZoom,
      maxBounds: [
        [config.bounds[0], config.bounds[1]],
        [config.bounds[2], config.bounds[3]],
      ],
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

    map.on("load", function () {
      loaded = true;
      (config.events || []).forEach(function (event) {
        if (typeof event.latitude !== "number" || typeof event.longitude !== "number") {
          return;
        }
        var popup = new window.maplibregl.Popup({ offset: 16 });
        var content = document.createElement("div");
        var title = document.createElement("strong");
        title.textContent = event.name;
        var price = document.createElement("div");
        price.textContent = event.price;
        content.appendChild(title);
        content.appendChild(price);
        popup.setDOMContent(content);
        new window.maplibregl.Marker({ color: "#4da3ff" })
          .setLngLat([event.longitude, event.latitude])
          .setPopup(popup)
          .addTo(map);
      });
      (config.places || []).forEach(function (place) {
        if (typeof place.latitude !== "number" || typeof place.longitude !== "number") {
          return;
        }
        var markerElement = document.createElement("div");
        markerElement.className = "poi-marker poi-marker--" + place.kind;
        markerElement.setAttribute("role", "img");
        markerElement.setAttribute("aria-label", place.kind + ": " + place.name);
        var symbol = document.createElement("span");
        symbol.className = "poi-marker-symbol";
        symbol.textContent = place.kind === "yale" ? "🏛️" :
          (place.kind === "restaurant" ? "🍴" : "🍸");
        markerElement.appendChild(symbol);

        var popup = new window.maplibregl.Popup({ offset: 18 });
        var content = document.createElement("div");
        var title = document.createElement("strong");
        title.textContent = place.name;
        var address = document.createElement("div");
        address.textContent = place.address;
        content.appendChild(title);
        content.appendChild(address);
        popup.setDOMContent(content);

        new window.maplibregl.Marker({ element: markerElement, anchor: "bottom" })
          .setLngLat([place.longitude, place.latitude])
          .setPopup(popup)
          .addTo(map);
      });
    });
    map.on("error", function (event) {
      if (!loaded && event && event.error) {
        fail(event.error.message || "local map tiles could not be loaded");
      }
    });

    return map;
  };
})();
