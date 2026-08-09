// Shared API types mirroring the backend schemas.

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
}

export interface Job {
  id: string;
  organization_name: string;
  position_title: string;
  location: string;
  deadline: string | null;
  contract_type: string;
  remote_policy: string;
  status: string;
  notes: string;
  raw_jd_text: string;
  source_url: string;
  executive_summary: string;
  fit_score: number | null;
  created_at: string;
  parsed?: JDAnalysis;
}

export interface JDAnalysis {
  position: Record<string, string>;
  requirements: Requirement[];
  responsibilities: string[];
  competencies: string[];
  keywords: { term: string; classification: string }[];
  summary: string;
}

export interface RequirementMatchData {
  status: "MATCHED" | "PARTIALLY_MATCHED" | "TRANSFERABLE" | "NOT_MATCHED" | "UNKNOWN";
  confidence: number;
  explanation: string;
  match_kind: string;
  evidence: { entity_type: string; entity_id: string; evidence: string; source: string }[];
}

export interface Requirement {
  id: string;
  text: string;
  category: string;
  requirement_type: string;
  importance: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  keywords: string[];
  match?: RequirementMatchData | null;
}

export interface JobAnalysisResponse {
  job: Job;
  parsed: JDAnalysis;
  requirements: Requirement[];
}

export interface JobScore {
  overall_score: number;
  category_scores: Record<string, number>;
  weights: Record<string, number>;
  threshold: number;
  recommendation: string;
  unknown_count: number;
  strong_matches: string[];
  partial_matches: string[];
  gaps: string[];
  transferable: string[];
  risks: string[];
  advantages: string[];
  explanation: string;
}

export interface ResearchClaim {
  id: string;
  category: string;
  claim: string;
  source_url: string;
  source_type: string;
  confidence: string;
  relevance_to_job: string;
}

export interface ResearchResponse {
  organization_research: ResearchClaim[];
  hiring_context: { identified: boolean; notes: string; team_insights: string[] } | null;
  people: { id: string; name: string; role: string; confidence: string; evidence: string[] }[];
}

export interface Application {
  id: string;
  job_id: string;
  status: string;
  fit_score: number | null;
  fit_score_snapshot: number | null;
  ats_score_snapshot: number | null;
  user_approved: boolean;
  user_notes: string;
  lessons_learned: string;
  outcome: string;
  interview_status: string;
  applied_at: string | null;
  cv_id: string | null;
  cover_letter_id: string | null;
  job: { id: string; organization_name: string; position_title: string; location: string; deadline: string | null; status: string } | null;
  created_at: string;
}

export interface Strategy {
  positioning: string;
  priority_experience: string[];
  priority_skills: string[];
  keywords: string[];
  evidence_plan: { requirement: string; evidence: unknown[] }[];
  de_emphasis: string[];
  concerns: string[];
  messaging_strategy: string;
}

export interface DocumentVersion {
  id: string;
  version_number: number;
  content: CVContent | CoverLetterContent;
  rendered_text: string;
  template_key: string;
  model: string;
  prompt_version: string;
  validation_results: ValidationResults;
  ats_analysis: ATSAnalysis;
  user_edited: boolean;
  is_current: boolean;
  created_at: string;
}

export interface ValidationResults {
  schema_valid: boolean;
  evidence_valid: boolean;
  hallucination_free: boolean;
  requirement_coverage_ok: boolean;
  ats_ok: boolean;
  quality_ok: boolean;
  unsupported_claims: string[];
  uncovered_requirements: string[];
  issues: string[];
}

export interface ATSAnalysis {
  ats_score?: number;
  keyword_coverage?: number;
  covered_keywords?: string[];
  missing_keywords?: string[];
  keyword_overuse_warnings?: string[];
  formatting_risks?: string[];
  requirement_coverage?: number;
  notes?: string[];
}

export interface CVBullet {
  text: string;
  evidence_ids: string[];
}

export interface CVContent {
  headline: string;
  summary: string;
  summary_evidence_ids: string[];
  experience: {
    organization: string;
    job_title: string;
    start_date: string;
    end_date: string;
    location: string;
    bullets: CVBullet[];
  }[];
  skills: string[];
  education: { institution: string; degree: string; field_of_study: string; start_date: string; end_date: string }[];
  certifications: string[];
  languages: { language: string; proficiency: string }[];
  additional_sections: { name: string; entries: { text: string }[] }[];
}

export interface CoverLetterContent {
  subject: string;
  salutation: string;
  paragraphs: { text: string; evidence_ids: string[] }[];
  closing: string;
}

export interface AppDocument {
  id: string;
  document_type: "cv" | "cover_letter";
  title: string;
  template_key: string;
  application_id: string;
  job: { id: string; organization_name: string; position_title: string } | null;
  current_version: DocumentVersion | null;
  versions: { version_number: number; created_at: string; user_edited: boolean; is_current: boolean; model: string }[];
  created_at: string;
}

export interface Template {
  id: string;
  key: string;
  name: string;
  document_type: string;
  description: string;
  config: Record<string, unknown>;
  is_builtin: boolean;
}

export interface WorkflowRun {
  id: string;
  status: string;
  current_stage: string;
  stages: { name: string; status: string; error?: string }[];
  workflow_type: string;
}

export interface DashboardStats {
  total_applications: number;
  by_status: Record<string, number>;
  average_fit: number;
  average_ats: number;
  applications_this_month: number;
  top_opportunities: { job_id: string; organization_name: string; position_title: string; overall_score: number }[];
}

export interface AgentExecution {
  id: string;
  agent_name: string;
  prompt_name: string;
  prompt_version: string;
  model: string;
  status: string;
  duration_ms: number;
  token_usage: { prompt_tokens: number; completion_tokens: number };
  error: string;
  created_at: string;
}
