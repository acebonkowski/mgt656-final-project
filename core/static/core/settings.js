(() => {
  const form = document.getElementById('photo-form');
  if (!form) return;
  const input = document.getElementById('photo-file');
  const save = document.getElementById('photo-save');
  const status = document.getElementById('photo-status');
  const photo = document.getElementById('settings-photo');

  function report(message, error = false) {
    status.textContent = message;
    status.classList.toggle('error', error);
  }

  // Keep the header avatar in step with the new picture, no reload needed.
  function updateHeader(url) {
    const avatar = document.querySelector('#profile-menu .profile-avatar');
    if (!avatar) return;
    let img = document.getElementById('profile-menu-photo');
    if (!url) { if (img) img.remove(); return; }
    if (!img) {
      img = document.createElement('img');
      img.id = 'profile-menu-photo';
      img.alt = '';
      img.width = img.height = 40;
      avatar.appendChild(img);
    }
    img.src = url;
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const file = input.files[0];
    if (!file) return report('Choose a JPEG or PNG photo.', true);
    if (file.size > 5 * 1024 * 1024 || !['image/jpeg', 'image/png'].includes(file.type)) {
      return report('Choose a JPEG or PNG photo no larger than 5 MB.', true);
    }
    save.disabled = true;
    report('Saving picture…');
    try {
      const response = await fetch(form.action, {
        method: 'POST', credentials: 'same-origin', body: new FormData(form),
      });
      if (!response.headers.get('content-type')?.includes('application/json')) {
        throw new Error('The photo could not be saved. Please refresh the page and try again.');
      }
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'The photo could not be saved.');
      photo.src = result.url;
      photo.alt = 'Your profile picture';
      updateHeader(result.url);
      input.value = '';
      report('Picture saved.');
    } catch (error) {
      report(error.message || 'The photo could not be saved. Please try again.', true);
    } finally {
      save.disabled = false;
    }
  });
})();
