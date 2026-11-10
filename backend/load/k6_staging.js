import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const apiLatency = new Trend('authenticated_api_duration', true);
const baseUrl = (__ENV.BASE_URL || '').replace(/\/$/, '');

export const options = {
  stages: [
    { duration: '2m', target: 500 },
    { duration: '10m', target: 500 },
    { duration: '1m', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    authenticated_api_duration: ['p(95)<2000'],
  },
};

export function setup() {
  if (!baseUrl || !__ENV.LOAD_TEST_EMAIL || !__ENV.LOAD_TEST_PASSWORD) {
    throw new Error('BASE_URL, LOAD_TEST_EMAIL, and LOAD_TEST_PASSWORD are required');
  }
  const login = http.post(`${baseUrl}/api/v1/auth/login`, JSON.stringify({
    email: __ENV.LOAD_TEST_EMAIL,
    password: __ENV.LOAD_TEST_PASSWORD,
  }), { headers: { 'Content-Type': 'application/json', Origin: baseUrl } });
  check(login, { 'staging athlete login succeeds': (r) => r.status === 200 });
  const token = login.json('access_token');
  if (!token) throw new Error('Login response did not contain an access token');
  return { token };
}

export default function (data) {
  const auth = { headers: { Authorization: `Bearer ${data.token}` } };
  http.get(`${baseUrl}/`, auth);
  for (const path of ['/api/v1/profile', '/api/v1/dashboard/targets']) {
    const response = http.get(`${baseUrl}${path}`, auth);
    apiLatency.add(response.timings.duration);
    check(response, { [`${path} returns successfully`]: (r) => r.status >= 200 && r.status < 300 });
  }
  sleep(10);
}
