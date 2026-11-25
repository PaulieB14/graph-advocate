import { defineRailway, github, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const graphAdvocateRepo = github("PaulieB14/graph-advocate", {
    branch: "main",
    checkSuites: false,
  });

  const graphAdvocateVolume = volume("graph-advocate-volume", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    region: "us-east4-eqdc4a",
    sizeMB: 500,
  });
  const outreachData = volume("outreach-data", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    region: "us-east4-eqdc4a",
    sizeMB: 5000,
  });
  const postgresVolume = volume("postgres-volume", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    region: "us-east4-eqdc4a",
    sizeMB: 5000,
  });

  const outreachCron = service("outreach-cron", {
    source: graphAdvocateRepo,
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    start: "python outreach.py",
    replicas: { "us-east4-eqdc4a": 1 },
    deploy: { cronSchedule: "0 9 * * *", restartPolicyType: "NEVER" },
    volumeMounts: { "/data": outreachData },
  });

  const graphAdvocate = service("graph-advocate", {
    source: graphAdvocateRepo,
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    // Dockerfile CMD is `python a2a_server.py`; leave start unset to match live.
    healthcheck: "/",
    replicas: { "us-east4-eqdc4a": 1 },
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 10 },
    domains: [{ domain: "graphadvocate.com", port: 8080 }],
    volumeMounts: { "/data": graphAdvocateVolume },
  });

  return project("Graph Advocate Project", {
    variables: { managed: false },
    resources: [outreachCron, graphAdvocate, graphAdvocateVolume, outreachData, postgresVolume],
  });
});
