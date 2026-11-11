(() => {
  const form = document.getElementById('onboarding-form');
  const name = document.getElementById('id_display_name');
  const school = document.getElementById('id_school');
  const program = document.getElementById('id_program');
  const button = document.getElementById('start-discovering');
  const programs = JSON.parse(document.getElementById('program-options').textContent);
  let photoBusy = false;

  function updateButton() {
    button.disabled = photoBusy || !name.value.trim() || !school.value || !program.value || !form.checkValidity();
  }

  function showError(field) {
    const missing = !field.value.trim();
    const error = document.getElementById(`${field.name}-errors`);
    error.textContent = missing ? 'This field is required.' : '';
    field.setAttribute('aria-invalid', String(missing));
  }

  school.addEventListener('change', () => {
    program.replaceChildren(new Option('Choose your program', ''));
    programs.filter(item => String(item.school_id) === school.value).forEach(item => {
      program.add(new Option(item.name, item.id));
    });
    program.disabled = !school.value;
    document.getElementById('program-errors').textContent = '';
    program.removeAttribute('aria-invalid');
    updateButton();
  });
  [name, school, program].forEach(field => {
    field.addEventListener('blur', () => showError(field));
    field.addEventListener('input', () => {
      if (field.getAttribute('aria-invalid') === 'true') showError(field);
      updateButton();
    });
    field.addEventListener('change', updateButton);
  });
  form.addEventListener('submit', event => {
    updateButton();
    if (button.disabled) {
      event.preventDefault();
      [name, school, program].forEach(showError);
    }
  });
  program.disabled = !school.value;
  updateButton();

  const photoInput = document.getElementById('photo-file');
  const choosePhoto = document.getElementById('choose-photo');
  const removePhoto = document.getElementById('remove-photo');
  const picture = document.getElementById('profile-picture');
  const photoStatus = document.getElementById('photo-status');
  document.getElementById('photo-controls').hidden = false;
  function reportPhoto(message, error = false) {
    photoStatus.textContent = message;
    photoStatus.classList.toggle('error', error);
  }
  picture.addEventListener('error', () => {
    if (picture.getAttribute('src') !== picture.dataset.default) {
      picture.src = picture.dataset.default;
      reportPhoto('Your saved photo could not be loaded. You can still continue.', true);
    }
  });
  async function changePhoto(action, file) {
    if (photoBusy) return;
    if (file && (file.size > 5 * 1024 * 1024 || !['image/jpeg', 'image/png'].includes(file.type))) {
      reportPhoto('Choose a JPEG or PNG photo no larger than 5 MB.', true);
      return;
    }
    photoBusy = true;
    choosePhoto.disabled = removePhoto.disabled = true;
    updateButton();
    reportPhoto(action === 'remove' ? 'Removing picture…' : 'Saving picture…');
    const data = new FormData();
    data.append('action', action);
    if (file) data.append('photo', file);
    try {
      const response = await fetch(form.dataset.photoUrl, {
        method: 'POST', credentials: 'same-origin', body: data,
        headers: { 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value }
      });
      if (response.redirected) throw new Error('Please sign in again before changing your photo.');
      if (!response.headers.get('content-type')?.includes('application/json')) {
        throw new Error('The photo could not be saved. Please refresh the page and try again.');
      }
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'The photo could not be saved.');
      picture.src = result.has_photo ? result.url : picture.dataset.default;
      picture.alt = result.has_photo ? 'Your profile picture' : 'Default Bulldog profile picture';
      choosePhoto.textContent = result.has_photo ? 'Edit picture' : 'Add a picture';
      removePhoto.hidden = !result.has_photo;
      reportPhoto(result.has_photo ? 'Picture saved.' : 'Picture removed. The Bulldog is your profile picture again.');
      if (!result.has_photo) choosePhoto.focus();
    } catch (error) {
      reportPhoto(error.message || 'The photo could not be saved. Please try again.', true);
    } finally {
      photoBusy = false;
      choosePhoto.disabled = removePhoto.disabled = false;
      photoInput.value = '';
      updateButton();
    }
  }
  choosePhoto.addEventListener('click', () => {
    photoInput.value = '';
    photoInput.click();
  });
  photoInput.addEventListener('change', () => {
    if (photoInput.files[0]) changePhoto('upload', photoInput.files[0]);
  });
  removePhoto.addEventListener('click', () => changePhoto('remove'));
})();
