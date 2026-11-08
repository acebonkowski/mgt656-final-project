(() => {
  const form = document.getElementById('onboarding-form');
  const name = document.getElementById('id_display_name');
  const school = document.getElementById('id_school');
  const program = document.getElementById('id_program');
  const button = document.getElementById('start-discovering');
  const programs = JSON.parse(document.getElementById('program-options').textContent);

  function updateButton() {
    button.disabled = !name.value.trim() || !school.value || !program.value || !form.checkValidity();
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
})();
