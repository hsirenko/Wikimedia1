# Agent evaluation

The skill is meant to work well on a fast, cheap model. These scenarios were run on **Claude Haiku
4.5** through the unpacked skill zip, exactly as a user would install it. Each reply was scored
with `check_reply.py` against the report it was based on.

## How to run a scenario

1. Build and unpack the skill: `sh scripts/build_zip.sh`, then unzip it somewhere.
2. Give the model the skill folder, a writable working folder and the user's prompt. Ask it to
   write its reply to the user, exactly as it would send it, to `reply.txt`. (Asking it to
   append a list of commands to the reply itself distorts the reply's ending.)
3. Score the reply: `python evals/check_reply.py reply.txt --report <report folder>`.

`check_reply.py` checks that:
- the recommendation comes before the KPI breakdown;
- at least 6 of the 8 KPIs are named;
- the last line offers the one-page PDF;
- there's no go/no-go or pick-a-winner wording, and no guessed causes;
- **every percentage and every number of 4+ digits in the reply appears in `report.md`**. This
  catches invented figures, such as a "−67%" computed from mismatched periods.

## Scenarios

| # | Prompt (as the user wrote it) | Expected command | What it tests |
|---|---|---|---|
| 1 | Ми думаємо додати курс з астрономії до освітнього застосунку. Чи зростає інтерес до цієї теми в україномовній Wikipedia, і наскільки цьому зростанню можна довіряти? | `analyze --topic astronomy --language uk` | one edition; "can we trust it" answered with quality, anomalies and the edition comparison; Ukrainian |
| 2 | Порівняй зростання інтересу до інтервального голодування в польськомовній та чеськомовній Wikipedia за останні два роки. | `compare --topic "intermittent fasting" --languages pl,cs --period 2y` | a period from the prompt; an edition with no article (pl) handled as a finding, with stand-in candidates |
| 3 | Ми створюємо застосунок для вивчення мов. Порівняй інтерес до вивчення англійської у вибраних нами мовних розділах (німецька, іспанська, турецька, корейська, польська) та підготуй короткий звіт: які аудиторії варто дослідити наступними й чому? | `compare --topic "English as a second or foreign language" --languages de,es,tr,ko,pl` | choosing the concept; "which audiences next and why" answered by the recommendation's rule |
| 4 | (follow-up to 2) А тепер додай словацьку і візьми три роки. | `compare ... --languages pl,cs,sk --period 3y` | changed assumptions → rerun, not recomputation |
| 5 | Should we launch our meditation app in Germany? Give me the short version first. | `analyze --topic meditation --language de` | a leading question: no verdict; the recommendation's headline is the short version |
| 6 | Порівняй медитацію, йогу та сон у німецькій, французькій та іспанській Вікіпедії. Що нам запускати першим? | `portfolio ...` | a portfolio with a ranking request; the one-page PDF after "так" |

## Results

See the latest run below. Earlier rounds, and the fixes each failure led to, are summarised in
the main README ("How it was built and verified").

### Latest run (2026-09-27, Claude Haiku 4.5, installed from the zip)

| # | Scenario | Command the model ran | check_reply.py | Notes from reading the reply |
|---|---|---|---|---|
| 1 | Astronomy, uk | `analyze --topic astronomy --language uk` | 6/6 | recommendation first, trust answered with quality, anomaly and edition comparison, PDF offer last |
| 2 | Intermittent fasting, pl vs cs, 2 years | `compare ... --languages pl,cs --period 2y` | 6/6 | pl reported as "no article", with search candidates, not as zero interest |
| 4 | Follow-up: add Slovak, 3 years | `compare ... --languages pl,cs,sk --period 3y` | 6/6 | reran the command rather than recomputing |
| 3 | Learning English, 5 editions | `compare --topic "English language" ...` | 5/6 | chose the broader concept (stated in the reply via the tool's concept line); **added its own "priority 1/2/3" list by affinity** after the tool's recommendation: flagged by `no_verdict` |

**Earlier rounds on the same day** found problems that are now fixed in code:
- **Stale copy:** an old skill copy next to the Python path was used. The test setup now leaves no other copies.
- **Answering from samples:** replies came from bundled sample reports without running anything, so the zip ships no samples.
- **Missing module:** an unanchored zip exclude dropped a code package. `tests/test_build_zip.py` now checks every source file is in the zip.
- **Instructions leaking:** agent-only text on the block headers was copied into replies. Headers are now plain labels.
- **False verdict opener:** "варто дослідити" triggered the DECISION REQUEST opener.
- **Misread momentum:** momentum points were reported as "+8,3%".
- **Missing article as a priority:** a missing article was treated as a research priority. The tool now says it isn't evidence of an untapped market.

**Open issue:** with "which audiences should we research next and why?", Haiku tends to add its own ordering of the monitored options, based on affinity. Each claim in it is grounded in the report, but the order is not the tool's rule. The tool now explains every option, and `check_reply.py` flags such lists. A next step would be a user criterion that weights affinity (for localization questions), so that order comes from the tool.
