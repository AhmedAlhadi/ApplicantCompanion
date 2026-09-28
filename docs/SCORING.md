# Job-fit score

The fit score is calculated in `backend/app/scoring/engine.py` from structured requirement matches. The model does not choose the number. It only writes the narrative (risks, advantages, explanation).

A requirement that was extracted but could not be evaluated stays in the sum. Dropping it and rescaling the rest treats that requirement as if it had scored like the ones that were checked, which inflates the result when the checked subset is the matches.

## Requirement score

Each requirement has a status and a match confidence in \([0, 1]\).

| Status | Score \(s\) |
|---|---|
| MATCHED | \(1\) |
| PARTIALLY_MATCHED | \(0.3 + 0.4 \cdot \mathrm{clamp}(c, 0, 1)\) |
| TRANSFERABLE | \(0.5\) |
| NOT_MATCHED | \(0\) |
| UNKNOWN, or no match row | unresolved |

A partial match therefore sits in \([0.3, 0.7]\). A requirement with no match row is UNKNOWN. UNKNOWN is not a confirmed miss.

## Importance weight

| Importance | Weight |
|---|---|
| CRITICAL | 4 |
| HIGH | 3 |
| MEDIUM | 2 |
| LOW | 1 |

A preferred requirement keeps that weight and then multiplies it by \(1/2\). Call the result \(w_i\).

## Categories

Each requirement is placed in one scoring category. The default category weights are configurable in settings; these are the defaults.

| Category | Default weight |
|---|---|
| Mandatory qualifications | 0.25 |
| Relevant experience | 0.20 |
| Skills and tools | 0.15 |
| Responsibilities | 0.15 |
| Domain knowledge | 0.10 |
| Leadership / management | 0.05 |
| Education / certifications | 0.05 |
| Language / other | 0.05 |

`technical_skills` is the skills-and-tools category. The settings key `skills_and_tools` is an alias for it. Requirement `category` values map onto these buckets in `CATEGORY_MAP` in the engine.

A category that contains **no** requirements is left out, and the remaining category weights are divided by their sum so they still add up to 1. That category was not in the job description.

A category that contains only UNKNOWN requirements stays in. Its weight is not given to the categories that could be scored.

## Three readings of the same requirements

Inside a category \(c\) that has at least one requirement, evaluated or not:

\[
D_c = \frac{\sum_{i \in \mathrm{known}} s_i w_i}{\sum_{i \in c} w_i}
\]

\[
P_c = \frac{\sum_{i \in \mathrm{known}} s_i w_i + \sum_{i \in \mathrm{unknown}} w_i}{\sum_{i \in c} w_i}
\]

\[
M_c = \frac{\sum_{i \in \mathrm{known}} s_i w_i + \sum_{i \in \mathrm{unknown}} 0.5\, w_i}{\sum_{i \in c} w_i}
\]

\(D_c\) is the demonstrated category score: an unchecked requirement adds its weight to the denominator and nothing to the numerator. \(P_c\) is the possible score: the same requirement is treated as fully met. \(M_c\) is the midpoint: the unchecked requirement is counted at \(1/2\). These three are the same weighted mean with the unknown score set to \(0\), \(1\), and \(0.5\).

Let \(W_c\) be the category weight, and let \(C\) be the set of categories that contain at least one requirement. The published figures are

\[
\mathrm{demonstrated} = \frac{\sum_{c \in C} W_c D_c}{\sum_{c \in C} W_c}
\]

\[
\mathrm{possible} = \frac{\sum_{c \in C} W_c P_c}{\sum_{c \in C} W_c}
\]

\[
\mathrm{overall} = \frac{\sum_{c \in C} W_c M_c}{\sum_{c \in C} W_c} = \frac{\mathrm{demonstrated} + \mathrm{possible}}{2}
\]

Stored fields:

| Field | Value |
|---|---|
| `overall_score_low` | demonstrated |
| `overall_score` | overall (the midpoint) |
| `overall_score_high` | possible |
| `category_scores` | each \(M_c\), so the bars match the published overall score |

When every requirement was evaluated, the three numbers are equal.

## Coverage

\[
\mathrm{coverage} = \frac{\sum_{i \in \mathrm{known}} w_i}{\sum_i w_i}
\]

Coverage is the importance-weighted share that was actually evaluated. It is not itself a fit score. Coverage \(0\) means nothing could be scored (no requirements, or every requirement UNKNOWN). The product shows that as not scored, and the recommendation is `incomplete`. The midpoint is still computed (\(0.5\) when every requirement is UNKNOWN, \(0\) when there are no requirements) so the range stays well defined.

## Recommendation

Compare the demonstrated and possible scores with the configured threshold \(T\) (default \(0.80\)).

| Condition | Recommendation |
|---|---|
| coverage \(= 0\) | `incomplete` |
| demonstrated \(\ge T\) | `strong_fit` |
| possible \(< T\) | `below_threshold` |
| otherwise | `incomplete` |

`strong_fit` means the score stays at or above the threshold even if every unchecked requirement is a miss. `below_threshold` means the score stays under the threshold even if every unchecked requirement is a full match. `incomplete` means the threshold sits inside the range, so the fit is not established.

Generation asks for an explicit decision unless the recommendation is `strong_fit`. That decision is advisory: the user can continue, review gaps, or cancel.

## Worked examples

Equal importance, one MATCHED and one UNKNOWN, same category. Demonstrated \(0.5\), published \(0.75\), possible \(1.0\), coverage \(0.5\), recommendation `incomplete`. The matched requirement is not reported as 100%.

English (LOW, language category, weight \(0.05\)) MATCHED, and a CRITICAL mandatory qualification (weight \(0.25\)) UNKNOWN. Other categories are absent, so the active weight is \(0.30\).

\[
\mathrm{overall} = \frac{0.05 \cdot 1 + 0.25 \cdot 0.5}{0.30} = 0.5833
\]

\[
\mathrm{demonstrated} = \frac{0.05}{0.30} = 0.1667
\qquad
\mathrm{possible} = 1
\]

Coverage is \(1 / 5 = 0.2\). The language match does not become the whole score.
