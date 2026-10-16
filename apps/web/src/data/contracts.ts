/* Generated from contracts/answer.schema.json. Do not edit. */

export type QuestionId = string;
export type QuestionVersion = number;
export type AsOf = string;
export type ValidUntil = string | null;
export type DataThrough = string | null;
export type Verdict = string;
export type Confidence = "high" | "medium" | "low" | "none";
export type Coverage = number;
export type Feature = string;
export type Effect = "+" | "-" | "0";
export type Drivers = Driver[];
export type Kind = string;
export type Label = string;
export type Ref = string | null;
export type Url = string | null;
export type Evidence = Evidence1[];
export type En = string;
export type Fil = string | null;
export type Name = string;
export type Version = string;
export type Status = "validated" | "experimental" | "unvalidated" | "planned";
export type BacktestRef = string | null;
export type Notes = string | null;
export type License1 = "PUBLIC_DOMAIN" | "ATTRIBUTION" | "SHARE_ALIKE" | "UNCLEAR" | "NON_COMMERCIAL";
export type License = License1[];
export type Sources = string[];
export type Attributions = string[];
export type Caveats = string[];

/**
 * One question evaluated for one scope at one point in time.
 */
export interface Answer {
  question_id: QuestionId;
  question_version: QuestionVersion;
  scope: Scope;
  as_of: AsOf;
  valid_until?: ValidUntil;
  data_through?: DataThrough;
  verdict: Verdict;
  value?: Value;
  confidence: Confidence;
  coverage: Coverage;
  drivers?: Drivers;
  evidence?: Evidence;
  text: LocalizedText;
  model: ModelInfo;
  license: License;
  sources?: Sources;
  attributions?: Attributions;
  caveats?: Caveats;
}
export interface Scope {
  [k: string]: string;
}
export interface Value {
  [k: string]: unknown;
}
export interface Driver {
  feature: Feature;
  value: Value1;
  effect?: Effect;
}
export interface Value1 {
  [k: string]: unknown;
}
export interface Evidence1 {
  kind: Kind;
  label: Label;
  ref?: Ref;
  url?: Url;
  value?: Value2;
}
export interface Value2 {
  [k: string]: unknown;
}
export interface LocalizedText {
  en: En;
  fil?: Fil;
}
export interface ModelInfo {
  name: Name;
  version: Version;
  status: Status;
  backtest_ref?: BacktestRef;
  notes?: Notes;
}
