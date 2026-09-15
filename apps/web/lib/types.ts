export type Actor = {
  id: string;
  email: string;
  name?: string | null;
  role: "OWNER" | "ADMIN" | "MANAGER" | "EMPLOYEE";
  time_zone?: string | null;
  organization: {
    id: string;
    name: string;
    slug: string;
  };
};

export type AuthSession = {
  token: string;
  actor: Actor;
};

export type PendingVerification = {
  message: string;
  email: string;
  verification_expires_at: string;
  verification_code_hint?: string | null;
};

export type DirectoryUser = {
  id: string;
  email: string;
  name?: string | null;
  time_zone?: string | null;
  role: "OWNER" | "ADMIN" | "MANAGER" | "EMPLOYEE";
  status: "ACTIVE" | "INACTIVE";
};

export type UserPreferences = {
  time_zone?: string | null;
};

export type WorkspacePreferences = {
  ai_script_profile_name?: string | null;
  ai_script_markdown?: string | null;
};

export type Notification = {
  id: string;
  type: string;
  title: string;
  body: string;
  link_url?: string | null;
  is_read: boolean;
  read_at?: string | null;
  created_at: string;
  metadata_json?: Record<string, unknown> | null;
};

export type OverviewMetrics = {
  total_assigned: number;
  not_started: number;
  in_progress: number;
  completed: number;
  failed: number;
  overdue: number;
  completion_rate: number;
  average_score: number;
  average_first_attempt_accuracy: number;
  average_final_accuracy: number;
};

export type TopicMetric = {
  topic: string;
  questions_answered: number;
  first_attempt_accuracy: number;
  final_accuracy: number;
  failure_rate: number;
};

export type Certificate = {
  certificate_number: string;
  issued_at: string;
  employee_name: string;
  employee_email: string;
  training_title: string;
  assignment_name: string;
  score?: number | null;
  download_path: string;
};

export type QuestionOption = {
  id: string;
  text: string;
  sort_order: number;
  is_correct?: boolean;
};

export type Question = {
  id: string;
  text: string;
  type: string;
  topic?: string | null;
  difficulty?: string | null;
  hint?: string | null;
  explanation?: string | null;
  status?: string;
  sort_order: number;
  options: QuestionOption[];
  attempts_used?: number;
  attempts_remaining?: number;
  terminal?: boolean;
};

export type Training = {
  id: string;
  title: string;
  description?: string | null;
  category?: string | null;
  status: string;
  current_version_id?: string | null;
  version_number?: number | null;
  question_count: number;
  published_at?: string | null;
  content_source?: {
    id: string;
    source_url?: string | null;
    title?: string | null;
    duration_seconds?: number | null;
    thumbnail_url?: string | null;
  } | null;
  research_material?: {
    query?: string | null;
    overview?: string | null;
    sections: {
      title: string;
      summary: string;
      bullets: string[];
      citations: string[];
    }[];
    sources: {
      title: string;
      url: string;
      domain?: string | null;
    }[];
  } | null;
  learning_objectives?: { id: string; text: string; sort_order: number }[];
  questions?: Question[];
};

export type Assignment = {
  id: string;
  name: string;
  status?: string | null;
  training_title: string;
  due_at?: string | null;
  start_at?: string | null;
  passing_score: number;
  required_watch_percentage: number;
  max_attempts_per_question: number;
  watch_percentage?: number;
  final_score?: number | null;
  question_count?: number;
  completed_at?: string | null;
  certificate?: Certificate | null;
};

export type AssignmentDetail = Assignment & {
  assignment_recipient_id: string;
  description?: string | null;
  video_url?: string | null;
  video_title?: string | null;
  video_duration_seconds?: number | null;
  quiz_ready: boolean;
};

export type QuizStart = {
  quiz_session_id: string;
  assignment_id: string;
  max_attempts_per_question: number;
  questions: Question[];
};

export type AttemptResult = {
  correct: boolean;
  attempt_number: number;
  attempts_remaining: number;
  terminal: boolean;
  message?: string | null;
  hint?: string | null;
  explanation?: string | null;
  correct_option_id?: string | null;
};

export type ResultPayload = {
  status: string;
  completed_at?: string | null;
  official_score?: number | null;
  passing_score: number;
  first_attempt_accuracy?: number | null;
  final_accuracy?: number | null;
  video_completion_percentage: number;
  summary?: {
    strengths: string[];
    needs_improvement: string[];
    recommended_review: { topic?: string; startSeconds?: number; endSeconds?: number }[];
    summary?: string | null;
  } | null;
  question_breakdown: Question[];
  certificate?: Certificate | null;
};

export type LearnerProgress = {
  assignment_recipient_id: string;
  assignment_id: string;
  employee_id: string;
  employee_name: string;
  employee_email: string;
  assignment_name: string;
  training_title: string;
  status: string;
  due_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  final_score?: number | null;
  certificate?: Certificate | null;
};
