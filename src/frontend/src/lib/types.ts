// Shared response shapes. Kept intentionally loose (many optional fields)
// because the backend's engine payloads are additive and explanatory rather
// than a rigid contract - see docs/architecture.md.

export type Role = "CITIZEN" | "OFFICER" | "FIELD_WORKER" | "ADMIN";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  language: string;
  jurisdiction_id: number | null;
}

export interface Category {
  code: string;
  name_en: string;
  name_kn: string;
  base_severity: number;
  safety_impact: number;
  sla_target_hours: number;
}

export interface SlaState {
  target_hours: number;
  elapsed_hours: number;
  remaining_hours: number;
  due_at: string;
  breached: boolean;
  breach_probability: number;
  breach_risk: "MET" | "BREACHED" | "HIGH" | "MODERATE" | "LOW";
  predicted_breach_at: string | null;
  note?: string;
}

export interface ComplaintSummary {
  id: number;
  public_id: string;
  title: string;
  category: { code: string; name_en: string; name_kn: string };
  status: string;
  verification_status: string;
  priority_level: string;
  priority_score: number;
  risk_level: string;
  risk_score: number;
  age_hours: number;
  ward: number | null;
  authority: string | null;
  jurisdiction_name: string | null;
  created_at: string;
  last_action_at: string;
  sla: SlaState;
  is_synthetic: boolean;
  assigned: boolean;
  latitude?: number;
  longitude?: number;
  description?: string;
  landmark?: string | null;
  citizen_id?: number | null;
  approximate_location?: boolean;
}

export interface Factor {
  code: string;
  label: string;
  points: number;
  max_points: number;
  detail: string;
}

export interface RiskExplanation {
  risk_score: number;
  risk_level: string;
  risk_factors: Factor[];
  recommended_action: string;
  model_version: string;
}

export interface PriorityExplanation {
  priority_score: number;
  priority_level: string;
  priority_factors: Factor[];
  model_version: string;
}

export interface VerificationFactor {
  code: string;
  label: string;
  verdict: "PASS" | "WARN" | "FAIL";
  score_delta: number;
  detail: string;
}

export interface TimelineEvent {
  id: number;
  event_type: string;
  note: string;
  from_status: string | null;
  to_status: string | null;
  actor: string;
  payload: Record<string, unknown> | null;
  at: string;
}

export interface DuplicateMatch {
  complaint_id: number;
  public_id: string;
  title: string;
  status: string;
  distance_m: number;
  text_similarity_pct: number;
  hours_apart: number;
  similarity_pct: number;
  reason: string;
}

export interface ComplaintDetail extends ComplaintSummary {
  verification: {
    verification_status: string;
    verification_factors: VerificationFactor[];
    disclaimer: string;
  };
  risk_explanation: RiskExplanation | null;
  priority_explanation: PriorityExplanation | null;
  jurisdiction: {
    authority: string | null;
    ward: number | null;
    boundary_version: string | null;
    effective_from: string | null;
    confidence_pct: number;
    reason: string | null;
    note: string;
  };
  duplicates: { complaint_id: number; public_id: string | null; similarity_pct: number;
    distance_m: number; decision: string }[];
  evidence: {
    id: number;
    filename: string;
    sha256: string;
    size_bytes: number;
    stage: string;
    url?: string;
    created_at: string;
  }[];
  timeline: TimelineEvent[];
  followups: { id: number; message: string; kind: string; at: string }[];
}

export interface DashboardOverview {
  total_complaints: number;
  open_complaints: number;
  resolved_complaints: number;
  resolution_rate_pct: number;
  avg_resolution_hours: number | null;
  high_risk_open: number;
  sla_breached_open: number;
  stagnant_complaints: number;
  complaints_last_n_days: number;
  window_days: number;
  by_category: { code: string; name_en: string; name_kn: string; count: number }[];
  by_status: { status: string; count: number }[];
  disclaimer: string;
}

export interface WardSummary {
  jurisdiction_id: number;
  authority: string;
  ward: number | null;
  name: string;
  total: number;
  open: number;
  resolved: number;
  high_risk: number;
  avg_resolution_hours: number | null;
  resolution_rate_pct: number;
}

export interface WardExplain {
  jurisdiction: { id: number; authority: string; ward: number | null; name: string };
  open_complaints: number;
  unassigned: number;
  high_risk: number;
  sla_breached: number;
  ward_avg_resolution_hours: number | null;
  city_avg_resolution_hours: number | null;
  reasons: { code: string; text: string; metric: number; action: string }[];
  disclaimer: string;
}

export interface MapMarker {
  public_id: string;
  lat: number;
  lng: number;
  category: string;
  category_name: string;
  status: string;
  priority_level: string;
  risk_score: number;
  risk_level: string;
  age_hours: number;
  jurisdiction: string | null;
  jurisdiction_id?: number | null;
  ward?: number | null;
}

export interface FieldTask {
  task_id: number;
  state: string;
  public_id: string;
  title: string;
  description: string;
  category: string;
  category_kn: string;
  landmark: string | null;
  latitude: number;
  longitude: number;
  priority_level: string;
  risk_score: number;
  status: string;
  sla: SlaState;
  assigned_at: string;
  started_at: string | null;
}

export interface JurisdictionVersion {
  id: number;
  jurisdiction_id: number;
  authority: string;
  ward: number | null;
  name: string;
  version_label: string;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
  boundary: number[][];
  source_note: string;
}

export interface SurgeStatus {
  run_id: number;
  label: string;
  state: string;
  incoming_reports: number;
  processed: number;
  queued: number;
  duplicates_detected: number;
  high_priority: number;
  avg_processing_latency_ms: number;
  throughput_per_sec: number | null;
  elapsed_seconds: number;
  note: string;
}
