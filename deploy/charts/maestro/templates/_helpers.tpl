{{/*
Shared snippets. Every first-party service gets the same env block (docs/contracts.md).
*/}}

{{- define "maestro.issuer" -}}
http://{{ .Values.hostIp }}:{{ .Values.ports.keycloak }}/realms/maestro
{{- end -}}

{{- define "maestro.keycloakInternal" -}}
http://keycloak.maestro-identity:8080/realms/maestro
{{- end -}}

{{- define "maestro.jwksUrl" -}}
{{ include "maestro.keycloakInternal" . }}/protocol/openid-connect/certs
{{- end -}}

{{- define "maestro.tokenUrl" -}}
{{ include "maestro.keycloakInternal" . }}/protocol/openid-connect/token
{{- end -}}

{{- define "maestro.publicUrl" -}}
http://{{ .root.Values.hostIp }}:{{ .port }}
{{- end -}}

{{/* Common env for every first-party Python service. Usage: {{ include "maestro.commonEnv" (dict "root" . "service" "cache-agent" "audience" "cache-agent,maestro-gateway") | nindent 12 }}
     `audience` (optional) is the comma-separated list of `aud` values the service accepts (ADR-0015); default: the gateway audience only. */}}
{{- define "maestro.commonEnv" -}}
- name: SERVICE_NAME
  value: {{ .service | quote }}
- name: LOG_LEVEL
  value: info
- name: FLEET_EVENTS_URL
  value: http://fleet-console.maestro:8080/api/events
- name: PROMETHEUS_URL
  value: {{ .root.Values.monitoring.prometheusUrl | quote }}
- name: GRAFANA_PUBLIC_URL
  value: {{ include "maestro.publicUrl" (dict "root" .root "port" .root.Values.ports.grafana) | quote }}
- name: OIDC_ISSUER
  value: {{ include "maestro.issuer" .root | quote }}
- name: OIDC_JWKS_URL
  value: {{ include "maestro.jwksUrl" .root | quote }}
- name: OIDC_TOKEN_URL
  value: {{ include "maestro.tokenUrl" .root | quote }}
- name: OIDC_AUDIENCE
  value: {{ .audience | default "maestro-gateway" | quote }}
- name: SKILLS_DIR
  value: /app/skills
- name: PUBLIC_GRAFANA_URL
  value: {{ include "maestro.publicUrl" (dict "root" .root "port" .root.Values.ports.grafana) | quote }}
- name: PUBLIC_PROMETHEUS_URL
  value: {{ include "maestro.publicUrl" (dict "root" .root "port" .root.Values.ports.prometheus) | quote }}
- name: PUBLIC_KEYCLOAK_URL
  value: {{ include "maestro.publicUrl" (dict "root" .root "port" .root.Values.ports.keycloak) | quote }}
- name: PUBLIC_GATEWAY_URL
  value: {{ include "maestro.publicUrl" (dict "root" .root "port" .root.Values.ports.fleetGateway) | quote }}
- name: PUBLIC_EDGE_URL
  value: {{ include "maestro.publicUrl" (dict "root" .root "port" .root.Values.ports.edgeGateway) | quote }}
- name: PUBLIC_CONSOLE_URL
  value: {{ include "maestro.publicUrl" (dict "root" .root "port" .root.Values.ports.fleetConsole) | quote }}
{{- end -}}

{{/* LLM env. Usage: include "maestro.llmEnv" (dict "root" . "model" ... "effort" ...) */}}
{{- define "maestro.llmEnv" -}}
- name: LLM_MODEL
  value: {{ .model | quote }}
- name: LLM_EFFORT
  value: {{ .effort | quote }}
- name: LLM_FALLBACKS
  value: {{ .root.Values.llm.fallbacks | quote }}
- name: LLM_MAX_TURNS
  value: {{ .root.Values.llm.maxTurns | quote }}
- name: ANTHROPIC_API_KEY
  valueFrom:
    secretKeyRef:
      name: anthropic
      key: ANTHROPIC_API_KEY
{{- end -}}

{{/* Standard probes for a Python service exposing /healthz on its port */}}
{{- define "maestro.httpProbes" -}}
readinessProbe:
  httpGet: { path: /healthz, port: {{ . }} }
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 5
livenessProbe:
  httpGet: { path: /healthz, port: {{ . }} }
  initialDelaySeconds: 30
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 5
{{- end -}}

{{/*
A domain agent Deployment + Service + ServiceMonitor.
Usage: include "maestro.domainAgent" (dict "root" . "name" "cache-agent" "namespace" "domain-cache" "domain" "cache" "skills" "cache-observability,prometheus-observability" "extraEnv" (list (dict "name" "VALKEY_URL" "value" "...")) "serviceAccount" "")
*/}}
{{- define "maestro.domainAgent" -}}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .name }}
  namespace: {{ .namespace }}
  labels: { app: {{ .name }}, maestro.io/role: domain-agent, maestro.io/domain: {{ .domain }} }
spec:
  replicas: 1
  selector:
    matchLabels: { app: {{ .name }} }
  template:
    metadata:
      labels: { app: {{ .name }}, maestro.io/role: domain-agent, maestro.io/domain: {{ .domain }} }
      annotations:
        # Roll the pod when the Anthropic key changes (the Secret is read only at container start).
        checksum/anthropic: {{ .root.Values.anthropicApiKey | sha256sum }}
    spec:
      {{- if .serviceAccount }}
      serviceAccountName: {{ .serviceAccount }}
      {{- end }}
      containers:
        - name: agent
          image: "{{ .root.Values.images.domainAgent.repository }}:{{ .root.Values.images.domainAgent.tag }}"
          imagePullPolicy: {{ .root.Values.images.pullPolicy }}
          ports:
            - { name: http, containerPort: 8000 }
          env:
            - name: AGENT_DOMAIN
              value: {{ .domain | quote }}
            - name: AGENT_SKILLS
              value: {{ .skills | quote }}
            {{- range .extraEnv }}
            - name: {{ .name }}
              value: {{ .value | quote }}
            {{- end }}
            {{- /* A domain agent accepts on-behalf-of tokens addressed to it (aud == its own client id, ADR-0015)
                   and direct callers' tokens addressed to the gateway (ADR-0005). */}}
            {{- include "maestro.commonEnv" (dict "root" .root "service" .name "audience" (printf "%s,maestro-gateway" .name)) | nindent 12 }}
            {{- include "maestro.llmEnv" (dict "root" .root "model" .root.Values.llm.agentModel "effort" .root.Values.llm.agentEffort) | nindent 12 }}
          {{- include "maestro.httpProbes" 8000 | nindent 10 }}
          resources: {{ toYaml .root.Values.resources.agent | nindent 12 }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ .name }}
  namespace: {{ .namespace }}
  labels: { app: {{ .name }}, maestro.io/role: domain-agent }
spec:
  selector: { app: {{ .name }} }
  ports:
    - { name: http, port: 8000, targetPort: http }
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ .name }}
  namespace: {{ .namespace }}
  labels: { app: {{ .name }} }
spec:
  selector:
    matchLabels: { app: {{ .name }} }
  endpoints:
    - port: http
      path: /metrics
      interval: 15s
{{- end -}}
