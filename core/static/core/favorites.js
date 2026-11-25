// Delegation also handles details inserted into the map popup.
(function () {
  document.addEventListener("click", async function (event) {
    var button = event.target.closest("button.favorite-button");
    if (!button || button.disabled) return;
    var status = button.closest(".event-favorite").querySelector(".favorite-status");
    var wanted = button.getAttribute("aria-pressed") !== "true";
    button.disabled = true;
    status.textContent = "Saving…";
    try {
      var response = await fetch(button.dataset.favoriteUrl, {
        method: "POST", credentials: "same-origin",
        headers: { "X-CSRFToken": button.dataset.csrf, "Accept": "application/json",
          "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ favorited: String(wanted) }).toString(),
      });
      if (response.redirected) throw new Error("Please log in again to save favorites.");
      var payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Couldn't save. Try again.");
      button.setAttribute("aria-pressed", String(payload.favorited));
      button.setAttribute("aria-label", payload.favorited ? "Remove from Favorites" : "Add to Favorites");
      button.querySelector(".favorite-heart").textContent = payload.favorited ? "♥" : "♡";
      button.querySelector(".favorite-label").textContent = payload.favorited ? "Favorited" : "Favorite";
      status.textContent = payload.favorited ? "Saved to favorites" : "Removed from favorites";
    } catch (error) {
      status.textContent = error instanceof SyntaxError || error instanceof TypeError
        ? "Couldn't save. Try again." : error.message;
    } finally { button.disabled = false; }
  });
})();
