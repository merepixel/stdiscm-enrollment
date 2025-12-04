import axios from 'axios';

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_BASE ||
  '/api';
const TOKEN_KEY = 'enrollment_jwt';

const api = axios.create({
  baseURL: API_BASE,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export async function login(email, password) {
  const resp = await api.post('/auth/login', { email, password });
  return resp.data;
}

export async function getCourses() {
  const resp = await api.get('/courses');
  return resp.data;
}

export async function getAssignedCourses() {
  const resp = await api.get('/courses/assigned');
  return resp.data;
}

export async function enrollInCourse(courseId) {
  const resp = await api.post('/enrollments/', { course_id: courseId });
  return resp.data;
}

export async function dropEnrollment(enrollmentId) {
  const resp = await api.delete(`/enrollments/${enrollmentId}`);
  return resp.data;
}

export async function getMyEnrollments() {
  // Gateway exposes /api/enrollments/my
  const resp = await api.get('/enrollments/my');
  return resp.data;
}

export async function getMyGrades() {
  // Gateway exposes /api/grades/my
  const resp = await api.get('/grades/my');
  return resp.data;
}

export async function submitGrade({ student_id, course_id, term, grade }) {
  // Faculty-only endpoint forwarded by gateway to Grade service.
  const resp = await api.post('/grades/', { student_id, course_id, term, grade });
  return resp.data;
}

export async function submitGradesBulk({ course_id, term, academic_year, records }) {
  // Faculty-only endpoint for bulk grade upsert.
  const resp = await api.post('/grades/bulk', { course_id, term, academic_year, records });
  return resp.data;
}

export async function getFacultyGrades() {
  // Placeholder: if an admin listing is added, target it here. For now, reuse /grades/my.
  const resp = await api.get('/grades/my');
  return resp.data;
}

export async function getCourseRoster(courseId) {
  const resp = await api.get(`/enrollments/course/${courseId}/roster`);
  return resp.data;
}

export default api;
