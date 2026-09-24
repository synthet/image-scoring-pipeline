import { api, ApiError } from '@/api/client'

export type DimensionKind = 'composite' | 'model' | 'shadow'

export interface SeriesMeta {
  kind: DimensionKind
  count: number
  coverage_pct: number
}

export interface Scope {
  kind: 'library' | 'keyword'
  keyword?: string
}

export interface ScoreMatrix {
  fingerprint: string
  generated_at: string
  scope: Scope
  image_count: number
  image_ids: number[]
  keys: string[]
  meta: Record<string, SeriesMeta>
  series: Record<string, (number | null)[]>
}

export interface Histogram {
  lo: number
  hi: number
  counts: number[]
}

export interface Descriptives {
  count: number
  coverage_pct: number | null
  mean?: number | null
  median?: number | null
  mode?: number | null
  min?: number | null
  max?: number | null
  range?: number | null
  q1?: number | null
  q3?: number | null
  iqr?: number | null
  variance?: number | null
  std?: number | null
  skewness?: number | null
  kurtosis?: number | null
  whisker_lo?: number | null
  whisker_hi?: number | null
  outliers?: number
  histogram: Histogram
}

type Matrix = (number | null)[][]

export interface ScoreStats {
  fingerprint: string
  scope: Scope
  image_count: number
  keys: string[]
  meta: Record<string, SeriesMeta>
  descriptives: Record<string, Descriptives>
  correlation: {
    pearson: Matrix
    pearson_p: Matrix
    spearman: Matrix
    spearman_p: Matrix
    n: number[][]
  }
}

export interface Coefficient {
  name: string
  beta: number | null
  std_beta: number | null
  se: number | null
  t: number | null
  p: number | null
  ci_lo: number | null
  ci_hi: number | null
  vif: number | null
  vif_infinite: boolean
  configured_weight: number | null
}

export type Severity = 'high' | 'warn' | 'info' | 'ok'

export interface ScoreRegression {
  scope: Scope
  target: string
  predictors: string[]
  complete_rows: number
  image_count: number
  configured_weights: Record<string, number> | null
  n: number
  k: number
  dof: number
  rank_deficient: boolean
  intercept: { beta: number | null; se: number | null; t: number | null; p: number | null }
  coefficients: Coefficient[]
  r2: number | null
  adj_r2: number | null
  cv_r2: number | null
  rmse: number | null
  mae: number | null
  f_stat: number | null
  f_p: number | null
  residuals: { fitted: number[]; residual: number[]; sampled: number; histogram: Histogram }
  recommendations: { severity: Severity; message: string }[]
}

export interface StackModelSignal {
  dimension: string
  stacks: number
  images: number
  within_std_mean: number | null
  within_range_mean: number | null
  within_share: number | null
  tie_rate: number | null
  top_gap_mean: number | null
  top_gap_z: number | null
  pick_auc: number | null
  pick_pairs: number
  reject_auc: number | null
  reject_pairs: number
  pick_top1_rate: number | null
  pick_stacks: number
  best_match_rate: number | null
  best_stacks: number
}

export interface ScoreStacks {
  scope: Scope
  image_count: number
  meta: Record<string, SeriesMeta>
  min_size: number
  stacks_considered: number
  images_in_stacks: number
  stacks_with_picks: number
  keys: string[]
  models: StackModelSignal[]
  ranking: string[]
  agreement: { spearman: Matrix; stacks: number[][] }
}

export interface KeywordDimensionProfile {
  dimension: string
  count: number
  mean: number | null
  median: number | null
  std: number | null
  rest_mean: number | null
  mean_delta: number | null
  cohens_d: number | null
  rank_shift: number | null
}

export interface ScoreKeywordProfiles {
  image_count: number
  keys: string[]
  keywords: { keyword: string; images: number; dimensions: KeywordDimensionProfile[] }[]
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** True when the backend reports the analytics need PostgreSQL. */
export function isNotPostgres(err: unknown): boolean {
  return err instanceof ApiError && err.status === 501
}

export const scoreAnalyticsApi = {
  // The matrix endpoint sends ETag + `Cache-Control: no-cache`, so the browser
  // revalidates and a 304 reuses its cached body transparently.
  matrix: (keyword?: string | null) =>
    api.get<ScoreMatrix>(`/analytics/scores/matrix${qs({ keyword })}`),
  stats: (keyword?: string | null) =>
    api.get<ScoreStats>(`/analytics/scores/stats${qs({ keyword })}`),
  regression: (target: string, predictors: string[] | null, keyword?: string | null) =>
    api.get<ScoreRegression>(
      `/analytics/scores/regression${qs({ target, predictors: predictors?.join(','), keyword })}`,
    ),
  stacks: (keyword?: string | null, minSize = 2) =>
    api.get<ScoreStacks>(`/analytics/scores/stacks${qs({ keyword, min_size: minSize })}`),
  keywords: (limit = 20, minImages = 30) =>
    api.get<ScoreKeywordProfiles>(`/analytics/scores/keywords${qs({ limit, min_images: minImages })}`),
}

type CI = [number | null, number | null]

export interface SuitabilityRow {
  dimension: string
  kind: DimensionKind
  G: number | null
  G_ci: CI
  G_n: number | null
  C: number | null
  C_ci: CI
  C_clusters: number | null
  in_Na: boolean | null
  in_Nb: boolean | null
  role: 'global' | 'culling' | 'both' | 'neither' | 'unknown'
  provisional: boolean
  caveats: string[]
}

export interface CullingMetric {
  pairs: number
  decisive_pairs?: number
  clusters?: number
  score_tie_rate?: number | null
  pairwise_accuracy_macro?: number | null
  pairwise_accuracy_macro_ci?: CI
  top1_agreement?: number | null
  ndcg_at_3?: number | null
  kendall_tau_b_mean?: number | null
}

export interface LabelSource {
  description: string
  independent: boolean
  images?: number
  rows?: number
  picks?: number
  rejects?: number
  decisive_clusters?: number
  equals_score_rating_pct?: number | null
}

export interface LogitEval {
  log_loss: number
  accuracy: number
  brier: number
  ece: number
}

export interface ScoreSuitability {
  manifest: Record<string, unknown>
  scope: Scope
  images: number
  dimensions: string[]
  kinds: Record<string, DimensionKind>
  clusters: { definition: string; count: number; images_in_clusters: number; standalone_images: number }
  split: { method: string; images: Record<string, number> }
  labels: {
    sources: Record<string, LabelSource>
    notes: string[]
    not_measurable: string[]
    culling_source: string
    culling_independent: boolean
    global_source: string | null
    global_independent: boolean
  }
  variance: Record<string, { within_share_cluster_weighted?: number | null; within_share_cluster_weighted_ci?: CI; icc1?: number | null; clusters?: number }>
  correlation: {
    keys: string[]
    pooled_spearman: { r: Matrix }
    within_spearman: { r: Matrix }
    pooled_vs_within: { a: string; b: string; pooled: number; within: number; delta: number; sign_flip: boolean }[]
  }
  culling: { label_source: string; labels_independent: boolean; all: Record<string, CullingMetric>; test: Record<string, CullingMetric> }
  pairwise_model: {
    grouped_cv_dev: {
      pairs?: number
      skipped?: string
      equation?: string
      cv?: LogitEval
      coefficients?: { dimension: string; beta_std: number; single_log_loss: number; marginal_log_loss_gain: number | null }[]
    }
    holdout: { skipped?: string; temperature?: number; test_calibrated?: LogitEval; test_uncalibrated?: LogitEval }
  }
  suitability: { evaluation_set: string; thresholds: { global: string; culling: string }; map: SuitabilityRow[] }
  subgroups: ({ stratum: string; value: string; clusters: number; note?: string } & Record<string, unknown>)[]
  findings: string[]
}

export const suitabilityApi = {
  get: (opts: { keyword?: string | null; cullingLabels: string; trustXmp: boolean; minSize: number }) =>
    api.get<ScoreSuitability>(
      `/analytics/scores/suitability${qs({
        keyword: opts.keyword,
        culling_labels: opts.cullingLabels,
        trust_xmp_ratings: opts.trustXmp ? 'true' : null,
        min_size: opts.minSize,
      })}`,
    ),
}
