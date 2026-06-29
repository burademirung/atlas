{{/*
============================================================================
Atlas chart helpers
============================================================================
*/}}

{{/* Base chart name, optionally overridden. */}}
{{- define "atlas.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully-qualified release name (<= 63 chars, DNS-safe). */}}
{{- define "atlas.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* chart label value: name-version. */}}
{{- define "atlas.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels shared by every object. */}}
{{- define "atlas.labels" -}}
helm.sh/chart: {{ include "atlas.chart" . }}
{{ include "atlas.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: atlas
{{- end -}}

{{/* Selector labels — stable across upgrades; never include version here. */}}
{{- define "atlas.selectorLabels" -}}
app.kubernetes.io/name: {{ include "atlas.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* ---- API component labels ---- */}}
{{- define "atlas.api.fullname" -}}
{{- printf "%s-api" (include "atlas.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "atlas.api.labels" -}}
{{ include "atlas.labels" . }}
app.kubernetes.io/component: api
{{- end -}}

{{- define "atlas.api.selectorLabels" -}}
{{ include "atlas.selectorLabels" . }}
app.kubernetes.io/component: api
{{- end -}}

{{/* ---- Worker component labels ---- */}}
{{- define "atlas.worker.fullname" -}}
{{- printf "%s-worker" (include "atlas.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "atlas.worker.labels" -}}
{{ include "atlas.labels" . }}
app.kubernetes.io/component: worker
{{- end -}}

{{- define "atlas.worker.selectorLabels" -}}
{{ include "atlas.selectorLabels" . }}
app.kubernetes.io/component: worker
{{- end -}}

{{/* Names of shared config/secret objects (referenced by envFrom). */}}
{{- define "atlas.configMapName" -}}
{{- printf "%s-config" (include "atlas.fullname" .) -}}
{{- end -}}

{{- define "atlas.secretName" -}}
{{- .Values.externalSecrets.targetSecretName | default (printf "%s-secrets" (include "atlas.fullname" .)) -}}
{{- end -}}

{{/*
Build a fully-qualified image reference.
Usage: include "atlas.image" (dict "root" . "repo" .Values.api.image.repository "tag" .Values.api.image.tag)
A tag beginning with "sha256:" is treated as an immutable digest (repo@sha256:...).
*/}}
{{- define "atlas.image" -}}
{{- $registry := .root.Values.image.registry -}}
{{- $repo := .repo -}}
{{- $tag := .tag | default .root.Chart.AppVersion -}}
{{- $base := $repo -}}
{{- if $registry -}}
{{- $base = printf "%s/%s" $registry $repo -}}
{{- end -}}
{{- if hasPrefix "sha256:" $tag -}}
{{- printf "%s@%s" $base $tag -}}
{{- else -}}
{{- printf "%s:%s" $base $tag -}}
{{- end -}}
{{- end -}}

{{/* Render imagePullSecrets if any are configured. */}}
{{- define "atlas.imagePullSecrets" -}}
{{- with .Values.image.pullSecrets }}
imagePullSecrets:
{{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}
