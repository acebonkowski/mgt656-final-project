// Share button on the event page (#32): native share sheet where supported,
// otherwise copy the public link, otherwise show it for manual copying.
(() => {
  const button = document.getElementById('share-event');
  const status = document.getElementById('share-status');
  const fallback = document.getElementById('share-fallback');
  if (!button || !status) return;

  const url = button.dataset.shareUrl;
  const title = button.dataset.shareTitle || document.title;
  let clearTimer;

  function confirm(message) {
    status.textContent = message;
    clearTimeout(clearTimer);
    clearTimer = setTimeout(() => { status.textContent = ''; }, 4000);
  }

  function showFallback() {
    if (!fallback) return;
    fallback.hidden = false;
    const input = fallback.querySelector('input');
    input.focus();
    input.select();
    confirm('Copy the link above to share it.');
  }

  async function copy() {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(url);
        confirm('Link copied');
        return;
      } catch (error) {
        // Permission denied: fall through to manual copy.
      }
    }
    showFallback();
  }

  button.addEventListener('click', async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title, url });
        confirm('Shared');
      } catch (error) {
        // The user closed the share sheet: say nothing.
        if (error && error.name === 'AbortError') return;
        await copy();
      }
      return;
    }
    await copy();
  });
})();
