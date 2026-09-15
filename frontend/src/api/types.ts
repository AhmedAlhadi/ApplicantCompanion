// Shared API types mirroring the backend schemas.

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
  is_active?: boolean;
  avatar_url?: string | null;
}

export interface AuthConfig {
  google_client_id: string;
  registration_open: boolean;
}

export interface AdminStats {
  total_users: number;
  active_users: number;
  admin_users: number;
  created_this_month: number;
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  has_password: boolean;
  google_linked: boolean;
  avatar_url: string | null;
  job_count: number;
  application_count: number;
}

export interface Job {
  id: string;
  organization_name: string;
  position_title: string;
  location: string;
  deadline: string | null;
  contract_type: string;
  remote_policy: string;
  department: string;
  team: string;
  grade_level: string;
  duration: string;
  reporting_line: string;
  status: string;
  notes: string;
  raw_jd_text: string;
  source_url: string;
  source_type: string;
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
  qualification_evaluation?: {
    status?: RequirementMatchData["status"];
    selected_path_index?: number | null;
    path_results?: {
      path_index: number;
      label: string;
      status: RequirementMatchData["status"];
    }[];
  };
}

export interface QualificationPredicate {
  kind: "degree_level" | "relevant_experience" | "education_field" | "certification" | "language" | "skill" | "domain_expertise" | "other";
  value?: string;
  minimum_level?: string;
  minimum_years?: number | null;
  terms?: string[];
}

export interface QualificationPath {
  label: string;
  predicates: QualificationPredicate[];
}

export interface Requirement {
  id: string;
  text: string;
  category: string;
  requirement_type: string;
  importance: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  keywords: string[];
  qualification_paths?: QualificationPath[];
  match?: RequirementMatchData | null;
}

export interface JobAnalysisResponse {
  job: Job;
  parsed: JDAnalysis;
  requirements: Requirement[];
}

export interface JobScore {
  overall_score: number;
  overall_score_low?: number | null;
  overall_score_high?: number | null;
  coverage?: number;
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
    experience_id?: string;
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
  error?: string;
  updated_at?: string;
}

export interface DashboardStats {
  total_applications: number;
  by_status: Record<string, number>;
  average_fit: number;
  average_ats: number;
  applications_this_month: number;
  top_opportunities: { job_id: string; organization_name: string; position_title: string; overall_score: number }[];
}

export type AppLanguage = "ar" | "en";

export interface UserSettings {
  score_threshold: number;
  scoring_weights: Record<string, number>;
  model_routing: Record<string, string>;
  ui_language: AppLanguage;
  content_language: AppLanguage;
  default_cv_template: string;
  default_cover_letter_template: string;
  ats_relevance: "high" | "low";
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

export type ReconciliationEntityType = "experience" | "project" | "achievement";
export type ReconciliationAction = "create" | "merge";

export interface ReconciliationProposal {
  proposal_id: string;
  entity_type: ReconciliationEntityType;
  action: ReconciliationAction;
  target_id: string | null;
  target_label: string;
  confidence: number;
  reasoning: string;
  payload: Record<string, unknown>;
  target_snapshot?: {
    id: string;
    label: string;
    organization?: string;
    job_title?: string;
    name?: string;
    description?: string;
    start_date?: string | null;
    end_date?: string | null;
    responsibilities?: string[];
  };
}

export interface PendingIngestion {
  id: string;
  user_id: string;
  document_id: string | null;
  status: "pending" | "completed" | "discarded";
  proposals: ReconciliationProposal[];
  auto_applied: Record<string, number>;
  summary: string;
  created_at: string;
  document?: { id: string; filename: string; doc_type: string } | null;
}

export interface IngestResult {
  document_id: string;
  pending_ingestion_id: string | null;
  auto_applied: Record<string, number>;
  proposals_count: number;
  profile?: Record<string, string>;
  created?: Record<string, number>;
  note?: string;
}

export interface OnboardingStatus {
  status: "in_progress" | "completed" | "skipped";
  has_profile: boolean;
  experience_count: number;
  pending_count: number;
  job_count: number;
  latest_job: {
    id: string;
    status: string;
    organization_name: string;
    position_title: string;
  } | null;
  latest_application: {
    id: string;
    status: string;
    job_id: string;
    fit_score: number | null;
  } | null;
  latest_score: {
    overall_score: number;
    threshold: number;
    recommendation: string;
  } | null;
  profile: {
    full_name: string;
    headline: string;
    summary: string;
    email: string;
    phone: string;
    location: string;
    links: Record<string, string>;
    primary_profession?: string;
    target_sectors?: string[];
  } | null;
}

export interface CareerNarrative {
  title?: string;
  period?: string;
  text?: string;
  narrative?: string;
}

export interface CareerProfile {
  full_name: string;
  headline: string;
  summary: string;
  email: string;
  phone: string;
  location: string;
  links: Record<string, string>;
  preferred_positioning: string;
  career_narratives: CareerNarrative[];
  primary_profession: string;
  target_sectors: string[];
}

export interface CareerExperience {
  id: string;
  organization: string;
  job_title: string;
  start_date: string | null;
  end_date: string | null;
  employment_type: string;
  location: string;
  description: string;
  responsibilities: string[];
  technologies: string[];
  domains: string[];
  leadership: string[];
  stakeholders: string[];
  verification_status: string;
  confidence: number;
}

export interface CareerProject {
  id: string;
  experience_id: string | null;
  name: string;
  description: string;
  role: string;
  technologies: string[];
  outcomes: string[];
  urls: string[];
  verification_status: string;
  confidence?: number;
}

export interface CareerAchievement {
  id: string;
  experience_id: string | null;
  project_id: string | null;
  education_id: string | null;
  title: string;
  description: string;
  quantified_result: string;
  skills: string[];
  verification_status: string;
  confidence: number;
}

export interface CareerSkill {
  id: string;
  name: string;
  canonical_name: string;
  category: string;
  proficiency: string;
  years_experience: number | null;
  synonyms: string[];
  evidence_count: number;
  verification_status: string;
}

export interface CareerEducation {
  id: string;
  institution: string;
  degree: string;
  field_of_study: string;
  start_date: string | null;
  end_date: string | null;
  verification_status: string;
}

export interface CareerCertification {
  id: string;
  name: string;
  issuer: string;
  issue_date: string | null;
  credential_type?: string;
  verification_status: string;
}

export interface KnowledgeContext {
  id: string;
  knowledge_id: string;
  experience_id: string | null;
  project_id: string | null;
  achievement_id: string | null;
  education_id: string | null;
  acquisition_mode: string;
  how_acquired: string;
  how_applied: string;
  verification_status: string;
  confidence: number;
}

export interface ProfessionalKnowledge {
  id: string;
  name: string;
  canonical_name: string;
  kind: string;
  summary: string;
  depth: string;
  years_experience: number | null;
  synonyms: string[];
  evidence_count: number;
  verification_status: string;
  confidence: number;
  contexts: KnowledgeContext[];
}

export interface CoachCitation {
  entity_type: string;
  entity_id: string;
  label: string;
  verification_status?: string;
}

export interface CoachMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: CoachCitation[];
  created_at: string | null;
  token_usage?: Record<string, number>;
}

export interface CoachConversation {
  id: string;
  title: string;
  job_id: string | null;
  application_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  messages?: CoachMessage[];
}
