import type { BakedAnswer } from "../data/types";
import { shortDate, text } from "../format";
import { useLang } from "../i18n";
import { ConfidenceChip, StatusChip, VerdictChip } from "./Chips";

export function AnswerCard({
  answer,
  title,
  children,
}: {
  answer: BakedAnswer;
  title?: string;
  children?: React.ReactNode;
}) {
  const { lang, t } = useLang();
  return (
    <article className="card">
      <header className="card-head">
        {title ? <h3>{title}</h3> : null}
        <div className="chips">
          <VerdictChip verdict={answer.verdict} />
          <ConfidenceChip level={answer.confidence} />
          <StatusChip status={answer.model.status} />
        </div>
      </header>
      <p className="answer-text">{text(answer, lang)}</p>
      {children}
      <details className="more">
        <summary>{t("why")}</summary>
        {answer.drivers && answer.drivers.length > 0 ? (
          <ul>
            {answer.drivers.map((d) => (
              <li key={d.feature}>
                {d.feature.replace(/_/g, " ")}: <strong>{String(d.value)}</strong>{" "}
                {d.effect !== "0" ? `(${d.effect})` : ""}
              </li>
            ))}
          </ul>
        ) : null}
        {answer.evidence && answer.evidence.length > 0 ? (
          <ul>
            {answer.evidence.map((e) => (
              <li key={e.label}>
                {e.label}
                {e.value !== undefined && e.value !== null ? `: ${String(e.value)}` : ""}
              </li>
            ))}
          </ul>
        ) : null}
        <h4>{t("caveats")}</h4>
        <ul>
          {(answer.caveats ?? []).map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <p className="meta">
          {answer.data_through ? `${t("dataThrough")} ${shortDate(answer.data_through)} · ` : ""}
          {(answer.sources ?? []).join(", ")}
          {answer.commercial_ok ? "" : " · research use only"}
        </p>
      </details>
    </article>
  );
}
