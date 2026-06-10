export type UserRole = 'admin' | 'recruiter' | 'hr_manager' | 'viewer';

export interface UserResponse {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_verified: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface Education {
  institution: string;
  degree?: string;
  year?: number;
}

export interface WorkExperience {
  company?: string;
  role?: string;
  start_date?: string;
  end_date?: string;
  achievements: string[];
  description?: string;
}

export interface CandidateData {
  name?: string;
  email?: string;
  phone?: string;
  skills: string[];
  years_experience?: number;
  education: Education[];
  work_experiences: WorkExperience[];
  location?: string;
  seniority?: string;
  summary?: string;
  desired_position?: string;
  certifications: string[];
  languages: string[];
  linkedin_url?: string;
  github_url?: string;
  desired_salary?: number;
  photo_url?: string | null;
}

export interface CandidateResponse extends CandidateData {
  id: string;
  file_id: string;
  status: string;
  current_resume_version?: number | null;
  created_at: string;
  deleted_at?: string;
}

export interface CreateCandidateRequest extends CandidateData {
  file_id: string;
}

export interface FileUploadResponse {
  file_id: string;
}

export interface JobResponse {
  id: string;
  title: string;
  description: string | null;
  required_skills: string[];
  required_technical_skills: string[];
  required_soft_skills: string[];
  required_seniority: string | null;
  location: string | null;
  decision_tags: Record<string, unknown> | null;
  threshold_score: number | null;
  candidates_for_next_stage: number | null;
  created_at: string;
  deleted_at: string | null;
}

export interface CreateJobRequest {
  title: string;
  description?: string;
  required_skills?: string[];
  required_seniority?: string;
  location?: string;
  threshold_score?: number;
  candidates_for_next_stage?: number;
}

export interface UpdateJobRequest {
  title?: string;
  description?: string;
  required_skills?: string[];
  required_technical_skills?: string[];
  required_soft_skills?: string[];
  required_seniority?: string;
  location?: string;
  decision_tags?: Record<string, unknown>;
  threshold_score?: number;
  candidates_for_next_stage?: number;
}

export const APPLICATION_STATUSES = [
  'parsing',
  'parse_failed',
  'applied',
  'reviewing',
  'shortlisted',
  'screening',
  'interview',
  'offer',
  'hired',
  'rejected',
  'withdrawn',
] as const;

export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

export const USER_SETTABLE_STATUSES = [
  'applied',
  'reviewing',
  'shortlisted',
  'interview',
  'offer',
  'hired',
  'rejected',
  'withdrawn',
] as const;

export type UserSettableStatus = (typeof USER_SETTABLE_STATUSES)[number];

export interface JobApplication {
  id: string;
  job_id: string;
  candidate_id: string | null;
  status: ApplicationStatus;
  resume_file_id: string;
  error_message?: string | null;
  source?: string | null;
  applied_at: string;
  updated_at: string;
  overall_score_10: number | null;
  scored_at: string | null;
  interview_scheduled_at: string | null;
  interview_location: string | null;
  candidate: CandidateResponse | null;
}

export interface CandidateApplicationSummary {
  id: string;
  job_id: string;
  job_title: string | null;
  status: string;
  interview_scheduled_at: string | null;
  interview_location: string | null;
  applied_at: string;
}

export interface SkillScore {
  name: string;
  score: number;
}

export interface SkillBreakdown {
  technical: SkillScore[];
  soft: SkillScore[];
}

export interface ComparisonResultResponse {
  id: string;
  candidate_id: string;
  overall_score: number | null;
  overall_score_10: number | null;
  dimension_scores: {
    skills_match?: number;
    experience_level?: number;
    education?: number;
    seniority_fit?: number;
  };
  reasoning: string | null;
  rank: number | null;
  skill_breakdown: SkillBreakdown | null;
  created_at: string;
}

export interface ComparisonVerdict {
  recommended_candidate_id: string;
  decision: 'strong' | 'moderate' | 'weak';
  decision_tags: string[];
  hire_verdicts: Record<string, 'hire' | 'consider' | 'reject'>;
  summary: string;
}

export interface ComparisonResponse {
  id: string;
  job_id: string;
  status: string;
  head_to_head_analysis: string | null;
  verdict: ComparisonVerdict | null;
  results: ComparisonResultResponse[];
  created_at: string;
  completed_at: string | null;
}

export interface HeadToHeadResponse {
  analysis: string;
  verdict: ComparisonVerdict | null;
}

export interface LeaderboardEntry {
  rank: number;
  candidate_id: string;
  candidate_name: string | null;
  candidate_email: string | null;
  candidate_seniority: string | null;
  overall_score: number | null;
  overall_score_10: number | null;
  dimension_scores: Record<string, number>;
  skill_breakdown: SkillBreakdown | null;
  reasoning: string | null;
  model_tag: string | null;
  scored_at: string | null;
  updated_at: string | null;
}

export type Tier = 'S' | 'A' | 'B' | 'F';

export interface ShortlistEntry extends LeaderboardEntry {
  tier: Tier | null;
}

export interface ShortlistResponse {
  mode: 'tiered' | 'qualified_only';
  target: number | null;
  threshold: number;
  cut_rating: number | null;
  scored_count: number;
  applicant_count: number;
  latest_scored_at: string | null;
  entries: ShortlistEntry[];
}

export interface JobAnalyticsSummary {
  total_applications: number;
  scored_count: number;
}

export const EVALUATION_STAGES = [
  'reviewing',
  'shortlisted',
  'interview',
  'offer',
  'hired',
  'rejected',
] as const;

export type EvaluationStage = (typeof EVALUATION_STAGES)[number];

export interface EvaluationResponse {
  id: string;
  candidate_id: string;
  job_id: string;
  evaluator_id: string;
  evaluator_name: string | null;
  stage: EvaluationStage | string;
  overall_rating: number | null;
  technical_score: number | null;
  communication_score: number | null;
  leadership_score: number | null;
  cultural_fit_score: number | null;
  english_score: number | null;
  domain_score: number | null;
  feedback: string | null;
  ai_suggested_rating: number | null;
  created_at: string;
  updated_at: string;
}

export interface CreateEvaluationRequest {
  job_id: string;
  stage: EvaluationStage;
  overall_rating?: number | null;
  technical_score?: number | null;
  communication_score?: number | null;
  leadership_score?: number | null;
  cultural_fit_score?: number | null;
  english_score?: number | null;
  domain_score?: number | null;
  feedback?: string | null;
}

export interface NoteResponse {
  id: string;
  candidate_id: string;
  author_id: string;
  text: string;
  created_at: string;
  updated_at: string;
}

export interface SkillCount {
  skill: string;
  count: number;
}

export interface AnalyticsOverview {
  total_candidates: number;
  active_candidates: number;
  total_jobs: number;
  total_applications: number;
  applications_by_status: Record<string, number>;
  top_skills: SkillCount[];
}

export interface FunnelStage {
  stage: string;
  count: number;
  conversion_rate: number | null;
}

export interface FunnelResponse {
  stages: FunnelStage[];
}

export interface JobTimeToHire {
  job_id: string;
  job_title: string | null;
  hired_count: number;
  avg_days_to_hire: number | null;
}

export interface TimeToHireResponse {
  overall_avg_days: number | null;
  total_hired: number;
  per_job: JobTimeToHire[];
}

export interface CandidateSourceItem {
  source: string;
  count: number;
}

export interface CandidateSourcesResponse {
  data: CandidateSourceItem[];
}

export interface CandidateSearchFilters {
  q?: string;
  skills?: string[];
  seniority?: string;
  status?: string;
  location?: string;
  years_min?: number;
  years_max?: number;
  page?: number;
  size?: number;
}

export interface CandidateListResponse {
  items: CandidateResponse[];
  total: number;
  page: number;
  size: number;
  pages: number;
}


export type NotificationType = 'new_application' | 'stage_change' | 'rating_update' | 'mention';

export interface Notification {
  id: string;
  user_id: string;
  type: NotificationType | string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: Notification[];
  unread_count: number;
}

export interface UserAdminResponse {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

export interface UpdateRoleRequest {
  role: UserRole;
}

export interface UpdateActiveRequest {
  is_active: boolean;
}

export interface InviteRequest {
  email: string;
  role: UserRole;
}

export interface InviteResponse {
  id: string;
  email: string;
  role: UserRole;
  expires_at: string;
  created_at: string;
}

export interface AuditLogEntry {
  id: string;
  user_id: string | null;
  method: string;
  path: string;
  status_code: number;
  ip: string | null;
  user_agent: string | null;
  request_id: string;
  created_at: string;
}

export interface BusinessEventEntry {
  id: string;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  request_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  meta: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditLogParams {
  user_id?: string;
  method?: string;
  path_contains?: string;
  from_dt?: string;
  to_dt?: string;
  limit?: number;
  offset?: number;
}

export interface BusinessEventParams {
  actor_id?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  request_id?: string;
  from_dt?: string;
  to_dt?: string;
  limit?: number;
  offset?: number;
}

export interface GenerateDescriptionRequest {
  title: string;
  seniority: string;
  required_skills?: string[];
  notes?: string;
}

export interface GenerateDescriptionResponse {
  summary: string;
  responsibilities: string[];
  requirements: string[];
}
