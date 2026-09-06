const state = { students: [], editingId: null, deletingId: null, searchTimer: null };
const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);
}

function initials(name) { return name.split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase(); }
function formatDate(value) { return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(`${value}Z`)); }
function showToast(message) { const toast = $('#toast'); toast.textContent = message; toast.hidden = false; setTimeout(() => { toast.hidden = true; }, 3000); }

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'Something went wrong. Please try again.');
  }
  return response.status === 204 ? null : response.json();
}

async function loadDashboard() {
  const data = await request('/api/dashboard');
  $('#totalStudents').textContent = data.total_students;
  $('#totalDepartments').textContent = data.total_departments;
  $('#databaseStatus').textContent = data.database_status;
  renderMetrics('#departmentStats', data.by_department, 'department');
  renderMetrics('#yearStats', data.by_year, 'year');
  $('#recentStudents').innerHTML = data.recent_students.map((student) => `<div class="recent-item"><span class="avatar">${escapeHtml(initials(student.full_name))}</span><div><strong>${escapeHtml(student.full_name)}</strong><small>${escapeHtml(student.department)} · Year ${student.year}</small></div></div>`).join('') || '<p class="empty-state">No records yet.</p>';
}

function renderMetrics(selector, rows, labelKey) {
  const max = Math.max(...rows.map((row) => row.count), 1);
  $(selector).innerHTML = rows.map((row) => `<div class="metric-row"><span class="metric-name">${escapeHtml(labelKey === 'year' ? `Year ${row.year}` : row.department)}</span><div class="bar-track"><div class="bar-fill" style="width:${(row.count / max) * 100}%"></div></div><span class="metric-value">${row.count}</span></div>`).join('') || '<p class="empty-state">No statistics yet.</p>';
}

async function loadStudents() {
  const search = $('#searchInput').value.trim();
  state.students = await request(`/api/students?search=${encodeURIComponent(search)}`);
  const table = $('#studentsTable');
  table.innerHTML = state.students.map((student) => `<tr><td><strong>${escapeHtml(student.full_name)}</strong><small>ID #${student.id}</small></td><td>${escapeHtml(student.email)}<small>${escapeHtml(student.phone)}</small></td><td><span class="department-tag">${escapeHtml(student.department)}</span></td><td>Year ${student.year}</td><td>${formatDate(student.created_at)}</td><td class="actions"><button class="icon-button" data-edit="${student.id}" title="Edit student">✎</button><button class="icon-button delete" data-delete="${student.id}" title="Delete student">⌫</button></td></tr>`).join('');
  $('#studentCount').textContent = `${state.students.length} ${state.students.length === 1 ? 'student' : 'students'}`;
  $('#emptyState').hidden = state.students.length !== 0;
}

function showPage(page) {
  document.querySelectorAll('.page').forEach((element) => element.classList.remove('active-page'));
  document.querySelectorAll('.nav-link').forEach((element) => element.classList.toggle('active', element.dataset.page === page));
  $(`#${page}Page`).classList.add('active-page');
  $('#pageTitle').textContent = page === 'dashboard' ? 'Dashboard' : 'Students';
  $('#sidebar').classList.remove('open');
  if (page === 'students') loadStudents().catch(handleError);
  if (page === 'dashboard') loadDashboard().catch(handleError);
}

function closeAllModals() {
  $('#studentModal').hidden = true;
  $('#deleteModal').hidden = true;
  state.editingId = null;
  state.deletingId = null;
}

function openStudentModal(student = null) {
  closeAllModals();
  state.editingId = student?.id ?? null;
  const form = $('#studentForm');
  form.reset();
  $('#formError').hidden = true;
  $('#modalTitle').textContent = student ? 'Edit student' : 'Add student';
  $('#saveStudentButton').textContent = student ? 'Save changes' : 'Save student';
  if (student) Object.entries(student).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value; });
  $('#studentModal').hidden = false;
  form.elements.full_name.focus();
}
function closeStudentModal() { $('#studentModal').hidden = true; state.editingId = null; }
function openDeleteModal(id) {
  const student = state.students.find((item) => item.id === id);
  if (!student) return;
  closeAllModals();
  state.deletingId = id;
  $('#deleteMessage').textContent = `Delete ${student.full_name}? This permanently removes their record from the local database.`;
  $('#deleteModal').hidden = false;
}
function closeDeleteModal() { $('#deleteModal').hidden = true; state.deletingId = null; }
function handleError(error) { showToast(error.message || 'Unable to complete that request.'); }

document.addEventListener('DOMContentLoaded', async () => {
  closeAllModals();
  document.querySelectorAll('.nav-link').forEach((button) => button.addEventListener('click', () => showPage(button.dataset.page)));
  document.querySelectorAll('[data-go-students]').forEach((button) => button.addEventListener('click', () => showPage('students')));
  $('#menuButton').addEventListener('click', () => $('#sidebar').classList.toggle('open'));
  $('#dashboardAddButton').addEventListener('click', () => openStudentModal());
  $('#addStudentButton').addEventListener('click', () => openStudentModal());
  document.querySelectorAll('[data-close-modal]').forEach((button) => button.addEventListener('click', closeStudentModal));
  document.querySelectorAll('[data-close-delete]').forEach((button) => button.addEventListener('click', closeDeleteModal));
  $('#studentModal').addEventListener('click', (event) => { if (event.target.id === 'studentModal') closeStudentModal(); });
  $('#deleteModal').addEventListener('click', (event) => { if (event.target.id === 'deleteModal') closeDeleteModal(); });
  $('#searchInput').addEventListener('input', () => { clearTimeout(state.searchTimer); state.searchTimer = setTimeout(() => loadStudents().catch(handleError), 250); });
  $('#studentsTable').addEventListener('click', (event) => { const edit = event.target.closest('[data-edit]'); const remove = event.target.closest('[data-delete]'); if (edit) openStudentModal(state.students.find((student) => student.id === Number(edit.dataset.edit))); if (remove) openDeleteModal(Number(remove.dataset.delete)); });
  $('#studentForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget; const payload = Object.fromEntries(new FormData(form)); payload.year = Number(payload.year);
    try { await request(state.editingId ? `/api/students/${state.editingId}` : '/api/students', { method: state.editingId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); closeStudentModal(); showToast(state.editingId ? 'Student record updated.' : 'Student added to the database.'); await Promise.all([loadStudents(), loadDashboard()]); } catch (error) { $('#formError').textContent = error.message; $('#formError').hidden = false; }
  });
  $('#confirmDeleteButton').addEventListener('click', async () => {
    if (state.deletingId === null) return;
    try { await request(`/api/students/${state.deletingId}`, { method: 'DELETE' }); closeDeleteModal(); showToast('Student record deleted.'); await Promise.all([loadStudents(), loadDashboard()]); } catch (error) { handleError(error); }
  });
  try { await Promise.all([loadDashboard(), loadStudents()]); } catch (error) { handleError(error); }
});
