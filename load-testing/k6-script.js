// k6 load test — high-rate log ingestion.
//
//   k6 run -e HOST=http://localhost:8000 load-testing/k6-script.js
//
// Ramps virtual users that each POST a 200-line batch, so a few hundred VUs
// generate a 50k+ lines/sec ingest rate. Tracks p95 request latency and RPS.

import http from "k6/http";
import { check } from "k6";

const HOST = __ENV.HOST || "http://localhost:8000";

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 100 },
        { duration: "1m", target: 300 },
        { duration: "1m", target: 300 },
        { duration: "30s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<50"],
    http_req_failed: ["rate<0.01"],
  },
};

const TEMPLATES = [
  '10.0.1.2 - - [2023-08-01T12:00:00] "GET /api/v1/users/42 HTTP/1.1" 200 512',
  "2023-08-01T12:00:00 ERROR connection to 10.0.4.7:8080 timed out after 3000ms",
  "2023-08-01T12:00:00 kernel: Out of memory: Killed process 8123 (java)",
  "2023-08-01T12:00:00 LOG: duration: 45ms statement: SELECT * FROM orders WHERE id=99",
];

function batch(n) {
  const out = [];
  for (let i = 0; i < n; i++) out.push(TEMPLATES[Math.floor(Math.random() * TEMPLATES.length)]);
  return out;
}

export default function () {
  const res = http.post(
    `${HOST}/ingest`,
    JSON.stringify({ source: "k6", lines: batch(200) }),
    { headers: { "Content-Type": "application/json" } }
  );
  check(res, { "status is 200": (r) => r.status === 200 });
}
