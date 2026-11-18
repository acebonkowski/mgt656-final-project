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

    var eventMarkers = [];
    var pendingEvents = null;

    // Clicking a pin opens the event (search panel dialog, #34). Without a
    // listener it falls back to the event page.
    var eventClickHandler = null;

    function eventMarker(event) {
      if (typeof event.latitude !== "number" || typeof event.longitude !== "number") {
        return null;
      }
      var marker = new window.maplibregl.Marker({ color: "#4da3ff" })
        .setLngLat([event.longitude, event.latitude]);
      var element = marker.getElement();
      element.classList.add("event-marker");
      element.setAttribute("role", "button");
      element.setAttribute("tabindex", "0");
      element.setAttribute("aria-label", "Event: " + event.name);
      function open() {
        if (eventClickHandler) eventClickHandler(event.id);
        else window.location.href = event.detail_url || event.url || "/events/" + event.id + "/";
      }
      element.addEventListener("click", function (clickEvent) {
        clickEvent.stopPropagation();
        open();
      });
      element.addEventListener("keydown", function (keyEvent) {
        if (keyEvent.key === "Enter" || keyEvent.key === " ") {
          keyEvent.preventDefault();
          open();
        }
      });
      return marker;
    }

    // Replaces all event markers (search results, #35). Before the map has
    // loaded, the latest list is kept and drawn on load.
    function setEvents(events) {
      if (!loaded) {
        pendingEvents = events;
        return;
      }
      eventMarkers.forEach(function (entry) { entry.marker.remove(); });
      eventMarkers = [];
      (events || []).forEach(function (event) {
        var marker = eventMarker(event);
        if (marker) eventMarkers.push({ id: event.id, marker: marker.addTo(map) });
      });
    }

    // "Search this area" (#35): a circle around the map centre whose radius
    // follows the zoom. Dashed while it is only a preview, solid once searched.
    var MILES_PER_DEGREE = 69.0;
    var area = null;  // { lat, lng, radius, preview }

    function circlePolygon(lat, lng, radius) {
      var points = [];
      var latStep = radius / MILES_PER_DEGREE;
      var lngStep = radius / (MILES_PER_DEGREE * Math.cos(lat * Math.PI / 180));
      for (var i = 0; i <= 64; i++) {
        var angle = (i / 64) * 2 * Math.PI;
        points.push([lng + lngStep * Math.cos(angle), lat + latStep * Math.sin(angle)]);
      }
      return points;
    }

    function drawArea() {
      var data = { type: "FeatureCollection", features: [] };
      if (area) {
        data.features.push({
          type: "Feature",
          properties: { preview: Boolean(area.preview) },
          geometry: { type: "Polygon", coordinates: [circlePolygon(area.lat, area.lng, area.radius)] },
        });
      }
      var source = map.getSource("search-area");
      if (source) {
        source.setData(data);
        return;
      }
      map.addSource("search-area", { type: "geojson", data: data });
      map.addLayer({
        id: "search-area-fill", type: "fill", source: "search-area",
        paint: {
          "fill-color": "#4da3ff",
          "fill-opacity": ["case", ["get", "preview"], 0.06, 0.12],
        },
      });
      map.addLayer({
        id: "search-area-preview", type: "line", source: "search-area",
        filter: ["==", ["get", "preview"], true],
        paint: { "line-color": "#1f6fd1", "line-width": 2, "line-dasharray": [3, 2] },
      });
      map.addLayer({
        id: "search-area-line", type: "line", source: "search-area",
        filter: ["==", ["get", "preview"], false],
        paint: { "line-color": "#1f6fd1", "line-width": 2.5 },
      });
    }

    function setArea(value) {
      area = value;
      if (loaded) drawArea();
    }

    // Circle for the current view: 80% of the distance from the centre to the
    // nearest edge, so it always fits on screen; 0.1 to 10 miles.
    function viewCircle() {
      var center = map.getCenter();
      var bounds = map.getBounds();
      var halfHeight = (bounds.getNorth() - bounds.getSouth()) / 2 * MILES_PER_DEGREE;
      var halfWidth = (bounds.getEast() - bounds.getWest()) / 2 * MILES_PER_DEGREE *
        Math.cos(center.lat * Math.PI / 180);
      var radius = Math.min(10, Math.max(0.1, 0.8 * Math.min(halfHeight, halfWidth)));
      return { lat: center.lat, lng: center.lng, radius: Math.round(radius * 10) / 10 };
    }

    window.eventMap = {
      setEvents: setEvents,
      setArea: setArea,
      viewCircle: viewCircle,
      // Call after the map container changes size (search panel, #34).
      resize: function () { map.resize(); },
      // Centres the map on an event's pin.
      focusEvent: function (id) {
        var entry = eventMarkers.filter(function (item) { return item.id === id; })[0];
        if (!entry) return;
        map.flyTo({ center: entry.marker.getLngLat(), zoom: Math.min(map.getMaxZoom(), Math.max(map.getZoom(), 15)) });
      },
      onEventClick: function (callback) { eventClickHandler = callback; },
      // Calls back when the user (not code) starts to pan or zoom the map.
      onUserMoveStart: function (callback) {
        map.on("movestart", function (event) {
          if (event && event.originalEvent) callback();
        });
      },
      // Calls back after the user (not code) pans or zooms the map.
      onUserMove: function (callback) {
        map.on("moveend", function (event) {
          if (event && event.originalEvent) callback();
        });
      },
    };

    map.on("load", function () {
      loaded = true;
      setEvents(pendingEvents || config.events);
      if (area) drawArea();
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
